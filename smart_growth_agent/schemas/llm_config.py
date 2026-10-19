from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr

MANAGED_LLM_PURPOSES = (
    "product_registry_import",
    "evidence_registry_import",
    "platform_rule_import",
    "xhs_product_context",
    "xhs_strategy",
    "xhs_writer",
    "xhs_compliance_semantic",
    "xhs_scoring",
    "xhs_feedback",
)


class LLMProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    provider_type: Literal["openai_compatible"] = "openai_compatible"
    base_url: HttpUrl
    api_key: SecretStr = Field(min_length=1)
    default_model: str = Field(min_length=1, max_length=200)


class LLMProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: HttpUrl | None = None
    api_key: SecretStr | None = None
    default_model: str | None = Field(default=None, min_length=1, max_length=200)
    is_enabled: bool | None = None


class LLMProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    provider_type: str
    base_url: str
    default_model: str
    is_enabled: bool
    has_api_key: bool = True
    last_tested_at: datetime | None
    last_test_status: str | None
    last_test_message: str | None
    created_at: datetime
    updated_at: datetime


class AgentLLMBindingUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_config_id: uuid.UUID
    model_override: str | None = Field(default=None, max_length=200)


class AgentLLMBindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purpose: str
    provider_config_id: uuid.UUID
    model_override: str | None


class LLMConfigurationStatus(BaseModel):
    credential_storage_ready: bool
    runtime_mode: str
    supported_purposes: tuple[str, ...] = MANAGED_LLM_PURPOSES


class LLMProviderTestOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    message: str


class LLMUsageTotals(BaseModel):
    calls: int
    successful_calls: int
    failed_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    unreported_token_calls: int
    average_latency_ms: int


class LLMUsageProviderBreakdown(LLMUsageTotals):
    provider: str
    model: str


class LLMUsagePurposeBreakdown(LLMUsageTotals):
    purpose: str


class LLMUsageReport(BaseModel):
    requested_days: int | None
    period_start: datetime | None
    period_end: datetime
    totals: LLMUsageTotals
    by_provider: list[LLMUsageProviderBreakdown]
    by_purpose: list[LLMUsagePurposeBreakdown]
