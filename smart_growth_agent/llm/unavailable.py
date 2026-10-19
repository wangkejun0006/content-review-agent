from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from smart_growth_agent.llm.types import LLMRequest, LLMResult

T = TypeVar("T", bound=BaseModel)


class UnavailableLLMGateway:
    async def generate(self, request: LLMRequest, response_model: type[T]) -> LLMResult[T]:
        del request, response_model
        raise RuntimeError(
            "LLM is not configured; set SMART_GROWTH_OPENAI_API_KEY and "
            "SMART_GROWTH_OPENAI_MODEL"
        )
