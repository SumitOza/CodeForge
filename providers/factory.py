"""providers/factory.py — build LangChain LLM from provider + model choice + user API keys.

Rate limits (free tier, June 2026):
  Cerebras   : 5 RPM / 30K TPM  — use CEREBRAS_CALL_DELAY between consecutive calls
  Groq       : 30 RPM / 6K TPM
  OpenRouter : 20 RPM / 200 RPD per model
"""
import asyncio
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from config import settings, PROVIDER_MODELS, normalize_model_id
from typing import Optional

# Cerebras free tier: 5 RPM = 1 request per 12 s.
# Nodes that call Cerebras back-to-back (code → fix → code …) must await this.
CEREBRAS_CALL_DELAY = 12.0  # seconds


async def cerebras_rate_limit_sleep():
    """Await between consecutive Cerebras calls to stay under 5 RPM."""
    await asyncio.sleep(CEREBRAS_CALL_DELAY)


def build_llm(provider: str, model_id: str, api_key: Optional[str] = None, temperature: float = 0.2):
    """
    Return a LangChain chat model for the given provider.
    api_key: user's stored key (decrypted). Falls back to env vars if None.

    Cerebras serves ALL its models (gpt-oss-120b, zai-glm-4.7) via an
    OpenAI-compatible endpoint, so ChatOpenAI works for both.
    """
    model_id = normalize_model_id(provider, model_id)

    if provider == "cerebras":
        key = api_key or settings.__dict__.get("cerebras_api_key")
        return ChatOpenAI(
            model=model_id,
            api_key=key,
            base_url="https://api.cerebras.ai/v1",
            temperature=temperature,
            max_tokens=settings.max_tokens,
            timeout=settings.request_timeout,
        )

    elif provider == "groq":
        key = api_key or settings.__dict__.get("groq_api_key")
        return ChatGroq(
            model=model_id,
            api_key=key,
            temperature=temperature,
            max_tokens=settings.max_tokens,
            timeout=settings.request_timeout,
        )

    elif provider == "openrouter":
        key = api_key or settings.__dict__.get("openrouter_api_key")
        return ChatOpenAI(
            model=model_id,
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            temperature=temperature,
            max_tokens=settings.max_tokens,
            timeout=settings.request_timeout,
            default_headers={
                "HTTP-Referer": "https://huggingface.co/spaces/SumitOza/codeforge",
                "X-Title": "CodeForge",
            },
        )

    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_available_providers(user_keys: dict) -> list:
    """Return list of providers the user has keys for."""
    available = []
    for provider, models in PROVIDER_MODELS.items():
        if user_keys.get(provider):
            available.append({
                "provider": provider,
                "models": models,
                "has_key": True,
            })
    return available


def get_provider_for_agent(agent_models: dict, agent_name: str) -> str:
    """Helper: return the provider name configured for a given agent."""
    return agent_models.get(agent_name, {}).get("provider", "cerebras")
