from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_growth_agent.domain.enums import ReviewDecision
from smart_growth_agent.schemas.phase2 import WriterOutput


class HumanReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    selected_candidate_id: uuid.UUID | None = None
    edited_content: WriterOutput | None = None
    change_request: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_decision_payload(self) -> HumanReviewCreate:
        if self.decision in {
            ReviewDecision.APPROVED,
            ReviewDecision.APPROVED_WITH_EDIT,
            ReviewDecision.REQUEST_CHANGES,
        } and self.selected_candidate_id is None:
            raise ValueError("selected_candidate_id is required for this decision")
        if self.decision == ReviewDecision.APPROVED_WITH_EDIT and self.edited_content is None:
            raise ValueError("edited_content is required for approved_with_edit")
        if self.decision == ReviewDecision.REQUEST_CHANGES and self.change_request is None:
            raise ValueError("change_request is required for request_changes")
        return self


class HumanReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    run_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: str
    selected_candidate_id: uuid.UUID | None
    content_version_id: uuid.UUID | None
    idempotency_key: str
    payload: dict
    created_at: datetime
