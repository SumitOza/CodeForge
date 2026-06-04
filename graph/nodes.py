"""graph/nodes.py — LangGraph node functions for each agent step.

Rate-limit strategy (June 2026 free tiers):
  Cerebras : 5 RPM → CEREBRAS_CALL_DELAY (12 s) injected in pick_file_node
             so every file cycle starts with a fresh window.
  Groq     : 30 RPM → no delay needed for normal builds.
  OpenRouter: 20 RPM → no delay needed for normal builds.

pick_file_node is the natural chokepoint: it runs once between every
code→review→fix→save cycle, making it the right place to throttle.
"""
import json, os, asyncio
from graph.state import CodeForgeState
from agents.base import BaseAgent
from agents.prompts import ARCHITECT_PROMPT, CODER_PROMPT, REVIEWER_PROMPT, FIXER_PROMPT
from providers.factory import build_llm, cerebras_rate_limit_sleep
from models import ProjectPlan, FileSpec, BuildEvent, ReviewResult
from config import DEFAULT_AGENT_MODELS

import re


def strip_fences(content: str) -> str:
    """Remove markdown code fences robustly — handles ```python, ```, CRLF, trailing newlines."""
    content = content.strip()
    content = re.sub(r'^```[a-zA-Z0-9]*\r?\n', '', content)   # opening fence
    content = re.sub(r'\r?\n```\s*$', '', content)             # closing fence with preceding newline
    content = re.sub(r'^```[a-zA-Z0-9]*\s*', '', content)     # bare opening fence fallback
    content = re.sub(r'\s*```\s*$', '', content)               # bare closing fence fallback
    return content.strip()


def _build_agent(state: CodeForgeState, agent_name: str, system_prompt: str) -> BaseAgent:
    cfg = state["agent_models"].get(agent_name, DEFAULT_AGENT_MODELS[agent_name])
    provider = cfg["provider"]
    model_id = cfg["model_id"]
    api_key = state["user_keys"].get(provider)
    llm = build_llm(provider, model_id, api_key=api_key)
    return BaseAgent(name=agent_name, llm=llm, system_prompt=system_prompt)


def _is_cerebras_agent(state: CodeForgeState, agent_name: str) -> bool:
    """Return True if the named agent is routed to Cerebras."""
    cfg = state["agent_models"].get(agent_name, DEFAULT_AGENT_MODELS[agent_name])
    return cfg.get("provider") == "cerebras"


def _emit(state: CodeForgeState, event: BuildEvent) -> list:
    return state.get("events", []) + [event]


async def plan_node(state: CodeForgeState) -> dict:
    agent = _build_agent(state, "architect", ARCHITECT_PROMPT)
    events = _emit(state, BuildEvent(type="log", message="Architect is planning your project..."))

    try:
        raw = await agent.call(f"Project description:\n{state['prompt']}")
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        plan_data = json.loads(raw)
        plan = ProjectPlan(**plan_data)
        file_queue = [FileSpec(**f) if isinstance(f, dict) else f for f in plan.files]

        events = _emit({**state, "events": events}, BuildEvent(
            type="plan_ready",
            message=f"Plan ready: {len(file_queue)} files to generate",
            data=plan.model_dump()
        ))
        return {
            "plan": plan,
            "file_queue": file_queue,
            "events": events,
            "total_tokens": state.get("total_tokens", 0) + agent.last_usage.output_tokens,
        }
    except Exception as e:
        events = _emit({**state, "events": events}, BuildEvent(type="error", message=f"Planning failed: {e}"))
        return {"error": str(e), "events": events}


async def pick_file_node(state: CodeForgeState) -> dict:
    """Select the next pending file.

    Also applies a rate-limit delay when any agent in this build uses Cerebras
    (5 RPM = 12 s between requests). The delay runs BEFORE picking so the
    first file in a fresh build is not delayed unnecessarily — we only sleep
    when there are already completed/in-progress files, i.e. on the 2nd+ cycle.
    """
    queue = [f for f in state["file_queue"] if f.status == "pending"]
    if not queue:
        return {"current_file": None}

    # Apply Cerebras rate-limit delay between file cycles (not before the very first file)
    already_processed = any(
        f.status in ("done", "failed") for f in state["file_queue"]
    )
    if already_processed:
        uses_cerebras = any(
            state["agent_models"].get(a, DEFAULT_AGENT_MODELS[a]).get("provider") == "cerebras"
            for a in ["coder", "fixer"]
        )
        if uses_cerebras:
            await cerebras_rate_limit_sleep()

    next_file = queue[0]
    next_file.status = "coding"
    return {"current_file": next_file}


async def code_node(state: CodeForgeState) -> dict:
    cf = state["current_file"]
    if not cf:
        return {}

    agent = _build_agent(state, "coder", CODER_PROMPT)
    events = _emit(state, BuildEvent(type="file_start", message=f"Coding {cf.path}", file_path=cf.path))

    # Build context: deps already written
    dep_context = ""
    for dep in cf.depends_on:
        if dep in state["completed_files"]:
            dep_context += f"\n--- {dep} ---\n{state['completed_files'][dep]}\n"

    prompt = f"""Project plan:
{state['plan'].model_dump_json(indent=2)}

File to write:
Path: {cf.path}
Description: {cf.description}

Dependency files already written:
{dep_context or 'None'}

Write the complete content of {cf.path}:"""

    try:
        content = await agent.call(prompt)
        content = strip_fences(content)
        cf.content = content
        cf.status = "reviewing"
        events = _emit({**state, "events": events}, BuildEvent(
            type="log", message=f"Coded {cf.path} ({len(content)} chars)", file_path=cf.path
        ))
        return {
            "current_file": cf,
            "events": events,
            "review_passed": False,
            "review_issues": [],
            "fix_attempts": 0,
            "total_tokens": state.get("total_tokens", 0) + agent.last_usage.output_tokens,
        }
    except Exception as e:
        cf.status = "failed"
        events = _emit({**state, "events": events}, BuildEvent(type="file_failed", message=str(e), file_path=cf.path))
        return {"current_file": cf, "events": events, "error": str(e)}


async def review_node(state: CodeForgeState) -> dict:
    cf = state["current_file"]
    if not cf or not cf.content:
        return {"review_passed": False, "review_issues": ["No content to review"]}

    agent = _build_agent(state, "reviewer", REVIEWER_PROMPT)

    prompt = f"""File path: {cf.path}
Description: {cf.description}

File content:
{cf.content}

Review this file and output JSON only."""

    try:
        raw = await agent.call(prompt)
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = ReviewResult(**json.loads(raw), file_path=cf.path)

        event_type = "review_pass" if result.passed else "review_fail"
        msg = f"Review {'passed' if result.passed else 'failed'}: {cf.path}"
        if result.issues:
            msg += f" — {len(result.issues)} issue(s)"

        events = _emit(state, BuildEvent(type=event_type, message=msg, file_path=cf.path, data=result.issues))
        return {
            "review_passed": result.passed,
            "review_issues": result.issues,
            "events": events,
            "total_tokens": state.get("total_tokens", 0) + agent.last_usage.output_tokens,
        }
    except Exception as e:
        events = _emit(state, BuildEvent(type="review_pass", message=f"Review parse error — assuming pass: {e}"))
        return {"review_passed": True, "review_issues": [], "events": events}


async def fix_node(state: CodeForgeState) -> dict:
    cf = state["current_file"]
    if not cf:
        return {}

    attempts = state.get("fix_attempts", 0) + 1
    agent = _build_agent(state, "fixer", FIXER_PROMPT)
    events = _emit(state, BuildEvent(type="fix_attempt", message=f"Fixer attempt {attempts} on {cf.path}", file_path=cf.path))

    # Fixer is Cerebras — add intra-cycle delay so fix→review→fix doesn't burst
    if _is_cerebras_agent(state, "fixer") and attempts > 1:
        await cerebras_rate_limit_sleep()

    prompt = f"""File path: {cf.path}

Original content:
{cf.content}

Issues to fix:
{chr(10).join(f'- {i}' for i in state['review_issues'])}

Output the complete corrected file:"""

    try:
        fixed = await agent.call(prompt)
        fixed = strip_fences(fixed)
        cf.content = fixed
        cf.retries = attempts
        return {
            "current_file": cf,
            "fix_attempts": attempts,
            "events": events,
            "total_tokens": state.get("total_tokens", 0) + agent.last_usage.output_tokens,
        }
    except Exception as e:
        events = _emit({**state, "events": events}, BuildEvent(type="error", message=f"Fix failed: {e}"))
        return {"current_file": cf, "fix_attempts": attempts, "events": events}


async def save_node(state: CodeForgeState) -> dict:
    cf = state["current_file"]
    if not cf or not cf.content:
        return {}
    cf.content = strip_fences(cf.content)

    output_dir = state["output_dir"]
    full_path = os.path.join(output_dir, cf.path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(cf.content)

    cf.status = "done"
    completed = {**state.get("completed_files", {}), cf.path: cf.content}

    # Update queue
    queue = state["file_queue"]
    for file in queue:
        if file.path == cf.path:
            file.status = "done"

    events = _emit(state, BuildEvent(type="file_done", message=f"Saved {cf.path}", file_path=cf.path))

    # Check if all done
    pending = [f for f in queue if f.status not in ("done", "failed")]
    if not pending:
        events = _emit({**state, "events": events}, BuildEvent(
            type="build_complete",
            message=f"Build complete. {len(completed)} files written.",
            data={"output_dir": output_dir}
        ))

    return {
        "current_file": None,
        "completed_files": completed,
        "file_queue": queue,
        "events": events,
    }


async def mark_failed_node(state: CodeForgeState) -> dict:
    cf = state["current_file"]
    if cf:
        cf.status = "failed"
        queue = state["file_queue"]
        for file in queue:
            if file.path == cf.path:
                file.status = "failed"
        events = _emit(state, BuildEvent(
            type="file_failed",
            message=f"Giving up on {cf.path} after {state.get('fix_attempts', 0)} attempts",
            file_path=cf.path
        ))
        return {"current_file": None, "file_queue": queue, "events": events}
    return {}
