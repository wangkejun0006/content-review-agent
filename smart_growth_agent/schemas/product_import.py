from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_growth_agent.schemas.document_parse import DocumentParseReport
from smart_growth_agent.schemas.ingestion import IngestionAnalysis
from smart_growth_agent.schemas.registry import ProductPayload


class ProductSourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ProductImportAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,199}$")
    payload: ProductPayload
    search_text: str = Field(min_length=1)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_summaries: list[ProductSourceSummary] = Field(default_factory=list)

    @field_validator("field_confidence")
    @classmethod
    def validate_confidence(cls, value: dict[str, float]) -> dict[str, float]:
        if any(score < 0 or score > 1 for score in value.values()):
            raise ValueError("field confidence values must be between 0 and 1")
        return value


class ProductImportDraft(ProductImportAIOutput):
    dedup: IngestionAnalysis | None = None
    parse_reports: list[DocumentParseReport] = Field(default_factory=list)


class ExtractedProductSource(BaseModel):
    name: str
    media_type: str
    text: str
