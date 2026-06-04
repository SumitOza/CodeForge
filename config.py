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
#
# CEREBRAS  (https://cloud.cerebras.ai)
#   Free tier: 5 RPM / 150 RPH / 2,400 RPD | 30K TPM / 1M TPH / 1M TPD
#   Context: 65,536 for gpt-oss-120b; 64,000 for zai-glm-4.7
#   Only TWO models available on personal/free tier as of June 2026:
#     gpt-oss-120b  — Production, 65,536 ctx
#     zai-glm-4.7   — Preview,    64,000 ctx
#   All Llama, Qwen3 models removed from free personal tier.
#
# GROQ  (https://console.groq.com)
#   Free tier: 30 RPM / 6,000 TPM / 1,000 RPD (per model)
#   gemma2-9b-it → deprecated Aug 2025 (replaced by llama-3.1-8b-instant)
#   llama-3.1-8b-instant STILL valid production model
#   deepseek-r1-distill-llama-70b → deprecated Sep 2025
#   llama-4-maverick → deprecated Feb 2026 (replaced by openai/gpt-oss-120b)
#   kimi-k2-instruct → deprecated Mar 2026 (replaced by openai/gpt-oss-120b)
#   Current production models: llama-3.1-8b-instant, llama-3.3-70b-versatile,
#                               openai/gpt-oss-120b, openai/gpt-oss-20b
#   Current preview models:     qwen/qwen3-32b, meta-llama/llama-4-scout-17b-16e-instruct
#
# GOOGLE AI (https://aistudio.google.com)
#   Free tier (post Dec 2025 cuts, stable as of June 2026):
#     gemini-2.5-flash-lite :  15 RPM / 1,000 RPD / 250K TPM  ← best for Coder
#     gemini-2.5-flash      :  10 RPM /   250 RPD / 250K TPM  ← good for Reviewer
#     gemini-2.5-pro        :   5 RPM /   100 RPD / 250K TPM  ← use sparingly
#   Retired Feb/Mar 2026: gemini-2.0-flash
#   Removed Dec 2025:     gemini-1.5-flash, gemini-1.5-flash-8b
#   Context: 1,048,576 tokens for all 2.5 models
#
# OPENROUTER  (https://openrouter.ai)
#   Free tier: 20 RPM / 200 RPD per model (no credit card needed)
#   google/gemma-3-27b-it:free → endpoint 404 (no longer available free)
#   deepseek/deepseek-r1:free  → endpoint 404 (no longer available free)
#   qwen/qwen3-235b-a22b:free  → endpoint 404 (no longer available free)
#   meta-llama/llama-3.3-70b-instruct:free → still available (rate-limited upstream)
#   New strong free options: nvidia/nemotron-3-super-120b-a12b:free,
#                            google/gemma-4-31b-it:free, qwen/qwen3-coder:free,
#                            openai/gpt-oss-120b:free, moonshotai/kimi-k2.6:free

PROVIDER_MODELS = {
    "cerebras": [
        # Only two models on personal/free tier as of June 2026
        # Production: best choice for architect, reviewer, fixer
        {"label": "GPT-OSS-120B",  "model_id": "gpt-oss-120b",  "context": 65536, "rpm": 5},
        # Preview: faster/cheaper, good for coder, filemanager
        {"label": "ZAI-GLM-4.7",   "model_id": "zai-glm-4.7",   "context": 64000, "rpm": 5},
    ],
    "google": [
        {"label": "Gemini 2.5 Flash-Lite",  "model_id": "gemini-2.5-flash-lite",  "context": 1048576, "rpm": 15},  # 1000 RPD
        {"label": "Gemini 2.5 Flash",       "model_id": "gemini-2.5-flash",       "context": 1048576, "rpm": 10},  # 250 RPD
    ],
    "groq": [
        # Production — recommended
        {"label": "Llama3.3-70B",       "model_id": "llama-3.3-70b-versatile",                   "context": 128000, "rpm": 30},
        {"label": "Llama3.1-8B fast",   "model_id": "llama-3.1-8b-instant",                      "context": 128000, "rpm": 30},
        {"label": "GPT-OSS-120B",       "model_id": "openai/gpt-oss-120b",                        "context": 131072, "rpm": 30},
        {"label": "GPT-OSS-20B",        "model_id": "openai/gpt-oss-20b",                         "context": 131072, "rpm": 30},
        # Preview — good quality but may change
        {"label": "Qwen3-32B preview",  "model_id": "qwen/qwen3-32b",                            "context": 131072, "rpm": 30},
        {"label": "Llama4 Scout preview","model_id": "meta-llama/llama-4-scout-17b-16e-instruct", "context": 131072, "rpm": 30},
    ],
    "openrouter": [
        # Most reliable free models as of June 2026
        {"label": "Llama3.3-70B free",      "model_id": "meta-llama/llama-3.3-70b-instruct:free",     "context": 131072, "rpm": 20},
        {"label": "GPT-OSS-120B free",      "model_id": "openai/gpt-oss-120b:free",                   "context": 131072, "rpm": 20},
        {"label": "Nemotron-Super-120B free","model_id": "nvidia/nemotron-3-super-120b-a12b:free",     "context": 1000000,"rpm": 20},
        {"label": "Gemma4-31B free",         "model_id": "google/gemma-4-31b-it:free",                "context": 262144, "rpm": 20},
        {"label": "Qwen3-Coder free",        "model_id": "qwen/qwen3-coder:free",                     "context": 1000000,"rpm": 20},
        {"label": "Kimi-K2.6 free",          "model_id": "moonshotai/kimi-k2.6:free",                 "context": 262144, "rpm": 20},
    ],
}

DEFAULT_AGENT_MODELS = {
    # gpt-oss-120b is the stronger production model — use for planning, reviewing, fixing
    "architect":   {"provider": "cerebras", "model_id": "gpt-oss-120b"},
    # gemini-2.5-flash is fast — good enough for writing/saving individual files
    "coder":    {"provider": "google", "model_id": "gemini-2.5-flash"},
    # Groq has higher RPM (30 vs 5) — better for reviewer which runs once per file
    "reviewer":    {"provider": "groq",     "model_id": "llama-3.3-70b-versatile"},
    "fixer": {"provider": "google", "model_id": "gemini-2.5-flash-lite"},
    "filemanager": {"provider": "groq",     "model_id": "llama-3.1-8b-instant"},
}

# Legacy / deprecated IDs → current provider API ids
MODEL_ALIASES = {
    "google": {
        "gemini-2.5-flash-preview":          "gemini-2.5-flash",
        "gemini-2.5-flash-lite-preview-06-17": "gemini-2.5-flash-lite",
    },  
    "cerebras": {
        # All previously available Cerebras models → nearest current equivalent
        # Qwen3 models → gpt-oss-120b (both were large reasoning models)
        "qwen-3-235b-a22b":                  "gpt-oss-120b",
        "qwen-3-235b-a22b-instruct-2507":    "gpt-oss-120b",
        "qwen-3-32b":                        "gpt-oss-120b",
        # Llama models → zai-glm-4.7 (both were smaller/faster models)
        "llama3.1-8b":                       "zai-glm-4.7",
        "llama-3.1-8b":                      "zai-glm-4.7",
        "llama3.1-8b-instant":               "zai-glm-4.7",
        "llama-3.1-8b-instant":              "zai-glm-4.7",
        "llama-3.3-70b":                     "gpt-oss-120b",
        "llama3.3-70b":                      "gpt-oss-120b",
        # zai-glm-4.7 also available under its Z.ai branding
        "zai-org/glm-4.7":                   "zai-glm-4.7",
    },
    "groq": {
        # Deprecated → replacement
        "gemma2-9b-it":                          "llama-3.1-8b-instant",
        "deepseek-r1-distill-llama-70b":         "openai/gpt-oss-120b",
        "meta-llama/llama-4-maverick-17b-128e-instruct": "openai/gpt-oss-120b",
        "moonshotai/kimi-k2-instruct":           "openai/gpt-oss-120b",
        "moonshotai/kimi-k2-instruct-0905":      "openai/gpt-oss-120b",
        "qwen-qwq-32b":                          "qwen/qwen3-32b",
        "mistral-saba-24b":                      "qwen/qwen3-32b",
    },
    "openrouter": {
        # Old free models that now 404 → best current replacements
        "google/gemma-3-27b-it:free":            "google/gemma-4-31b-it:free",
        "deepseek/deepseek-r1:free":             "openai/gpt-oss-120b:free",
        "qwen/qwen3-235b-a22b:free":             "nvidia/nemotron-3-super-120b-a12b:free",
        "mistralai/mistral-7b-instruct:free":    "meta-llama/llama-3.3-70b-instruct:free",
        # Old llama format without :free suffix
        "meta-llama/llama-3.3-70b-instruct":     "meta-llama/llama-3.3-70b-instruct:free",
    },
}


def normalize_model_id(provider: str, model_id: str) -> str:
    return MODEL_ALIASES.get(provider, {}).get(model_id, model_id)
