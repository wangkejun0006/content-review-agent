from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from smart_growth_agent.domain.enums import (
    KnowledgeCriticality,
    RetrievalMethod,
    VerificationResult,
)


class KnowledgeSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    source_type: str = Field(min_length=1, max_length=100)
    platform: str | None = Field(default=None, max_length=50)
    canonical_url: HttpUrl
    retrieval_method: RetrievalMethod = RetrievalMethod.MANUAL
    freshness_days: int = Field(default=90, ge=1, le=3650)
    criticality: KnowledgeCriticality = KnowledgeCriticality.NORMAL


class KnowledgeSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    source_type: str
    platform: str | None
    canonical_url: str
    retrieval_method: RetrievalMethod
    freshness_days: int
    criticality: KnowledgeCriticality
    enabled: bool
    created_at: datetime
    updated_at: datetime


class SourceCaptureCreate(BaseModel):
    content: str = Field(min_length=1)
    captured_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class SourceCaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    source_id: uuid.UUID
    captured_at: datetime
    content: str
    checksum: str
    metadata_json: dict
    created_at: datetime


class RegistryVerificationCreate(BaseModel):
    source_id: uuid.UUID | None = None
    source_capture_id: uuid.UUID | None = None
    checked_at: datetime | None = None
    result: VerificationResult
    notes: str = ""


class RegistryVerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    revision_id: uuid.UUID
    source_id: uuid.UUID | None
    source_capture_id: uuid.UUID | None
    checked_at: datetime
    result: VerificationResult
    checked_by: uuid.UUID | None
    notes: str
    created_at: datetime


class FreshnessIssue(BaseModel):
    revision_id: uuid.UUID
    stable_key: str
    source_id: uuid.UUID | None = None
    critical: bool
    stale: bool
    change_detected: bool = False
    last_verified_at: datetime | None = None
    freshness_days: int
    message: str


class ProductClaimCoverageRead(BaseModel):
    product_item_id: uuid.UUID
    product_revision_id: uuid.UUID
    product_name: str
    active_claims: int
    fully_supported_claims: int
    verified_evidence_documents: int
    status: str
    warnings: list[str]


class ClaimCoverageRead(BaseModel):
    scope: str
    run_id: uuid.UUID | None = None
    products_total: int
    products_with_claims: int
    product_claim_coverage_percent: float
    claims_total: int
    fully_supported_claims: int
    claim_evidence_coverage_percent: float
    verified_evidence_documents: int
    products: list[ProductClaimCoverageRead]
