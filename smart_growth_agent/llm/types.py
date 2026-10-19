from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    brand_id: uuid.UUID
    purpose: str = Field(min_length=1, max_length=100)
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    prompt_revision_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None


class LLMUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMResult[T: BaseModel](BaseModel):
    value: T
    provider: str
    model: str
    usage: LLMUsage
    latency_ms: int
    provider_request_id: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def telemetry_logged(self) -> bool:
        """Whether the gateway already persisted this paid provider call.

        Managed providers write telemetry immediately after receiving a valid typed
        response.  Business services can then avoid duplicate rows while still
        retaining their fallback logging for fake and direct gateways.
        """

        return self.raw_metadata.get("telemetry_logged") is True
