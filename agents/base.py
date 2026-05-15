"""agents/base.py — base agent wrapping a LangChain LLM with retry and token counting."""
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from models import TokenUsage
from typing import Optional
import time, asyncio


class BaseAgent:
    def __init__(self, name: str, llm: BaseChatModel, system_prompt: str):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.last_usage = TokenUsage(agent=name, provider="unknown", model_id="unknown")

    async def call(self, user_message: str, max_retries: int = 3) -> str:
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message),
        ]
        for attempt in range(max_retries):
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.llm.invoke(messages)
                )
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    self.last_usage.input_tokens  = response.usage_metadata.get("input_tokens", 0)
                    self.last_usage.output_tokens = response.usage_metadata.get("output_tokens", 0)
                return response.content

            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Agent {self.name} failed after {max_retries} attempts: {e}")
                wait = 2 ** attempt
                await asyncio.sleep(wait)

        return ""
