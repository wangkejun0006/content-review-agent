from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from smart_growth_agent.schemas.document_parse import DocumentParseReport
from smart_growth_agent.schemas.ingestion import IngestionAnalysis

EvidenceDocumentType = Literal[
    "product_specification",
    "test_report",
    "material_certificate",
    "brand_approval",
    "other",
]


class EvidenceImportAIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    document_type: EvidenceDocumentType
    source_summary: str = Field(min_length=1)
    relevant_excerpts: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class EvidenceImportDraft(EvidenceImportAIOutput):
    source_uri: str = Field(min_length=1)
    content: str = Field(min_length=1)
    dedup: IngestionAnalysis | None = None
    parse_reports: list[DocumentParseReport] = Field(default_factory=list)
