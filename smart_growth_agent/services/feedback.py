from __future__ import annotations

import json
import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import (
    AttributionEvidence,
    CommerceSnapshot,
    ContentCandidate,
    ContentVersion,
    FeedbackRecommendation,
    FeedbackRun,
    FeedbackRunRegistrySnapshot,
    Job,
    LLMCallLog,
    MetricSnapshot,
    Publication,
    RegistryItem,
    RegistryRevision,
    ScoreReport,
)
from smart_growth_agent.domain.enums import (
    AttributionStrength,
    FeedbackRunStatus,
    JobStatus,
    JobType,
    RegistryType,
    RevisionStatus,
    VerificationStatus,
)
from smart_growth_agent.domain.errors import ConflictError, NotFoundError, ValidationError
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.feedback import FeedbackOutput, FeedbackRunCreate
from smart_growth_agent.schemas.registry import StrategyInsightPayload
from smart_growth_agent.services.audit import record_audit
from smart_growth_agent.services.phase2 import canonical_checksum, generation_key
from smart_growth_agent.services.registry import payload_checksum

PROMPT_FEEDBACK = "xhs_feedback"
FEEDBACK_REGISTRY_TYPES = {
    RegistryType.BRAND_PROFILE,
    RegistryType.CONTENT_PATTERN,
    RegistryType.SCORING_RUBRIC,
    RegistryType.STRATEGY_INSIGHT,
}
ATTRIBUTION_RANK = {
    AttributionStrength.CORRELATIVE: 0,
    AttributionStrength.ASSISTED: 1,
    AttributionStrength.DIRECT: 2,
}


class FeedbackService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_gateway: LLMGateway | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.llm_gateway = llm_gateway

    async def create_run(
        self,
        *,
        brand_id: uuid.UUID,
        data: FeedbackRunCreate,
        actor_id: uuid.UUID,
        idempotency_key: str,
        max_attempts: int,
    ) -> tuple[FeedbackRun, Job, list[uuid.UUID]]:
        async with self.session_factory() as session, session.begin():
            existing_job = await session.scalar(
                select(Job).where(
                    Job.brand_id == brand_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
            if existing_job is not None:
                if existing_job.job_type != JobType.FEEDBACK_RUN:
                    raise ConflictError("idempotency key belongs to another job type")
                run = await session.get(
                    FeedbackRun, uuid.UUID(existing_job.payload["feedback_run_id"])
                )
                if run is None or run.brand_id != brand_id:
                    raise ConflictError("idempotency key is attached to an invalid feedback run")
                revision_ids = list(
                    await session.scalars(
                        select(FeedbackRunRegistrySnapshot.revision_id).where(
                            FeedbackRunRegistrySnapshot.feedback_run_id == run.id
                        )
                    )
                )
                return run, existing_job, revision_ids

            publications = list(
                await session.scalars(
                    select(Publication).where(
                        Publication.brand_id == brand_id,
                        Publication.id.in_(data.publication_ids),
                    )
                )
            )
            if len(publications) != len(data.publication_ids):
                raise ValidationError("all publications must belong to the current brand")
            metrics = list(
                await session.scalars(
                    select(MetricSnapshot)
                    .where(
                        MetricSnapshot.brand_id == brand_id,
                        MetricSnapshot.publication_id.in_(data.publication_ids),
                    )
                    .order_by(MetricSnapshot.captured_at)
                )
            )
            publications_with_metrics = {row.publication_id for row in metrics}
            if publications_with_metrics != set(data.publication_ids):
                raise ValidationError("every publication requires at least one metric snapshot")

            evidence_query = select(AttributionEvidence).where(
                AttributionEvidence.brand_id == brand_id,
                AttributionEvidence.publication_id.in_(data.publication_ids),
            )
            if data.commerce_snapshot_ids:
                commerce = list(
                    await session.scalars(
                        select(CommerceSnapshot).where(
                            CommerceSnapshot.brand_id == brand_id,
                            CommerceSnapshot.id.in_(data.commerce_snapshot_ids),
                        )
                    )
                )
                if len(commerce) != len(data.commerce_snapshot_ids):
                    raise ValidationError(
                        "all commerce snapshots must belong to the current brand"
                    )
                evidence_query = evidence_query.where(
                    AttributionEvidence.commerce_snapshot_id.in_(data.commerce_snapshot_ids)
                )
                evidence = list(await session.scalars(evidence_query))
            else:
                evidence = list(await session.scalars(evidence_query))
                commerce_ids = {row.commerce_snapshot_id for row in evidence}
                commerce = (
                    list(
                        await session.scalars(
                            select(CommerceSnapshot).where(
                                CommerceSnapshot.brand_id == brand_id,
                                CommerceSnapshot.id.in_(commerce_ids),
                            )
                        )
                    )
                    if commerce_ids
                    else []
                )

            active_assets = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(
                            RegistryRevision,
                            RegistryRevision.id == RegistryItem.current_revision_id,
                        )
                        .where(RegistryItem.brand_id == brand_id)
                    )
                ).all()
            )
            prompt_row = next(
                (
                    (item, revision)
                    for item, revision in active_assets
                    if item.registry_type == RegistryType.PROMPT_TEMPLATE
                    and item.stable_key == PROMPT_FEEDBACK
                ),
                None,
            )
            if prompt_row is None:
                raise ValidationError("active xhs_feedback prompt is required")
            frozen_assets = [
                (item, revision, "feedback_context")
                for item, revision in active_assets
                if item.registry_type in FEEDBACK_REGISTRY_TYPES
            ]
            frozen_assets.append((*prompt_row, "feedback_prompt"))

            run_id = uuid.uuid4()
            publication_ids = [str(item.id) for item in publications]
            metric_ids = [str(item.id) for item in metrics]
            commerce_ids = [str(item.id) for item in commerce]
            evidence_ids = [str(item.id) for item in evidence]
            checksum = canonical_checksum(
                {
                    "publication_ids": sorted(publication_ids),
                    "metric_snapshot_ids": sorted(metric_ids),
                    "commerce_snapshot_ids": sorted(commerce_ids),
                    "attribution_evidence_ids": sorted(evidence_ids),
                    "registry_revision_ids": sorted(str(row[1].id) for row in frozen_assets),
                }
            )
            run = FeedbackRun(
                id=run_id,
                brand_id=brand_id,
                thread_id=str(run_id),
                status=FeedbackRunStatus.QUEUED,
                publication_ids=publication_ids,
                metric_snapshot_ids=metric_ids,
                commerce_snapshot_ids=commerce_ids,
                attribution_evidence_ids=evidence_ids,
                prompt_revision_id=prompt_row[1].id,
                input_checksum=checksum,
                created_by=actor_id,
            )
            session.add(run)
            for item, revision, purpose in frozen_assets:
                session.add(
                    FeedbackRunRegistrySnapshot(
                        brand_id=brand_id,
                        feedback_run_id=run_id,
                        item_id=item.id,
                        revision_id=revision.id,
                        purpose=purpose,
                    )
                )
            job = Job(
                brand_id=brand_id,
                job_type=JobType.FEEDBACK_RUN,
                status=JobStatus.QUEUED,
                payload={"feedback_run_id": str(run_id)},
                idempotency_key=idempotency_key,
                max_attempts=max_attempts,
            )
            session.add(job)
            await session.flush()
            record_audit(
                session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="feedback_run.created",
                resource_type="feedback_run",
                resource_id=run.id,
                details={
                    "job_id": str(job.id),
                    "publication_count": len(publications),
                    "metric_snapshot_count": len(metrics),
                },
            )
            return run, job, [revision.id for _, revision, _ in frozen_assets]

    async def generate(
        self, *, brand_id: uuid.UUID, feedback_run_id: uuid.UUID
    ) -> tuple[uuid.UUID, uuid.UUID]:
        if self.llm_gateway is None:
            raise RuntimeError("feedback generation requires an LLM gateway")
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(FeedbackRecommendation).where(
                    FeedbackRecommendation.feedback_run_id == feedback_run_id,
                    FeedbackRecommendation.brand_id == brand_id,
                )
            )
            if existing is not None and existing.strategy_insight_revision_id is not None:
                return existing.id, existing.strategy_insight_revision_id
            run = await session.scalar(
                select(FeedbackRun).where(
                    FeedbackRun.id == feedback_run_id,
                    FeedbackRun.brand_id == brand_id,
                )
            )
            if run is None:
                raise NotFoundError("feedback run not found")
            context = await self._load_context(session, run)
            prompt = await session.get(RegistryRevision, run.prompt_revision_id)
            if prompt is None:
                raise RuntimeError("feedback prompt snapshot is missing")

        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                run_id=feedback_run_id,
                purpose="xhs_feedback",
                prompt_revision_id=prompt.id,
                temperature=0.1,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(context, ensure_ascii=False, sort_keys=True),
                    ),
                ],
            ),
            FeedbackOutput,
        )
        allowed_scope = self._allowed_scope(context["attribution_evidence"])
        self._validate_evidence_ids(result.value, context)
        output = self._govern_attribution(result.value, allowed_scope)
        output_payload = output.model_dump(mode="json")
        checksum = canonical_checksum(context)
        key = generation_key(feedback_run_id, prompt.id, checksum)
        insight_payload = StrategyInsightPayload(
            observation=output.summary,
            hypothesis=(
                output.hypotheses[0].statement
                if output.hypotheses
                else "当前数据不足以形成更具体的因果假设"
            ),
            recommended_actions=[item.action for item in output.actions],
            confidence=output.confidence,
            supporting_feedback_run_ids=[feedback_run_id],
            attribution_scope=output.attribution_scope.value,
        ).model_dump(mode="json")

        async with self.session_factory() as session, session.begin():
            existing = await session.scalar(
                select(FeedbackRecommendation).where(
                    FeedbackRecommendation.feedback_run_id == feedback_run_id
                )
            )
            if existing is not None and existing.strategy_insight_revision_id is not None:
                return existing.id, existing.strategy_insight_revision_id
            item = RegistryItem(
                brand_id=brand_id,
                registry_type=RegistryType.STRATEGY_INSIGHT,
                stable_key=f"feedback_{feedback_run_id.hex}",
            )
            session.add(item)
            await session.flush()
            insight = RegistryRevision(
                item_id=item.id,
                version=1,
                status=RevisionStatus.DRAFT,
                verification_status=VerificationStatus.PROVISIONAL,
                payload=insight_payload,
                search_text=" ".join(
                    [output.summary, *[action.action for action in output.actions]]
                ),
                source_uri=f"feedback-run:{feedback_run_id}",
                checksum=payload_checksum(insight_payload),
                created_by=run.created_by,
            )
            session.add(insight)
            await session.flush()
            recommendation = FeedbackRecommendation(
                brand_id=brand_id,
                feedback_run_id=feedback_run_id,
                recommendation=output_payload,
                confidence=Decimal(str(output.confidence)),
                attribution_scope=output.attribution_scope,
                input_checksum=checksum,
                generation_key=key,
                strategy_insight_revision_id=insight.id,
            )
            session.add(recommendation)
            if not result.telemetry_logged:
                session.add(
                    LLMCallLog(
                    brand_id=brand_id,
                    run_id=feedback_run_id,
                    provider=result.provider,
                    model=result.model,
                    purpose="xhs_feedback",
                    prompt_revision_id=prompt.id,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.latency_ms,
                    provider_request_id=result.provider_request_id,
                    )
                )
            await session.flush()
            record_audit(
                session,
                brand_id=brand_id,
                actor_id=run.created_by,
                action="feedback_recommendation.created",
                resource_type="feedback_recommendation",
                resource_id=recommendation.id,
                details={
                    "strategy_insight_revision_id": str(insight.id),
                    "attribution_scope": output.attribution_scope.value,
                },
            )
            return recommendation.id, insight.id

    async def _load_context(self, session: AsyncSession, run: FeedbackRun) -> dict:
        publication_ids = [uuid.UUID(value) for value in run.publication_ids]
        metric_ids = [uuid.UUID(value) for value in run.metric_snapshot_ids]
        commerce_ids = [uuid.UUID(value) for value in run.commerce_snapshot_ids]
        evidence_ids = [uuid.UUID(value) for value in run.attribution_evidence_ids]
        publications = list(
            await session.scalars(select(Publication).where(Publication.id.in_(publication_ids)))
        )
        versions = list(
            await session.scalars(
                select(ContentVersion).where(
                    ContentVersion.id.in_([row.content_version_id for row in publications])
                )
            )
        )
        candidates = list(
            await session.scalars(
                select(ContentCandidate).where(
                    ContentCandidate.id.in_([row.candidate_id for row in versions])
                )
            )
        )
        scores = list(
            await session.scalars(
                select(ScoreReport).where(
                    ScoreReport.content_version_id.in_([row.id for row in versions])
                )
            )
        )
        metrics = list(
            await session.scalars(
                select(MetricSnapshot)
                .where(MetricSnapshot.id.in_(metric_ids))
                .order_by(MetricSnapshot.publication_id, MetricSnapshot.captured_at)
            )
        )
        commerce = (
            list(
                await session.scalars(
                    select(CommerceSnapshot).where(CommerceSnapshot.id.in_(commerce_ids))
                )
            )
            if commerce_ids
            else []
        )
        evidence = (
            list(
                await session.scalars(
                    select(AttributionEvidence).where(
                        AttributionEvidence.id.in_(evidence_ids)
                    )
                )
            )
            if evidence_ids
            else []
        )
        by_publication: dict[uuid.UUID, list[dict]] = defaultdict(list)
        for row in metrics:
            by_publication[row.publication_id].append(
                {
                    "id": str(row.id),
                    "captured_at": row.captured_at.isoformat(),
                    **{name: getattr(row, name) for name in (
                        "impressions",
                        "views",
                        "likes",
                        "collections",
                        "comments",
                        "shares",
                        "follows",
                        "profile_visits",
                        "outbound_clicks",
                    )},
                    "is_correction": row.is_correction,
                    "corrects_snapshot_id": (
                        str(row.corrects_snapshot_id) if row.corrects_snapshot_id else None
                    ),
                }
            )
        version_by_id = {row.id: row for row in versions}
        candidate_by_id = {row.id: row for row in candidates}
        score_by_version = {row.content_version_id: row for row in scores}
        return {
            "feedback_run_id": str(run.id),
            "publications": [
                {
                    "id": str(row.id),
                    "published_at": row.published_at.isoformat(),
                    "content": version_by_id[row.content_version_id].payload,
                    "route_key": candidate_by_id[
                        version_by_id[row.content_version_id].candidate_id
                    ].route_key,
                    "internal_score": (
                        float(score_by_version[row.content_version_id].total_score)
                        if row.content_version_id in score_by_version
                        else None
                    ),
                    "metric_snapshots": by_publication[row.id],
                }
                for row in publications
            ],
            "commerce_snapshots": [
                {
                    "id": str(row.id),
                    "captured_at": row.captured_at.isoformat(),
                    "scope_type": row.scope_type,
                    "scope_key": row.scope_key,
                    "impressions": row.impressions,
                    "product_views": row.product_views,
                    "add_to_cart": row.add_to_cart,
                    "orders": row.orders,
                    "paid_orders": row.paid_orders,
                    "gmv": float(row.gmv) if row.gmv is not None else None,
                }
                for row in commerce
            ],
            "attribution_evidence": [
                {
                    "id": str(row.id),
                    "publication_id": str(row.publication_id),
                    "commerce_snapshot_id": str(row.commerce_snapshot_id),
                    "evidence_type": row.evidence_type,
                    "strength": row.strength.value,
                    "details": row.details,
                }
                for row in evidence
            ],
        }

    @staticmethod
    def _allowed_scope(evidence: list[dict]) -> AttributionStrength:
        strengths = [AttributionStrength(item["strength"]) for item in evidence]
        return max(
            strengths,
            key=lambda item: ATTRIBUTION_RANK[item],
            default=AttributionStrength.CORRELATIVE,
        )

    @staticmethod
    def _validate_evidence_ids(output: FeedbackOutput, context: dict) -> None:
        allowed_ids = {
            uuid.UUID(snapshot["id"])
            for publication in context["publications"]
            for snapshot in publication["metric_snapshots"]
        }
        allowed_ids.update(
            uuid.UUID(item["id"]) for item in context["attribution_evidence"]
        )
        cited_ids = {
            evidence_id
            for observation in output.observations
            for evidence_id in observation.evidence_ids
        }
        unknown = cited_ids - allowed_ids
        if unknown:
            raise RuntimeError(
                "feedback output cited evidence IDs outside the frozen input: "
                + ", ".join(sorted(str(value) for value in unknown))
            )

    @staticmethod
    def _govern_attribution(
        output: FeedbackOutput, allowed: AttributionStrength
    ) -> FeedbackOutput:
        if ATTRIBUTION_RANK[output.attribution_scope] > ATTRIBUTION_RANK[allowed]:
            output.attribution_scope = allowed
        for item in [*output.observations, *output.hypotheses]:
            if ATTRIBUTION_RANK[item.attribution_scope] > ATTRIBUTION_RANK[allowed]:
                item.attribution_scope = allowed
        if allowed != AttributionStrength.DIRECT:
            limitation = (
                "当前没有直接归因证据，京东变化只能解释为辅助归因或同期相关性，"
                "不得表述为该内容导致。"
            )
            if limitation not in output.limitations:
                output.limitations.append(limitation)
        return output
