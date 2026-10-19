from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SemanticFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "medical_claim",
        "false_experience",
        "ai_trace",
        "advertising",
        "authenticity",
    ]
    severity: Literal["blocker", "warning"]
    message: str = Field(min_length=1)
    evidence_excerpt: str = ""
    suggestion: str = Field(min_length=1)
    rule_revision_id: uuid.UUID | None = None
    claim_revision_id: uuid.UUID | None = None


class ComplianceSemanticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    findings: list[SemanticFinding] = Field(default_factory=list)
    requires_revision: bool


class ComplianceFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    severity: str
    message: str
    source: str
    evidence_excerpt: str
    suggestion: str
    rule_revision_id: uuid.UUID | None
    claim_revision_id: uuid.UUID | None


class ComplianceReportRead(BaseModel):
    id: uuid.UUID
    content_version_id: uuid.UUID
    deterministic_pass: bool
    semantic_pass: bool
    has_blockers: bool
    summary: str
    findings: list[ComplianceFindingRead]
