"""database_local.py — pure SQLite, no network, no auth. Used when MODE=local."""
import sqlite3, json, uuid, time
from pathlib import Path
from typing import Optional, List
from models import ApiKeyResponse, BuildSession
from crypto import encrypt_key, decrypt_key, preview_key
from config import settings

_DB = Path(settings.local_workspace).expanduser() / ".codeforge.db"

LOCAL_USER = {
    "id": "local-user",
    "email": "local@codeforge",
    "full_name": "Local User",
    "created_at": "2024-01-01T00:00:00Z",
    "hashed_password": "",
    "total_builds": 0,
    "total_tokens_used": 0,
}

def _conn():
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    _init(c)
    return c

def _init(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY, user_id TEXT, provider TEXT,
        encrypted_key TEXT, key_preview TEXT, created_at TEXT,
        UNIQUE(user_id, provider)
    );
    CREATE TABLE IF NOT EXISTS build_sessions (
        id TEXT PRIMARY KEY, user_id TEXT, prompt TEXT,
        status TEXT DEFAULT 'planning', plan TEXT,
        files_done TEXT DEFAULT '[]', files_failed TEXT DEFAULT '[]',
        total_tokens INT DEFAULT 0, started_at REAL, completed_at REAL
    );
    """)
    c.commit()

# ── users (always the same local user) ───────────────────────────────────────
async def get_user_by_id(uid): return LOCAL_USER
async def get_user_by_email(email): return LOCAL_USER
async def create_user(email, hashed_password, full_name): return LOCAL_USER
async def increment_user_stats(user_id, tokens=0): pass

# ── api keys ──────────────────────────────────────────────────────────────────
async def save_api_key(user_id: str, provider: str, key_value: str) -> ApiKeyResponse:
    c = _conn()
    kid, preview, now = str(uuid.uuid4()), preview_key(key_value), time.strftime("%Y-%m-%dT%H:%M:%SZ")
    c.execute("INSERT OR REPLACE INTO api_keys VALUES (?,?,?,?,?,?)",
              (kid, user_id, provider, encrypt_key(key_value), preview, now))
    c.commit()
    return ApiKeyResponse(id=kid, provider=provider, key_preview=preview, created_at=now)

async def get_api_keys(user_id: str) -> List[ApiKeyResponse]:
    rows = _conn().execute("SELECT * FROM api_keys WHERE user_id=?", (user_id,)).fetchall()
    return [ApiKeyResponse(id=r["id"], provider=r["provider"],
                           key_preview=r["key_preview"], created_at=r["created_at"]) for r in rows]

async def get_decrypted_key(user_id: str, provider: str) -> Optional[str]:
    r = _conn().execute("SELECT encrypted_key FROM api_keys WHERE user_id=? AND provider=?",
                        (user_id, provider)).fetchone()
    return decrypt_key(r["encrypted_key"]) if r else None

async def delete_api_key(user_id: str, provider: str):
    c = _conn(); c.execute("DELETE FROM api_keys WHERE user_id=? AND provider=?",
                           (user_id, provider)); c.commit()

# ── build sessions ────────────────────────────────────────────────────────────
async def create_session(session: BuildSession):
    c = _conn()
    c.execute("INSERT OR IGNORE INTO build_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
              (session.session_id, session.user_id, session.prompt, session.status,
               None, "[]", "[]", 0, session.started_at, None))
    c.commit()

async def update_session(session_id: str, updates: dict):
    c = _conn()
    serialized = {k: json.dumps(v) if isinstance(v, list) else v for k, v in updates.items()}
    cols = ", ".join(f"{k}=?" for k in serialized)
    c.execute(f"UPDATE build_sessions SET {cols} WHERE id=?", list(serialized.values()) + [session_id])
    c.commit()

async def get_session(session_id: str, user_id: str) -> Optional[dict]:
    r = _conn().execute("SELECT * FROM build_sessions WHERE id=? AND user_id=?",
                        (session_id, user_id)).fetchone()
    if not r: return None
    d = dict(r)
    d["files_done"]   = json.loads(d.get("files_done") or "[]")
    d["files_failed"] = json.loads(d.get("files_failed") or "[]")
    return d

async def list_sessions(user_id: str, limit: int = 20) -> List[dict]:
    rows = _conn().execute(
        "SELECT id,prompt,status,started_at,total_tokens,files_done "
        "FROM build_sessions WHERE user_id=? ORDER BY started_at DESC LIMIT ?",
        (user_id, limit)).fetchall()
    result = []
    for r in rows:
        d = dict(r); d["files_done"] = json.loads(d.get("files_done") or "[]")
        result.append(d)
    return result

async def log_token_usage(*args, **kwargs): pass