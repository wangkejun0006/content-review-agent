from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactReference(StrictContract):
    revision_id: uuid.UUID
    statement: str = Field(min_length=1)


class ClaimReference(StrictContract):
    claim_revision_id: uuid.UUID
    statement: str = Field(min_length=1)
    allowed_expression: str = Field(min_length=1)


class ProductContextOutput(StrictContract):
    schema_name: Literal["product_context_package"] = "product_context_package"
    schema_version: Literal["1.0"] = "1.0"
    summary: str = Field(min_length=1)
    relevant_facts: list[FactReference] = Field(default_factory=list)
    allowed_claims: list[ClaimReference] = Field(default_factory=list)
    provisional_facts: list[FactReference] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class PolicyRuleReference(StrictContract):
    revision_id: uuid.UUID
    stable_key: str
    category: str
    rule_text: str
    severity: str
    source_url: str
    stale: bool = False


class PolicyContextOutput(StrictContract):
    schema_name: Literal["policy_context_package"] = "policy_context_package"
    schema_version: Literal["1.0"] = "1.0"
    rules: list[PolicyRuleReference] = Field(default_factory=list)
    freshness_warnings: list[str] = Field(default_factory=list)


class TrendObservation(StrictContract):
    platform: str
    topic: str
    trend_type: Literal["topic", "format", "hook", "visual", "language"]
    source_url: str
    observed_at: str
    summary: str
    relevance_score: float = Field(ge=0, le=1)
    confidence: Literal["low", "medium", "high"]
    risks: list[str] = Field(default_factory=list)


class TrendResearchOutput(StrictContract):
    schema_name: Literal["trend_context_package"] = "trend_context_package"
    schema_version: Literal["1.0"] = "1.0"
    observations: list[TrendObservation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CreativeRoute(StrictContract):
    route_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,99}$")
    angle_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,99}$")
    angle_name: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    target_emotion: str = Field(min_length=1)
    hook_mechanism: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    variation_axes: list[str] = Field(min_length=1)
    allowed_claim_revision_ids: list[uuid.UUID] = Field(default_factory=list)
    visual_direction: str = Field(min_length=1)
    cta_direction: str = Field(min_length=1)


class MarketingSupportRecommendation(StrictContract):
    policy: Literal["organic_only", "evaluate", "required"] = "evaluate"
    recommended: bool = False
    program_revision_ids: list[uuid.UUID] = Field(default_factory=list)
    program_names: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    application_checklist: list[str] = Field(default_factory=list)
    budget_assumptions: list[str] = Field(default_factory=list)
    measurement_plan: list[str] = Field(default_factory=list)
    human_decision_required: Literal[True] = True


class StrategyOutput(StrictContract):
    schema_name: Literal["xhs_strategy_plan"] = "xhs_strategy_plan"
    schema_version: Literal["1.0"] = "1.0"
    objective: str = Field(min_length=1)
    target_audience: str = Field(min_length=1)
    key_message: str = Field(min_length=1)
    brand_voice: list[str] = Field(min_length=1)
    guardrails: list[str] = Field(default_factory=list)
    marketing_support: MarketingSupportRecommendation = Field(
        default_factory=MarketingSupportRecommendation
    )
    creative_routes: list[CreativeRoute] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_routes(self) -> StrategyOutput:
        keys = [route.route_key for route in self.creative_routes]
        if len(set(keys)) != 3:
            raise ValueError("creative route_key values must be unique")
        return self


class VisualBrief(StrictContract):
    cover_concept: str = Field(min_length=1)
    cover_text: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    shot_list: list[str] = Field(min_length=1)
    props_and_background: list[str] = Field(default_factory=list)
    avoid_elements: list[str] = Field(default_factory=list)


class MediaPlan(StrictContract):
    preferred_format: Literal["image_set", "video"] = "image_set"
    rationale: str = Field(
        default="沿用视觉建议，由运营人员决定最终形式", max_length=300
    )
    preferred_generation_prompt: str = Field(
        default="根据 visual_brief 生成克制、真实的产品内容素材",
        min_length=1,
        max_length=600,
    )
    alternate_format: Literal["image_set", "video"] = "video"
    alternate_generation_prompt: str = Field(
        default="将同一创意转换为备用内容形式", min_length=1, max_length=300
    )
    aspect_ratio: str = "3:4"
    duration_seconds: int | None = Field(default=None, ge=5, le=180)
    image_sequence: list[str] = Field(default_factory=list, max_length=8)
    shot_list: list[str] = Field(default_factory=list, max_length=8)
    voiceover: str = Field(default="", max_length=800)
    on_screen_text: list[str] = Field(default_factory=list, max_length=10)
    negative_prompts: list[str] = Field(default_factory=list, max_length=10)
    shooting_notes: list[str] = Field(default_factory=list, max_length=8)
    product_media_ids: list[uuid.UUID] = Field(default_factory=list)
    claim_revision_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_alternate_format(self) -> MediaPlan:
        if self.alternate_format == self.preferred_format:
            raise ValueError("alternate_format must differ from preferred_format")
        if self.preferred_format == "video" and self.duration_seconds is None:
            raise ValueError("video media plan requires duration_seconds")
        return self


class WriterOutput(StrictContract):
    schema_name: Literal["xhs_content_candidate"] = "xhs_content_candidate"
    schema_version: Literal["1.0"] = "1.0"
    route_key: str
    angle_key: str
    title_options: list[str] = Field(min_length=3, max_length=3)
    recommended_title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    visual_brief: VisualBrief
    media_plan: MediaPlan = Field(default_factory=MediaPlan)
    tags: list[str] = Field(default_factory=list, max_length=20)
    cta: str = Field(min_length=1)
    cited_claim_revision_ids: list[uuid.UUID] = Field(default_factory=list)
    source_revision_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_recommended_title(self) -> WriterOutput:
        if self.recommended_title not in self.title_options:
            raise ValueError("recommended_title must be one of title_options")
        if len(set(self.title_options)) != 3:
            raise ValueError("title_options must be unique")
        return self


class ContextPackageRead(StrictContract):
    id: uuid.UUID
    context_type: str
    payload: dict


class StrategyPlanRead(StrictContract):
    id: uuid.UUID
    payload: StrategyOutput


class ContentCandidateRead(StrictContract):
    id: uuid.UUID
    route_key: str
    angle_key: str
    current_version: int
    content_version_id: uuid.UUID
    payload: WriterOutput
