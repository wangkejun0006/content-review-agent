from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"


class RegistryType(StrEnum):
    BRAND_PROFILE = "brand_profile"
    PRODUCT = "product"
    PRODUCT_CLAIM = "product_claim"
    AUDIENCE = "audience"
    PLATFORM_RULE = "platform_rule"
    PLATFORM_MARKETING_PROGRAM = "platform_marketing_program"
    CONTENT_PATTERN = "content_pattern"
    STRATEGY_INSIGHT = "strategy_insight"
    SCORING_RUBRIC = "scoring_rubric"
    PROMPT_TEMPLATE = "prompt_template"


class RevisionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class VerificationStatus(StrEnum):
    PROVISIONAL = "provisional"
    VERIFIED = "verified"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    PHASE1_READY = "phase1_ready"
    WAITING_KNOWLEDGE_REVIEW = "waiting_knowledge_review"
    CONTENT_DRAFT_READY = "content_draft_ready"
    READY_FOR_MANUAL_PUBLISH = "ready_for_manual_publish"
    REJECTED = "rejected"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobType(StrEnum):
    GROWTH_RUN = "growth_run"
    FEEDBACK_RUN = "feedback_run"


class FeedbackRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Platform(StrEnum):
    XHS = "xhs"
    JD = "jd"


class AttributionStrength(StrEnum):
    DIRECT = "direct"
    ASSISTED = "assisted"
    CORRELATIVE = "correlative"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_EDIT = "approved_with_edit"
    REQUEST_CHANGES = "request_changes"
    REJECTED = "rejected"


class RetrievalMethod(StrEnum):
    MANUAL = "manual"
    FIXED_URL = "fixed_url"
    WEB_SEARCH = "web_search"
    OFFICIAL_API = "official_api"


class KnowledgeCriticality(StrEnum):
    NORMAL = "normal"
    CRITICAL = "critical"


class VerificationResult(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNAVAILABLE = "unavailable"
    MANUALLY_VERIFIED = "manually_verified"


class ContextType(StrEnum):
    PRODUCT = "product"
    POLICY = "policy"
    TREND = "trend"
