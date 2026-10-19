from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DuplicateMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_type: Literal["exact_source", "same_sku", "same_stable_key", "similar_text"]
    entity_type: str
    item_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    evidence_document_id: uuid.UUID | None = None
    label: str
    similarity: float = Field(ge=0, le=1)
    recommended_action: Literal["cancel", "new_revision", "review"]


class IngestionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingestion_id: uuid.UUID
    duplicate_status: Literal["none", "possible", "exact"]
    matches: list[DuplicateMatch] = Field(default_factory=list)
    recommended_action: Literal["new_item", "new_revision", "cancel", "review"]
    llm_skipped: bool = False
    message: str


class IngestionResolve(BaseModel):
    decision: Literal["new_item", "new_revision", "independent", "cancel"]
    decision_reason: str = ""
    resulting_item_id: uuid.UUID | None = None
    resulting_revision_id: uuid.UUID | None = None
    resulting_evidence_document_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> IngestionResolve:
        if self.decision == "independent" and not self.decision_reason.strip():
            raise ValueError("independent duplicate decision requires a reason")
        return self


class IngestionRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    ingestion_type: str
    source_uri: str | None
    source_checksum: str
    duplicate_status: str
    matches: list[dict]
    recommended_action: str
    status: str
    decision: str | None
    decision_reason: str | None
    resulting_item_id: uuid.UUID | None
    resulting_revision_id: uuid.UUID | None
    resulting_evidence_document_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    resolved_at: datetime | None
