from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from smart_growth_agent.schemas.document_parse import DocumentParseReport
from smart_growth_agent.schemas.ingestion import IngestionAnalysis


class PlatformRuleAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,199}$")
    category: Literal["content_compliance", "ai_content", "health_claim", "recommendation"]
    rule_text: str = Field(min_length=1)
    severity: Literal["blocker", "warning", "information"]
    confidence: float = Field(ge=0, le=1)
    source_excerpt: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


class PlatformRuleImportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_key: str
    payload: dict
    search_text: str
    confidence: float
    source_excerpt: str
    warnings: list[str]
    dedup: IngestionAnalysis | None = None
    parse_reports: list[DocumentParseReport] = Field(default_factory=list)


class PlatformRuleImportContext(BaseModel):
    source_url: HttpUrl
    verified_at: datetime
