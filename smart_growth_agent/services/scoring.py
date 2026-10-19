from __future__ import annotations

import json
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import (
    ComplianceFinding,
    ComplianceReport,
    ContentCandidate,
    ContentVersion,
    LLMCallLog,
    RegistryItem,
    RegistryRevision,
    RunRegistrySnapshot,
    ScoreDimension,
    ScoreReport,
)
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.registry import ScoringRubricPayload
from smart_growth_agent.schemas.scoring import (
    ScoreDimensionRead,
    ScoreReportRead,
    ScoringOutput,
)
from smart_growth_agent.services.phase2 import canonical_checksum, generation_key

PROMPT_SCORING = "xhs_scoring"
RUBRIC_XHS_CONTENT = "xhs_content_score"


class ScoringService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_gateway: LLMGateway,
    ) -> None:
        self.session_factory = session_factory
        self.llm_gateway = llm_gateway

    async def score_content_version(
        self, *, brand_id: uuid.UUID, content_version_id: uuid.UUID
    ) -> uuid.UUID:
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(ScoreReport).where(
                    ScoreReport.brand_id == brand_id,
                    ScoreReport.content_version_id == content_version_id,
                )
            )
            if existing is not None:
                return existing.id
            version = await session.scalar(
                select(ContentVersion).where(
                    ContentVersion.id == content_version_id,
                    ContentVersion.brand_id == brand_id,
                )
            )
            if version is None:
                raise RuntimeError("content version not found")
            candidate = await session.get(ContentCandidate, version.candidate_id)
            if candidate is None or candidate.brand_id != brand_id:
                raise RuntimeError("content candidate not found")
            compliance = await session.scalar(
                select(ComplianceReport).where(
                    ComplianceReport.content_version_id == version.id,
                    ComplianceReport.brand_id == brand_id,
                )
            )
            if compliance is None:
                raise RuntimeError("content version must be reviewed for compliance before scoring")
            findings = list(
                await session.scalars(
                    select(ComplianceFinding)
                    .where(ComplianceFinding.report_id == compliance.id)
                    .order_by(ComplianceFinding.created_at)
                )
            )
            snapshot_rows = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(
                            RunRegistrySnapshot,
                            RunRegistrySnapshot.item_id == RegistryItem.id,
                        )
                        .join(
                            RegistryRevision,
                            RegistryRevision.id == RunRegistrySnapshot.revision_id,
                        )
                        .where(RunRegistrySnapshot.run_id == candidate.run_id)
                    )
                ).all()
            )

        prompt = self._require_asset(
            snapshot_rows, RegistryType.PROMPT_TEMPLATE, PROMPT_SCORING
        )
        rubric_revision = self._require_asset(
            snapshot_rows, RegistryType.SCORING_RUBRIC, RUBRIC_XHS_CONTENT
        )
        rubric = ScoringRubricPayload.model_validate(rubric_revision.payload)
        input_payload = {
            "content": version.payload,
            "compliance": {
                "has_blockers": compliance.has_blockers,
                "semantic_pass": compliance.semantic_pass,
                "summary": compliance.summary,
                "findings": [
                    {
                        "category": finding.category,
                        "severity": finding.severity,
                        "message": finding.message,
                    }
                    for finding in findings
                ],
            },
            "rubric": rubric.model_dump(mode="json"),
        }
        checksum = canonical_checksum(input_payload)
        key = generation_key(
            content_version_id, "scoring", rubric_revision.id, prompt.id, checksum
        )
        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                run_id=candidate.run_id,
                purpose="xhs_scoring",
                prompt_revision_id=prompt.id,
                temperature=0.1,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
                    ),
                ],
            ),
            ScoringOutput,
        )
        weights = {item.name: item.weight for item in rubric.dimensions}
        total = sum(
            Decimal(item.score) * Decimal(weights[item.name]) / Decimal(100)
            for item in result.value.dimensions
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        async with self.session_factory() as session, session.begin():
            report = ScoreReport(
                brand_id=brand_id,
                content_version_id=content_version_id,
                rubric_revision_id=rubric_revision.id,
                prompt_revision_id=prompt.id,
                total_score=total,
                pass_threshold=rubric.pass_threshold,
                summary=result.value.summary,
                revision_suggestions=result.value.revision_suggestions,
                input_checksum=checksum,
                generation_key=key,
            )
            session.add(report)
            await session.flush()
            for item in result.value.dimensions:
                session.add(
                    ScoreDimension(
                        brand_id=brand_id,
                        report_id=report.id,
                        dimension=item.name,
                        score=Decimal(item.score),
                        rationale=item.rationale,
                    )
                )
            if not result.telemetry_logged:
                session.add(
                    LLMCallLog(
                    brand_id=brand_id,
                    run_id=candidate.run_id,
                    provider=result.provider,
                    model=result.model,
                    purpose="xhs_scoring",
                    prompt_revision_id=prompt.id,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.latency_ms,
                    provider_request_id=result.provider_request_id,
                    )
                )
            await session.flush()
            return report.id

    async def get_report(
        self, *, brand_id: uuid.UUID, report_id: uuid.UUID
    ) -> ScoreReportRead:
        async with self.session_factory() as session:
            report = await session.scalar(
                select(ScoreReport).where(
                    ScoreReport.id == report_id,
                    ScoreReport.brand_id == brand_id,
                )
            )
            if report is None:
                raise RuntimeError("score report not found")
            dimensions = list(
                await session.scalars(
                    select(ScoreDimension)
                    .where(ScoreDimension.report_id == report.id)
                    .order_by(ScoreDimension.created_at)
                )
            )
        return ScoreReportRead(
            id=report.id,
            content_version_id=report.content_version_id,
            rubric_revision_id=report.rubric_revision_id,
            prompt_revision_id=report.prompt_revision_id,
            total_score=report.total_score,
            pass_threshold=report.pass_threshold,
            passed=report.total_score >= report.pass_threshold,
            summary=report.summary,
            revision_suggestions=report.revision_suggestions,
            dimensions=[
                ScoreDimensionRead(
                    name=item.dimension,
                    score=item.score,
                    rationale=item.rationale,
                )
                for item in dimensions
            ],
        )

    @staticmethod
    def _require_asset(
        rows: list[tuple[RegistryItem, RegistryRevision]],
        registry_type: RegistryType,
        stable_key: str,
    ) -> RegistryRevision:
        for item, revision in rows:
            if item.registry_type == registry_type and item.stable_key == stable_key:
                return revision
        raise RuntimeError(
            f"required {registry_type.value} revision is missing from run snapshot: {stable_key}"
        )
