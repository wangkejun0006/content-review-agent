from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from smart_growth_agent.llm.types import LLMRequest, LLMResult

T = TypeVar("T", bound=BaseModel)


class LLMGateway(Protocol):
    async def generate(self, request: LLMRequest, response_model: type[T]) -> LLMResult[T]: ...
