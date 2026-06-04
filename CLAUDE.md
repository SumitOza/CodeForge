# CodeForge — Multi-Agent AI Code Builder

> Built for the Anthropic / HuggingFace AI Agents contest.

## What it does

CodeForge lets any user describe a software project in plain English and receive
a complete, working codebase — automatically planned, coded, reviewed, fixed, and
saved by a coordinated team of five AI agents.

## Agent architecture

CodeForge uses **LangGraph** to orchestrate five specialised agents in a deterministic
state machine with cyclic retry loops:

| Agent | Role | Default model |
|---|---|---|
| **Architect** | Reads the prompt, outputs a structured JSON build plan | Qwen3-235B (Cerebras) |
| **Coder** | Writes each file completely, in dependency order | Llama3.1-8B (Cerebras) |
| **Reviewer** | Checks imports, schemas, logic — outputs PASS or issues | Llama3.3-70B (Groq) |
| **Fixer** | Patches specific issues, retries up to 3× per file | Qwen3-235B (Cerebras) |
| **FileManager** | Writes approved files to disk, updates build manifest | Llama3.1-8B (Groq) |

### State machine flow

```
plan → pick_file → code → review → [pass] → save → pick_file (next)
                              ↓
                           [fail] → fix → review (retry, max 3×)
                              ↓
                      [max retries] → mark_failed → pick_file (next)
```

SQLite checkpointing allows interrupted builds to resume from the last checkpoint.

## Key technical features

- **Provider-agnostic**: each agent's model is independently selectable from
  Cerebras, Groq, or OpenRouter — all free tiers
- **Per-user encrypted API keys**: AES-256-GCM encryption, stored in Supabase,
  never exposed in plaintext
- **JWT authentication**: email + password, bcrypt hashed, 24h token expiry
- **Multi-user isolation**: each build runs in `./output/{user_id}/{session_id}/`
- **WebSocket streaming**: build events stream live to the UI
- **Persistent storage**: `/data` volume on HuggingFace Spaces persists output files
  and SQLite checkpoints across restarts

## Tech stack

| Layer | Technology |
|---|---|
| UI | Gradio 4 |
| API | FastAPI + WebSocket |
| Orchestration | LangGraph 0.2 |
| LLM providers | Cerebras · Groq · OpenRouter |
| Database | Supabase (managed Postgres) |
| Auth | JWT (python-jose) + bcrypt |
| Encryption | AES-256-GCM (cryptography) |
| Deploy | Docker → HuggingFace Spaces |

## Setup

### 1. Clone and configure

```bash
git clone https://huggingface.co/spaces/SumitOza/codeforge
cd codeforge
cp .env.example .env
# Fill in .env with your Supabase + secret values
```

### 2. Set up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Open the SQL editor and run `supabase_schema.sql`
3. Copy your project URL, anon key, and service role key into `.env`

### 3. Generate secrets

```bash
# Encryption key (32-byte AES key)
python -c "from crypto import generate_encryption_key; print(generate_encryption_key())"

# JWT secret
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Run locally

```bash
pip install -r requirements.txt
python -m ui.app
# Opens at http://localhost:7860
```

### 5. Deploy to HuggingFace Spaces

```bash
# In your HF Space settings, add all .env values as Space Secrets
# Then push — Docker build runs automatically
git add . && git commit -m "deploy" && git push
```

## Usage

1. Register or log in
2. Go to **API Keys** and add at least one provider key (Cerebras / Groq / OpenRouter — all free)
3. Go to **Build**, describe your project, optionally tune which model each agent uses
4. Click **Build project** — watch it plan, code, review, fix, and save
5. Check **Build history** for past sessions

## Project structure

```
codeforge/
├── main.py              FastAPI app
├── config.py            Settings + model catalogue
├── models.py            Pydantic schemas
├── database.py          Supabase operations
├── auth.py              JWT + bcrypt
├── crypto.py            AES-256 key encryption
├── agents/
│   ├── base.py          BaseAgent with retry
│   └── prompts.py       System prompts for all agents
├── graph/
│   ├── state.py         LangGraph TypedDict state
│   ├── nodes.py         Node functions (plan/code/review/fix/save)
│   └── builder.py       Graph assembly + SQLite checkpointer
├── providers/
│   └── factory.py       Provider-agnostic LLM factory
├── routers/
│   ├── auth_router.py   Register · Login · Profile
│   ├── keys_router.py   API key CRUD
│   └── build_router.py  Build start · status · WebSocket
├── ui/
│   └── app.py           Gradio web interface
├── supabase_schema.sql  Database setup
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Author

Built by **Sumit Oza** — AI Systems Architect specialising in agentic orchestration,
LangGraph state machines, and production-grade autonomous workflows.

- GitHub: [github.com/SumitOza](https://github.com/SumitOza)
- HuggingFace: [huggingface.co/SumitOza](https://huggingface.co/SumitOza)
- LinkedIn: [linkedin.com/in/sumitoza](https://linkedin.com/in/sumitoza)
