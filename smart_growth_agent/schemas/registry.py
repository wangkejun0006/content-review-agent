from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from smart_growth_agent.domain.enums import (
    RegistryType,
    RevisionStatus,
    RiskLevel,
    VerificationStatus,
)


class BrandProfilePayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    positioning: str = Field(min_length=1)
    brand_story: str = ""
    voice: list[str] = Field(default_factory=list)
    forbidden_tones: list[str] = Field(default_factory=list)


class ProductPayload(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    sku: str | None = Field(default=None, max_length=100)
    product_type: Literal["desk_accessory", "stationery"]
    description: str = Field(min_length=1)
    features: list[str] = Field(min_length=1)
    materials: list[str] = Field(default_factory=list)
    non_medical_disclaimer: str = "虚构文具示例，不涉及健康或医疗用途"


class ProductClaimPayload(BaseModel):
    statement: str = Field(min_length=1)
    allowed_expressions: list[str] = Field(min_length=1)
    forbidden_expressions: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    product_item_ids: list[uuid.UUID] = Field(min_length=1)
    evidence_document_ids: list[uuid.UUID] = Field(min_length=1)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> ProductClaimPayload:
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class AudiencePayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    scenarios: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)


class PlatformRulePayload(BaseModel):
    platform: Literal["xhs", "douyin"] = "xhs"
    category: Literal["content_compliance", "ai_content", "health_claim", "recommendation"]
    rule_text: str = Field(min_length=1)
    severity: Literal["blocker", "warning", "information"]
    source_url: HttpUrl
    effective_from: date | None = None
    verified_at: datetime


class PlatformMarketingProgramPayload(BaseModel):
    platform: Literal["xhs"] = "xhs"
    name: str = Field(min_length=1, max_length=200)
    program_type: Literal[
        "creator_custom",
        "creator_batch",
        "product_trial",
        "live_buyer",
        "ad_campaign",
        "content_boost",
        "official_consulting",
    ]
    objectives: list[
        Literal[
            "awareness",
            "content_validation",
            "creator_seeding",
            "amplification",
            "conversion",
        ]
    ] = Field(min_length=1)
    description: str = Field(min_length=1)
    eligibility_requirements: list[str] = Field(default_factory=list)
    required_assets: list[str] = Field(default_factory=list)
    application_steps: list[str] = Field(default_factory=list)
    budget_guidance: str = "需由运营人员向平台确认"
    measurement_signals: list[str] = Field(default_factory=list)
    source_url: HttpUrl
    verified_at: datetime


class ContentPatternPayload(BaseModel):
    name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    structure: list[str] = Field(min_length=1)
    suitable_audience_keys: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class StrategyInsightPayload(BaseModel):
    observation: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    recommended_actions: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    supporting_feedback_run_ids: list[uuid.UUID] = Field(default_factory=list)
    attribution_scope: Literal["direct", "assisted", "correlative"] = "correlative"


class RubricDimension(BaseModel):
    name: Literal["Hook", "Emotion", "Authenticity", "Visual", "SaveValue", "Conversion"]
    weight: int = Field(gt=0, le=100)
    criteria: str = Field(min_length=1)


class ScoringRubricPayload(BaseModel):
    name: str = Field(min_length=1)
    pass_threshold: int = Field(default=70, ge=0, le=100)
    dimensions: list[RubricDimension] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_dimensions(self) -> ScoringRubricPayload:
        expected = {"Hook", "Emotion", "Authenticity", "Visual", "SaveValue", "Conversion"}
        actual = {dimension.name for dimension in self.dimensions}
        if actual != expected:
            raise ValueError(f"dimensions must be exactly {sorted(expected)}")
        if sum(dimension.weight for dimension in self.dimensions) != 100:
            raise ValueError("dimension weights must total 100")
        return self


class PromptTemplatePayload(BaseModel):
    purpose: str = Field(min_length=1, max_length=100)
    template: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    output_schema_name: str = Field(min_length=1, max_length=200)


PAYLOAD_MODELS: dict[RegistryType, type[BaseModel]] = {
    RegistryType.BRAND_PROFILE: BrandProfilePayload,
    RegistryType.PRODUCT: ProductPayload,
    RegistryType.PRODUCT_CLAIM: ProductClaimPayload,
    RegistryType.AUDIENCE: AudiencePayload,
    RegistryType.PLATFORM_RULE: PlatformRulePayload,
    RegistryType.PLATFORM_MARKETING_PROGRAM: PlatformMarketingProgramPayload,
    RegistryType.CONTENT_PATTERN: ContentPatternPayload,
    RegistryType.STRATEGY_INSIGHT: StrategyInsightPayload,
    RegistryType.SCORING_RUBRIC: ScoringRubricPayload,
    RegistryType.PROMPT_TEMPLATE: PromptTemplatePayload,
}


def validate_registry_payload(
    registry_type: RegistryType, payload: dict[str, Any]
) -> dict[str, Any]:
    model = PAYLOAD_MODELS[registry_type].model_validate(payload)
    return model.model_dump(mode="json")


class RegistryItemCreate(BaseModel):
    stable_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,199}$")
    payload: dict[str, Any]
    search_text: str = ""
    source_uri: str | None = None
    verification_status: VerificationStatus = VerificationStatus.PROVISIONAL


class RegistryRevisionCreate(BaseModel):
    payload: dict[str, Any]
    search_text: str = ""
    source_uri: str | None = None
    verification_status: VerificationStatus = VerificationStatus.PROVISIONAL


class RegistryRevisionUpdate(BaseModel):
    payload: dict[str, Any] | None = None
    search_text: str | None = None
    source_uri: str | None = None
    verification_status: VerificationStatus | None = None


class RegistryRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    version: int
    status: RevisionStatus
    verification_status: VerificationStatus
    payload: dict[str, Any]
    search_text: str
    source_uri: str | None
    checksum: str
    created_by: uuid.UUID
    activated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None


class RegistryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    registry_type: RegistryType
    stable_key: str
    current_revision_id: uuid.UUID | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RegistryItemDetail(RegistryItemRead):
    revisions: list[RegistryRevisionRead]


class EvidenceDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    document_type: str = Field(min_length=1, max_length=100)
    source_uri: str = Field(min_length=1)
    content: str = Field(min_length=1)


class EvidenceDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    document_type: str
    source_uri: str
    content: str
    checksum: str
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    is_active: bool
    created_at: datetime


DEFAULT_SCORING_RUBRIC = ScoringRubricPayload(
    name="XHS Content Score v1",
    pass_threshold=70,
    dimensions=[
        RubricDimension(name="Hook", weight=20, criteria="开头能否迅速建立阅读动机"),
        RubricDimension(name="Emotion", weight=15, criteria="是否形成真实且克制的情绪连接"),
        RubricDimension(name="Authenticity", weight=20, criteria="表达是否可信且无虚构体验"),
        RubricDimension(name="Visual", weight=15, criteria="视觉建议是否明确且适合产品"),
        RubricDimension(name="SaveValue", weight=15, criteria="是否提供值得收藏的实用信息"),
        RubricDimension(name="Conversion", weight=15, criteria="是否自然引导进一步了解或购买"),
    ],
)
