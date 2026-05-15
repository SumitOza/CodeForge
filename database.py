"""database.py — Supabase client and all database operations."""
from supabase import create_client, Client
from config import settings
from models import UserProfile, ApiKeyResponse, BuildSession
from crypto import encrypt_key, decrypt_key, preview_key
import uuid, time
from typing import Optional, List


def get_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


# ── Users ─────────────────────────────────────────────────────────────────────
async def create_user(email: str, hashed_password: str, full_name: str) -> dict:
    db = get_client()
    user_id = str(uuid.uuid4())
    data = {
        "id": user_id,
        "email": email,
        "hashed_password": hashed_password,
        "full_name": full_name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_builds": 0,
        "total_tokens_used": 0,
    }
    result = db.table("users").insert(data).execute()
    return result.data[0]


async def get_user_by_email(email: str) -> Optional[dict]:
    db = get_client()
    result = db.table("users").select("*").eq("email", email).execute()
    return result.data[0] if result.data else None


async def get_user_by_id(user_id: str) -> Optional[dict]:
    db = get_client()
    result = db.table("users").select("*").eq("id", user_id).execute()
    return result.data[0] if result.data else None


async def increment_user_stats(user_id: str, tokens: int = 0):
    db = get_client()
    user = await get_user_by_id(user_id)
    if user:
        db.table("users").update({
            "total_builds": user["total_builds"] + 1,
            "total_tokens_used": user["total_tokens_used"] + tokens,
        }).eq("id", user_id).execute()


# ── API Keys ──────────────────────────────────────────────────────────────────
async def save_api_key(user_id: str, provider: str, key_value: str) -> ApiKeyResponse:
    db = get_client()
    key_id = str(uuid.uuid4())
    encrypted = encrypt_key(key_value)
    preview = preview_key(key_value)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Upsert — one key per provider per user
    db.table("api_keys").upsert({
        "id": key_id,
        "user_id": user_id,
        "provider": provider,
        "encrypted_key": encrypted,
        "key_preview": preview,
        "created_at": now,
    }, on_conflict="user_id,provider").execute()

    return ApiKeyResponse(id=key_id, provider=provider, key_preview=preview, created_at=now)


async def get_api_keys(user_id: str) -> List[ApiKeyResponse]:
    db = get_client()
    result = db.table("api_keys").select("id,provider,key_preview,created_at").eq("user_id", user_id).execute()
    return [ApiKeyResponse(**row) for row in result.data]


async def get_decrypted_key(user_id: str, provider: str) -> Optional[str]:
    db = get_client()
    result = db.table("api_keys").select("encrypted_key").eq("user_id", user_id).eq("provider", provider).execute()
    if not result.data:
        return None
    return decrypt_key(result.data[0]["encrypted_key"])


async def delete_api_key(user_id: str, provider: str):
    db = get_client()
    db.table("api_keys").delete().eq("user_id", user_id).eq("provider", provider).execute()


# ── Build sessions ────────────────────────────────────────────────────────────
async def create_session(session: BuildSession):
    db = get_client()
    db.table("build_sessions").insert({
        "id": session.session_id,
        "user_id": session.user_id,
        "prompt": session.prompt,
        "status": session.status,
        "plan": session.plan.model_dump() if session.plan else None,
        "files_done": session.files_done,
        "files_failed": session.files_failed,
        "total_tokens": session.total_tokens,
        "started_at": session.started_at,
    }).execute()


async def update_session(session_id: str, updates: dict):
    db = get_client()
    db.table("build_sessions").update(updates).eq("id", session_id).execute()


async def get_session(session_id: str, user_id: str) -> Optional[dict]:
    db = get_client()
    result = db.table("build_sessions").select("*").eq("id", session_id).eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


async def list_sessions(user_id: str, limit: int = 20) -> List[dict]:
    db = get_client()
    result = (db.table("build_sessions")
              .select("id,prompt,status,started_at,total_tokens,files_done")
              .eq("user_id", user_id)
              .order("started_at", desc=True)
              .limit(limit)
              .execute())
    return result.data


# ── Usage logs ────────────────────────────────────────────────────────────────
async def log_token_usage(user_id: str, session_id: str, agent: str, provider: str, model_id: str, tokens: int):
    db = get_client()
    db.table("usage_logs").insert({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "session_id": session_id,
        "agent": agent,
        "provider": provider,
        "model_id": model_id,
        "tokens": tokens,
        "logged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }).execute()
