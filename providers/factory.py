"""providers/factory.py — build LangChain LLM from provider + model choice + user API keys."""
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from config import settings, PROVIDER_MODELS
from typing import Optional


def build_llm(provider: str, model_id: str, api_key: Optional[str] = None, temperature: float = 0.2):
    """
    Return a LangChain chat model for the given provider.
    api_key: user's stored key (decrypted). Falls back to env vars if None.
    """
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
