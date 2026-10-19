from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_growth_agent.domain.enums import AttributionStrength, FeedbackRunStatus


class FeedbackRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_ids: list[uuid.UUID] = Field(min_length=1)
    commerce_snapshot_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_ids(self) -> FeedbackRunCreate:
        if len(set(self.publication_ids)) != len(self.publication_ids):
            raise ValueError("publication_ids must be unique")
        if len(set(self.commerce_snapshot_ids)) != len(self.commerce_snapshot_ids):
            raise ValueError("commerce_snapshot_ids must be unique")
        return self


class FeedbackRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    thread_id: str
    status: FeedbackRunStatus
    publication_ids: list[uuid.UUID]
    metric_snapshot_ids: list[uuid.UUID]
    commerce_snapshot_ids: list[uuid.UUID]
    attribution_evidence_ids: list[uuid.UUID]
    prompt_revision_id: uuid.UUID | None
    input_checksum: str | None
    error: dict | None
    recommendation_id: uuid.UUID | None = None
    strategy_insight_revision_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    created_at: datetime


class FeedbackObservation(BaseModel):
    statement: str = Field(min_length=1)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)
    attribution_scope: AttributionStrength = AttributionStrength.CORRELATIVE
    confidence: float = Field(ge=0, le=1)


class FeedbackHypothesis(BaseModel):
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    attribution_scope: AttributionStrength = AttributionStrength.CORRELATIVE
    confidence: float = Field(ge=0, le=1)


class FeedbackAction(BaseModel):
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    expected_signal: str = Field(min_length=1)


class FeedbackOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    observations: list[FeedbackObservation] = Field(min_length=1)
    hypotheses: list[FeedbackHypothesis] = Field(default_factory=list)
    actions: list[FeedbackAction] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    attribution_scope: AttributionStrength
    limitations: list[str] = Field(default_factory=list)


class FeedbackRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    feedback_run_id: uuid.UUID
    recommendation: FeedbackOutput
    confidence: Decimal
    attribution_scope: AttributionStrength
    input_checksum: str
    strategy_insight_revision_id: uuid.UUID | None
    created_at: datetime
