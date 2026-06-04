"""agents/base.py — base agent with provider-aware 429 retry.

Retry strategy
--------------
There are two distinct 429 scenarios:

1. RPM throttle (Groq, OpenRouter, Cerebras)
   - Clears in seconds, not minutes
   - retryDelay hint is usually absent or very short (< 5 s)
   - Strategy: short fixed wait (RPM_BASE_WAIT), capped exponential, max 30 s

2. Daily quota exhaustion (Google free tier, OpenRouter per-model cap)
   - retryDelay hint present and meaningful (10–60 s range)
   - Strategy: honour the hint exactly (+ 2 s margin); exponential fallback
     also reasonable since daily quota won't recover mid-build anyway

Distinguishing rule
-------------------
If a retryDelay hint > QUOTA_THRESHOLD_SECS is present → daily quota path.
Otherwise → RPM throttle path.
"""
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from models import TokenUsage
import asyncio, re

# ── Tuning constants ──────────────────────────────────────────────────────────

# RPM throttle: initial wait and hard cap
RPM_BASE_WAIT  = 5    # seconds for first retry
RPM_MAX_WAIT   = 30   # never wait longer than this for an RPM error

# Daily quota: base wait when no retryDelay hint is in the response
QUOTA_BASE_WAIT = 20  # seconds; doubles per attempt

# If a retryDelay hint exceeds this, treat as daily quota (not RPM)
QUOTA_THRESHOLD_SECS = 8


def _parse_retry_after(exc: Exception) -> float | None:
    """
    Extract a retry-delay from the exception message.
    Handles:
      'retryDelay': '16s'         (Google JSON body)
      'Please retry in 16.514s'   (Google plain-text)
      'Rate limit ... retry after 2s'  (some providers)
    Returns seconds as float, or None if not found.
    """
    msg = str(exc)

    # 'retryDelay': '16s'  or  retryDelay: 16s
    m = re.search(r"retryDelay['\"]?\s*[,:]\s*['\"]?(\d+(?:\.\d+)?)\s*s", msg, re.I)
    if m:
        return float(m.group(1))

    # 'Please retry in 16.514461022s'
    m = re.search(r"retry in\s+(\d+(?:\.\d+)?)s", msg, re.I)
    if m:
        return float(m.group(1))

    # 'retry after 2s' / 'retry after: 2'
    m = re.search(r"retry after[:\s]+(\d+(?:\.\d+)?)\s*s?", msg, re.I)
    if m:
        return float(m.group(1))

    return None


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "429", "resource_exhausted", "rate limit", "ratelimit",
        "quota", "too many requests", "ratelimitexceeded",
    ))


class BaseAgent:
    def __init__(self, name: str, llm: BaseChatModel, system_prompt: str):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.last_usage = TokenUsage(agent=name, provider="unknown", model_id="unknown")

    async def call(self, user_message: str, max_retries: int = 5) -> str:
        """
        Invoke the LLM with provider-aware 429 retry logic.

        - RPM throttle (no/short retryDelay): wait RPM_BASE_WAIT * 2^attempt,
          capped at RPM_MAX_WAIT. Typically clears in < 30 s.
        - Daily quota (retryDelay > QUOTA_THRESHOLD_SECS): wait exactly that
          long (+ 2 s margin). If no hint: QUOTA_BASE_WAIT * 2^attempt.
        - Other errors: standard 2^attempt back-off, max 16 s.
        """
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message),
        ]

        last_exc = None

        for attempt in range(max_retries):
            try:
                response = await self.llm.ainvoke(messages)
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    self.last_usage.input_tokens  = response.usage_metadata.get("input_tokens", 0)
                    self.last_usage.output_tokens = response.usage_metadata.get("output_tokens", 0)
                return response.content

            except Exception as exc:
                last_exc = exc

                if attempt == max_retries - 1:
                    break  # exhausted retries

                if _is_quota_error(exc):
                    suggested = _parse_retry_after(exc)

                    if suggested is not None and suggested > QUOTA_THRESHOLD_SECS:
                        # Daily quota: provider told us exactly how long to wait
                        wait = suggested + 2  # safety margin
                        print(
                            f"[{self.name}] daily quota 429 (attempt {attempt + 1}): "
                            f"waiting {wait:.1f}s as instructed…",
                            flush=True,
                        )
                    else:
                        # RPM throttle: short hint or no hint — cap at RPM_MAX_WAIT
                        wait = min(RPM_BASE_WAIT * (2 ** attempt), RPM_MAX_WAIT)
                        hint_str = f"{suggested:.1f}s hint" if suggested is not None else "no hint"
                        print(
                            f"[{self.name}] RPM 429 (attempt {attempt + 1}, {hint_str}): "
                            f"waiting {wait:.1f}s…",
                            flush=True,
                        )

                    await asyncio.sleep(wait)

                else:
                    # Generic transient error — short exponential back-off
                    wait = min(2 ** attempt, 16)
                    print(
                        f"[{self.name}] error (attempt {attempt + 1}): {exc!r} "
                        f"— retrying in {wait}s",
                        flush=True,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"Agent {self.name} failed after {max_retries} attempts: {last_exc}"
        )