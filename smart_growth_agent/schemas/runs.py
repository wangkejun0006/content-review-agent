from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_growth_agent.domain.enums import RunStatus


class BriefConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["xhs"] = "xhs"
    content_identity: Literal["brand_owned"] = "brand_owned"
    key_message: str = ""
    required_points: list[str] = Field(default_factory=list)
    forbidden_points: list[str] = Field(default_factory=list)
    tone: list[str] = Field(default_factory=lambda: ["克制", "生活化", "科技美学"])
    scenario: str = ""
    cta_type: Literal["discussion", "save", "learn_more"] = "discussion"
    body_length: int = Field(default=600, ge=100, le=2000)
    candidate_count: Literal[3] = 3
    marketing_support_policy: Literal["organic_only", "evaluate", "required"] = "evaluate"
    marketing_objective: Literal[
        "awareness",
        "content_validation",
        "creator_seeding",
        "amplification",
        "conversion",
    ] = "awareness"
    marketing_budget_min: int | None = Field(default=None, ge=0)
    marketing_budget_max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_marketing_budget(self) -> BriefConstraints:
        if (
            self.marketing_budget_min is not None
            and self.marketing_budget_max is not None
            and self.marketing_budget_max < self.marketing_budget_min
        ):
            raise ValueError("marketing_budget_max cannot be below marketing_budget_min")
        return self


class CampaignBriefCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1)
    product_item_ids: list[uuid.UUID] = Field(min_length=1)
    audience_item_ids: list[uuid.UUID] = Field(default_factory=list)
    constraints: BriefConstraints = Field(default_factory=BriefConstraints)


class CampaignBriefRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    objective: str
    product_item_ids: list[str]
    audience_item_ids: list[str]
    constraints: dict
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class GrowthRunCreate(BaseModel):
    brief_id: uuid.UUID


class GrowthRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    brief_id: uuid.UUID
    thread_id: str
    status: RunStatus
    gate_status: str
    error: dict[str, Any] | None
    recommended_candidate_id: uuid.UUID | None
    selected_candidate_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    registry_revision_ids: list[uuid.UUID] = Field(default_factory=list)
    job_id: uuid.UUID | None = None
