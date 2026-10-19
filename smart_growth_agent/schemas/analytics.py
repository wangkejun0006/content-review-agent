from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from smart_growth_agent.domain.enums import AttributionStrength, Platform


class PublicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_version_id: uuid.UUID
    platform: Literal[Platform.XHS] = Platform.XHS
    platform_content_id: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    published_at: datetime


class PublicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    content_version_id: uuid.UUID
    platform: Platform
    platform_content_id: str
    url: str
    published_at: datetime
    created_at: datetime


class MetricFields(BaseModel):
    impressions: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    collections: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    follows: int | None = Field(default=None, ge=0)
    profile_visits: int | None = Field(default=None, ge=0)
    outbound_clicks: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_metric(self) -> MetricFields:
        metric_names = (
            "impressions",
            "views",
            "likes",
            "collections",
            "comments",
            "shares",
            "follows",
            "profile_visits",
            "outbound_clicks",
        )
        if all(getattr(self, name) is None for name in metric_names):
            raise ValueError("at least one metric is required")
        return self


class MetricSnapshotCreate(MetricFields):
    model_config = ConfigDict(extra="forbid")

    captured_at: datetime
    is_correction: bool = False
    correction_reason: str | None = Field(default=None, min_length=1, max_length=2000)
    corrects_snapshot_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_correction(self) -> MetricSnapshotCreate:
        if self.is_correction and (
            self.correction_reason is None or self.corrects_snapshot_id is None
        ):
            raise ValueError("correction requires reason and corrects_snapshot_id")
        if not self.is_correction and (
            self.correction_reason is not None or self.corrects_snapshot_id is not None
        ):
            raise ValueError("non-correction snapshot cannot reference a correction")
        return self


class MetricSnapshotRead(MetricSnapshotCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    publication_id: uuid.UUID
    created_at: datetime


class CommerceSnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    captured_at: datetime
    scope_type: Literal["store", "sku", "campaign"]
    scope_key: str = Field(min_length=1, max_length=300)
    impressions: int | None = Field(default=None, ge=0)
    product_views: int | None = Field(default=None, ge=0)
    add_to_cart: int | None = Field(default=None, ge=0)
    orders: int | None = Field(default=None, ge=0)
    paid_orders: int | None = Field(default=None, ge=0)
    gmv: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_metric(self) -> CommerceSnapshotCreate:
        values = self.model_dump(exclude={"captured_at", "scope_type", "scope_key"})
        if all(value is None for value in values.values()):
            raise ValueError("at least one commerce metric is required")
        return self


class CommerceSnapshotRead(CommerceSnapshotCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    created_at: datetime


class AttributionEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_id: uuid.UUID
    commerce_snapshot_id: uuid.UUID
    evidence_type: Literal["dedicated_link", "code", "campaign", "manual_link"]
    strength: AttributionStrength
    details: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_strength(self) -> AttributionEvidenceCreate:
        if self.strength == AttributionStrength.DIRECT and self.evidence_type not in {
            "dedicated_link",
            "code",
        }:
            raise ValueError("direct attribution requires dedicated_link or code evidence")
        return self


class AttributionEvidenceRead(AttributionEvidenceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    created_at: datetime
