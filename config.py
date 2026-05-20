"""config.py — centralised settings. All secrets via environment variables."""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    # ── Mode ──────────────────────────────────────────────────────────────────
    mode: str = Field(default="cloud", env="MODE")  # "cloud" or "local"
    local_workspace: str = Field(default="~/codeforge-workspace", env="LOCAL_WORKSPACE")

    # ── Supabase (required in cloud, ignored in local) ─────────────────────────
    supabase_url: str         = Field(default="", env="SUPABASE_URL")
    supabase_anon_key: str    = Field(default="", env="SUPABASE_ANON_KEY")
    supabase_service_key: str = Field(default="", env="SUPABASE_SERVICE_KEY")
    database_url: str         = Field(default="", env="DATABASE_URL")

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: str         = Field(default="local-dev-secret-change-me", env="JWT_SECRET")
    jwt_algorithm: str      = "HS256"
    jwt_expire_minutes: int = 1440  # 24h

    # ── Encryption key for stored API keys ────────────────────────────────────
    encryption_key: str = Field(default="", env="ENCRYPTION_KEY")

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str       = "CodeForge"
    output_dir: str     = Field(default="/data/output", env="OUTPUT_DIR")
    checkpoint_dir: str = Field(default="./data/checkpoints", env="CHECKPOINT_DIR")
    max_retries: int    = 3
    max_tokens: int     = 6000
    request_timeout: int = 120

    @property
    def is_local(self) -> bool:
        return self.mode == "local"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# ── validate cloud-only required fields ───────────────────────────────────────
if not settings.is_local:
    missing = [f for f, v in [
        ("SUPABASE_URL", settings.supabase_url),
        ("SUPABASE_SERVICE_KEY", settings.supabase_service_key),
        ("ENCRYPTION_KEY", settings.encryption_key),
    ] if not v]
    if missing:
        raise ValueError(f"Missing required env vars for cloud mode: {missing}")

# ── Provider model catalogue ──────────────────────────────────────────────────
PROVIDER_MODELS = {
    "cerebras": [
        {"label": "Qwen3-235B",  "model_id": "qwen-3-235b-a22b-instruct-2507", "context": 65536, "rpm": 1},
        {"label": "Llama3.1-8B",  "model_id": "llama3.1-8b", "context": 8192,  "rpm": 30},
    ],
    "groq": [
        {"label": "Llama3.3-70B",      "model_id": "llama-3.3-70b-versatile",        "context": 128000, "rpm": 30},
        {"label": "Llama3.1-8B fast",  "model_id": "llama-3.1-8b-instant",           "context": 128000, "rpm": 30},
        {"label": "DeepSeek-R1 70B",   "model_id": "deepseek-r1-distill-llama-70b",  "context": 128000, "rpm": 30},
        {"label": "Gemma2-9B",         "model_id": "gemma2-9b-it",                   "context": 8192,   "rpm": 30},
    ],
    "openrouter": [
        {"label": "Llama3.3-70B free",  "model_id": "meta-llama/llama-3.3-70b-instruct:free", "context": 128000, "rpm": 20},
        {"label": "Qwen3-235B free",    "model_id": "qwen/qwen3-235b-a22b:free",               "context": 65536,  "rpm": 20},
        {"label": "DeepSeek-R1 free",   "model_id": "deepseek/deepseek-r1:free",               "context": 128000, "rpm": 20},
        {"label": "Gemma3-27B free",    "model_id": "google/gemma-3-27b-it:free",              "context": 96000,  "rpm": 20},
        {"label": "Mistral-7B free",    "model_id": "mistralai/mistral-7b-instruct:free",      "context": 32768,  "rpm": 20},
    ],
}

DEFAULT_AGENT_MODELS = {
    "architect":   {"provider": "cerebras",    "model_id": "qwen-3-235b-a22b-instruct-2507"},
    "coder":       {"provider": "cerebras",    "model_id": "llama3.1-8b"},
    "reviewer":    {"provider": "groq",        "model_id": "llama-3.3-70b-versatile"},
    "fixer":       {"provider": "cerebras",    "model_id": "qwen-3-235b-a22b-instruct-2507"},
    "filemanager": {"provider": "groq",        "model_id": "llama-3.3-70b-versatile"},
}

# Legacy IDs (old UI / docs) → current provider API ids
MODEL_ALIASES = {
    "cerebras": {
        "qwen-3-235b-a22b": "qwen-3-235b-a22b-instruct-2507",
        "llama-3.1-8b": "llama3.1-8b",
        "llama3.1-8b-instant": "llama3.1-8b",  # groq-style name sent to cerebras
    },
}


def normalize_model_id(provider: str, model_id: str) -> str:
    return MODEL_ALIASES.get(provider, {}).get(model_id, model_id)
