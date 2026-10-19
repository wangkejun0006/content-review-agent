from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column

from smart_growth_agent.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from smart_growth_agent.domain.enums import (
    AttributionStrength,
    ContextType,
    FeedbackRunStatus,
    JobStatus,
    JobType,
    KnowledgeCriticality,
    Platform,
    RegistryType,
    RetrievalMethod,
    RevisionStatus,
    Role,
    RunStatus,
    VerificationResult,
    VerificationStatus,
)

JSONType = JSON().with_variant(JSONB(), "postgresql")


@compiles(Vector, "sqlite")
def compile_vector_sqlite(_type: Vector, _compiler: Any, **_kwargs: Any) -> str:
    return "TEXT"


def enum_column(enum_type: type, *, default: Any | None = None) -> Any:
    return mapped_column(
        Enum(
            enum_type,
            native_enum=False,
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=default,
    )


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BrandMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brand_memberships"
    __table_args__ = (UniqueConstraint("brand_id", "user_id"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[Role] = enum_column(Role)


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )


class RegistryItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "registry_items"
    __table_args__ = (UniqueConstraint("brand_id", "registry_type", "stable_key"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    registry_type: Mapped[RegistryType] = enum_column(RegistryType)
    stable_key: Mapped[str] = mapped_column(String(200), nullable=False)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "registry_revisions.id",
            name="fk_registry_items_current_revision_id_registry_revisions",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegistryRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "registry_revisions"
    __table_args__ = (
        UniqueConstraint("item_id", "version"),
        Index(
            "uq_registry_revisions_one_active",
            "item_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("registry_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RevisionStatus] = enum_column(RevisionStatus, default=RevisionStatus.DRAFT)
    verification_status: Mapped[VerificationStatus] = enum_column(
        VerificationStatus, default=VerificationStatus.PROVISIONAL
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    activated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegistryLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "registry_links"
    __table_args__ = (
        UniqueConstraint(
            "source_revision_id", "relation_type", "target_item_id", "target_revision_id"
        ),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    source_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("registry_revisions.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("registry_items.id", ondelete="CASCADE"), nullable=False
    )
    target_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("registry_revisions.id", ondelete="SET NULL"), nullable=True
    )


class EvidenceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_documents"

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EvidenceChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)


class IngestionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_records"
    __table_args__ = (
        Index("ix_ingestion_records_source", "brand_id", "ingestion_type", "source_checksum"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    ingestion_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duplicate_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    matches: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    recommended_action: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="awaiting_decision")
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resulting_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resulting_evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProductMediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_media_assets"

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    product_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("registry_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_type: Mapped[str] = mapped_column(String(30), nullable=False, default="image")
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    alt_text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)


class RevisionEvidenceLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_evidence_links"
    __table_args__ = (UniqueConstraint("revision_id", "evidence_document_id"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("registry_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )


class CampaignBrief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_briefs"

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    product_item_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    audience_item_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GrowthRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "growth_runs"

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    brief_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("campaign_briefs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[RunStatus] = enum_column(RunStatus, default=RunStatus.QUEUED)
    gate_status: Mapped[str] = mapped_column(String(100), nullable=False, default="pending")
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    recommended_candidate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunRegistrySnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "run_registry_snapshots"
    __table_args__ = (UniqueConstraint("run_id", "revision_id"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("growth_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )


class StrategyPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_plans"
    __table_args__ = (
        UniqueConstraint("run_id"),
        UniqueConstraint("generation_key"),
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("growth_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    prompt_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)


class ContentCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_candidates"
    __table_args__ = (UniqueConstraint("run_id", "route_key"),)
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("growth_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    route_key: Mapped[str] = mapped_column(String(100), nullable=False)
    angle_key: Mapped[str] = mapped_column(String(100), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ContentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version"),
        UniqueConstraint("generation_key"),
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    prompt_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)


class ContentClaimUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_claim_usages"
    __table_args__ = (UniqueConstraint("content_version_id", "claim_revision_id", "usage_type"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    usage_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")


class KnowledgeSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (UniqueConstraint("brand_id", "canonical_url"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_method: Mapped[RetrievalMethod] = enum_column(RetrievalMethod)
    freshness_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    criticality: Mapped[KnowledgeCriticality] = enum_column(
        KnowledgeCriticality, default=KnowledgeCriticality.NORMAL
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SourceCapture(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_captures"
    __table_args__ = (UniqueConstraint("source_id", "checksum"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class RegistryVerification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "registry_verifications"

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("registry_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_capture_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("source_captures.id", ondelete="SET NULL"), nullable=True
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[VerificationResult] = enum_column(VerificationResult)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RunContextPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "run_context_packages"
    __table_args__ = (
        UniqueConstraint("run_id", "context_type"),
        UniqueConstraint("generation_key"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("growth_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    context_type: Mapped[ContextType] = enum_column(ContextType)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class ComplianceReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_reports"
    __table_args__ = (
        UniqueConstraint("content_version_id"),
        UniqueConstraint("generation_key"),
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    deterministic_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    semantic_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_blockers: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)


class ComplianceFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_findings"
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compliance_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggestion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rule_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    claim_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class ScoreReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "score_reports"
    __table_args__ = (
        UniqueConstraint("content_version_id"),
        UniqueConstraint("generation_key"),
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rubric_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    prompt_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    pass_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    revision_suggestions: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)


class ScoreDimension(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "score_dimensions"
    __table_args__ = (UniqueConstraint("report_id", "dimension"),)
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("score_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)


class HumanReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "human_reviews"
    __table_args__ = (UniqueConstraint("brand_id", "idempotency_key"),)
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    content_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class LLMCallLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "llm_call_logs"
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )


class LLMProviderConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "llm_provider_configs"
    __table_args__ = (UniqueConstraint("brand_id", "name"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    default_model: Mapped[str] = mapped_column(String(200), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentLLMBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_llm_bindings"
    __table_args__ = (UniqueConstraint("brand_id", "purpose"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("llm_provider_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_override: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("brand_id", "idempotency_key"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    job_type: Mapped[JobType] = enum_column(JobType)
    status: Mapped[JobStatus] = enum_column(JobStatus, default=JobStatus.QUEUED)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    manual_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)


class WorkerHeartbeat(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    hostname: Mapped[str] = mapped_column(String(200), nullable=False)
    process_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    current_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class Publication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("brand_id", "platform", "platform_content_id"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    platform: Mapped[Platform] = enum_column(Platform)
    platform_content_id: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MetricSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metric_snapshots"
    __table_args__ = (UniqueConstraint("publication_id", "captured_at"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    publication_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collections: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_visits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outbound_clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_correction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrects_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("metric_snapshots.id", ondelete="RESTRICT"), nullable=True
    )


class CommerceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commerce_snapshots"
    __table_args__ = (UniqueConstraint("brand_id", "scope_type", "scope_key", "captured_at"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(300), nullable=False)
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    add_to_cart: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gmv: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)


class AttributionEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attribution_evidence"
    __table_args__ = (
        UniqueConstraint("publication_id", "commerce_snapshot_id", "evidence_type"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    publication_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commerce_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("commerce_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    strength: Mapped[AttributionStrength] = enum_column(AttributionStrength)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("brand_id", "idempotency_key"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    import_type: Mapped[str] = mapped_column(String(50), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)


class FeedbackRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback_runs"

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[FeedbackRunStatus] = enum_column(
        FeedbackRunStatus, default=FeedbackRunStatus.QUEUED
    )
    publication_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    metric_snapshot_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    commerce_snapshot_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    attribution_evidence_ids: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list
    )
    prompt_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    input_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)


class FeedbackRunRegistrySnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "feedback_run_registry_snapshots"
    __table_args__ = (UniqueConstraint("feedback_run_id", "revision_id"),)

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    feedback_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("feedback_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )


class FeedbackRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback_recommendations"
    __table_args__ = (
        UniqueConstraint("feedback_run_id"),
        UniqueConstraint("generation_key"),
    )

    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    feedback_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("feedback_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendation: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    attribution_scope: Mapped[AttributionStrength] = enum_column(AttributionStrength)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_insight_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("registry_revisions.id", ondelete="RESTRICT"), nullable=True
    )
