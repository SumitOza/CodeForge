"""ui/app.py — Gradio web UI for CodeForge."""
import gradio as gr
import httpx, json, os, threading, time
from config import PROVIDER_MODELS, DEFAULT_AGENT_MODELS

API = os.getenv("API_BASE", "http://localhost:8000/api")

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def api_post(path, body, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.post(f"{API}{path}", json=body, headers=headers, timeout=30)
        return r.json(), r.status_code
    except Exception as e:
        return {"detail": str(e)}, 500

def api_get(path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.get(f"{API}{path}", headers=headers, timeout=15)
        return r.json(), r.status_code
    except Exception as e:
        return {"detail": str(e)}, 500

def api_delete(path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.delete(f"{API}{path}", headers=headers, timeout=10)
        return r.status_code
    except Exception as e:
        return 500


# ── Auth handlers ─────────────────────────────────────────────────────────────
def handle_login(email, password):
    data, code = api_post("/auth/login", {"email": email, "password": password})
    if code == 200:
        return (
            data["access_token"], data["full_name"], data["email"],
            gr.update(visible=False), gr.update(visible=True),
            f"Welcome back, {data['full_name']}!", ""
        )
    return ("", "", "", gr.update(visible=True), gr.update(visible=False),
            "", f"Error: {data.get('detail','Login failed')}")

def handle_register(full_name, email, password):
    data, code = api_post("/auth/register", {"full_name": full_name, "email": email, "password": password})
    if code == 201:
        return (
            data["access_token"], data["full_name"], data["email"],
            gr.update(visible=False), gr.update(visible=True),
            f"Welcome to CodeForge, {data['full_name']}!", ""
        )
    return ("", "", "", gr.update(visible=True), gr.update(visible=False),
            "", f"Error: {data.get('detail','Registration failed')}")

def handle_logout(token):
    return ("", "", "", gr.update(visible=True), gr.update(visible=False), "", "")


# ── Keys handlers ─────────────────────────────────────────────────────────────
def load_keys(token):
    if not token:
        return "Not logged in."
    data, code = api_get("/keys/", token)
    if code != 200:
        return f"Error: {data.get('detail')}"
    if not data:
        return "No API keys saved yet."
    rows = [f"• **{k['provider']}** — `{k['key_preview']}` (added {k['created_at'][:10]})" for k in data]
    return "\n".join(rows)

def save_key(token, provider, key_value):
    if not token:
        return "Please log in first.", load_keys(token)
    data, code = api_post("/keys/", {"provider": provider, "key_value": key_value}, token)
    if code == 201:
        return f"Key saved for {provider}.", load_keys(token)
    return f"Error: {data.get('detail')}", load_keys(token)

def remove_key(token, provider):
    if not token:
        return "Please log in first.", load_keys(token)
    api_delete(f"/keys/{provider}", token)
    return f"Removed {provider} key.", load_keys(token)


# ── Build handlers ────────────────────────────────────────────────────────────
def start_build(token, prompt, arch_p, arch_m, cod_p, cod_m, rev_p, rev_m, fix_p, fix_m):
    if not token:
        return "Please log in first.", ""
    agent_models = {
        "architect":   {"provider": arch_p, "model_id": arch_m},
        "coder":       {"provider": cod_p,  "model_id": cod_m},
        "reviewer":    {"provider": rev_p,  "model_id": rev_m},
        "fixer":       {"provider": fix_p,  "model_id": fix_m},
        "filemanager": {"provider": rev_p,  "model_id": rev_m},
    }
    data, code = api_post("/build/start", {"prompt": prompt, "agent_models": agent_models}, token)
    if code == 202:
        return f"Build started! Session: `{data['session_id']}`", data["session_id"]
    return f"Error: {data.get('detail')}", ""

def poll_status(token, session_id):
    if not token or not session_id:
        return "No active session."
    data, code = api_get(f"/build/sessions/{session_id}", token)
    if code != 200:
        return f"Error: {data.get('detail')}"
    files_done = data.get("files_done", [])
    files_failed = data.get("files_failed", [])
    tokens = data.get("total_tokens", 0)
    status = data.get("status", "unknown")
    return (
        f"**Status:** {status}\n"
        f"**Files done:** {len(files_done)} | **Failed:** {len(files_failed)}\n"
        f"**Tokens used:** {tokens:,}\n\n"
        + ("\n".join(f"✅ {f}" for f in files_done))
        + ("\n".join(f"❌ {f}" for f in files_failed))
    )

def load_sessions(token):
    if not token:
        return "Not logged in."
    data, code = api_get("/build/sessions", token)
    if code != 200:
        return "Error loading sessions."
    if not data:
        return "No build sessions yet."
    rows = []
    for s in data:
        rows.append(f"• `{s['id'][:8]}...` — {s['status']} — {s.get('prompt','')[:60]}")
    return "\n".join(rows)


# ── Model dropdowns ───────────────────────────────────────────────────────────
all_providers = list(PROVIDER_MODELS.keys())
def models_for(provider):
    return [m["model_id"] for m in PROVIDER_MODELS.get(provider, [])]

def update_model_choices(provider):
    choices = models_for(provider)
    return gr.update(choices=choices, value=choices[0] if choices else None)


# ── Gradio UI ─────────────────────────────────────────────────────────────────
with gr.Blocks(title="CodeForge") as demo:
    token_state   = gr.State("")
    session_state = gr.State("")
    user_name     = gr.State("")
    user_email    = gr.State("")

    gr.Markdown("# ⚙️ CodeForge\n### Multi-agent AI code builder — describe any project, get working code.")

    status_bar = gr.Markdown("")

    # ── Auth panel ────────────────────────────────────────────────────────────
    with gr.Group(visible=True) as auth_panel:
        with gr.Tabs():
            with gr.Tab("Login"):
                li_email = gr.Textbox(label="Email", placeholder="you@example.com")
                li_pass  = gr.Textbox(label="Password", type="password")
                li_btn   = gr.Button("Login", variant="primary")
                li_err   = gr.Markdown("")
            with gr.Tab("Register"):
                re_name  = gr.Textbox(label="Full name")
                re_email = gr.Textbox(label="Email")
                re_pass  = gr.Textbox(label="Password (min 8 chars)", type="password")
                re_btn   = gr.Button("Create account", variant="primary")
                re_err   = gr.Markdown("")

    # ── Main app ──────────────────────────────────────────────────────────────
    with gr.Group(visible=False) as app_panel:
        with gr.Row():
            gr.Markdown("### CodeForge")
            logout_btn = gr.Button("Logout", size="sm", scale=0)

        with gr.Tabs():

            # Build tab
            with gr.Tab("Build"):
                prompt_in = gr.Textbox(
                    label="Describe your project",
                    placeholder="Build a FastAPI REST API for a todo app with SQLite and JWT auth",
                    lines=4
                )

                gr.Markdown("**Agent model configuration**")
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("Architect")
                        arch_p = gr.Dropdown(choices=all_providers, value="cerebras", label="Provider")
                        arch_m = gr.Dropdown(choices=models_for("cerebras"), value=models_for("cerebras")[0], label="Model")
                    with gr.Column():
                        gr.Markdown("Coder")
                        cod_p = gr.Dropdown(choices=all_providers, value="cerebras", label="Provider")
                        cod_m = gr.Dropdown(choices=models_for("cerebras"), value=models_for("cerebras")[1], label="Model")
                    with gr.Column():
                        gr.Markdown("Reviewer")
                        rev_p = gr.Dropdown(choices=all_providers, value="groq", label="Provider")
                        rev_m = gr.Dropdown(choices=models_for("groq"), value=models_for("groq")[0], label="Model")
                    with gr.Column():
                        gr.Markdown("Fixer")
                        fix_p = gr.Dropdown(choices=all_providers, value="cerebras", label="Provider")
                        fix_m = gr.Dropdown(choices=models_for("cerebras"), value=models_for("cerebras")[0], label="Model")

                # Update model choices when provider changes
                arch_p.change(update_model_choices, arch_p, arch_m)
                cod_p.change(update_model_choices, cod_p, cod_m)
                rev_p.change(update_model_choices, rev_p, rev_m)
                fix_p.change(update_model_choices, fix_p, fix_m)

                build_btn    = gr.Button("Build project", variant="primary")
                build_status = gr.Markdown("")
                poll_btn     = gr.Button("Refresh status")
                build_log    = gr.Markdown("")

                build_btn.click(
                    start_build,
                    [token_state, prompt_in, arch_p, arch_m, cod_p, cod_m, rev_p, rev_m, fix_p, fix_m],
                    [build_status, session_state]
                )
                poll_btn.click(poll_status, [token_state, session_state], build_log)

            # API Keys tab
            with gr.Tab("API Keys"):
                gr.Markdown("Your keys are stored AES-256 encrypted. Only previews are shown.")
                keys_display = gr.Markdown("")
                with gr.Row():
                    key_provider = gr.Dropdown(choices=all_providers, value="cerebras", label="Provider")
                    key_value    = gr.Textbox(label="API Key", type="password", placeholder="sk-...")
                with gr.Row():
                    save_key_btn   = gr.Button("Save key", variant="primary")
                    remove_key_btn = gr.Button("Remove key")
                key_msg = gr.Markdown("")

                save_key_btn.click(save_key, [token_state, key_provider, key_value], [key_msg, keys_display])
                remove_key_btn.click(remove_key, [token_state, key_provider], [key_msg, keys_display])

            # History tab
            with gr.Tab("Build history"):
                refresh_hist = gr.Button("Refresh")
                history_display = gr.Markdown("")
                refresh_hist.click(load_sessions, token_state, history_display)

    # ── Auth wiring ───────────────────────────────────────────────────────────
    auth_outputs = [token_state, user_name, user_email, auth_panel, app_panel, status_bar, li_err]

    li_btn.click(handle_login, [li_email, li_pass], auth_outputs)
    re_btn.click(handle_register, [re_name, re_email, re_pass],
                 [token_state, user_name, user_email, auth_panel, app_panel, status_bar, re_err])
    logout_btn.click(handle_logout, token_state,
                     [token_state, user_name, user_email, auth_panel, app_panel, status_bar, li_err])

    # Load keys and sessions when app panel becomes visible
    token_state.change(lambda t: (load_keys(t), load_sessions(t)),
                     token_state, [keys_display, history_display])


if __name__ == "__main__":
    import subprocess, threading
    # Start FastAPI in background
    api = threading.Thread(
        target=lambda: subprocess.run(["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]),
        daemon=True
    )
    api.start()
    time.sleep(2)
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)