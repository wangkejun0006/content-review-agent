from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import (
    ComplianceReport,
    ContentCandidate,
    ContentVersion,
    GrowthRun,
    HumanReview,
    Job,
)
from smart_growth_agent.domain.enums import JobStatus, JobType, ReviewDecision, RunStatus
from smart_growth_agent.domain.errors import ConflictError, NotFoundError, ValidationError
from smart_growth_agent.schemas.reviews import HumanReviewCreate
from smart_growth_agent.services.audit import record_audit


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def submit(
        self,
        *,
        brand_id: uuid.UUID,
        run_id: uuid.UUID,
        data: HumanReviewCreate,
        reviewer_id: uuid.UUID,
        idempotency_key: str,
    ) -> HumanReview:
        async with self.session.begin():
            existing = await self.session.scalar(
                select(HumanReview).where(
                    HumanReview.brand_id == brand_id,
                    HumanReview.idempotency_key == idempotency_key,
                )
            )
            payload = data.model_dump(mode="json")
            if existing is not None:
                if existing.run_id != run_id or existing.payload != payload:
                    raise ConflictError("idempotency key is attached to a different review")
                return existing

            run = await self.session.scalar(
                select(GrowthRun)
                .where(GrowthRun.id == run_id, GrowthRun.brand_id == brand_id)
                .with_for_update()
            )
            if run is None:
                raise NotFoundError("growth run not found")
            job = await self.session.scalar(
                select(Job)
                .where(
                    Job.brand_id == brand_id,
                    Job.job_type == JobType.GROWTH_RUN,
                    Job.payload["run_id"].as_string() == str(run_id),
                )
                .with_for_update()
            )
            if run.status != RunStatus.WAITING_HUMAN or job is None:
                raise ConflictError("growth run is not waiting for human review")
            if job.status != JobStatus.WAITING_HUMAN:
                raise ConflictError("growth run job is not waiting for human review")
            content_version_id = None
            if data.selected_candidate_id is not None:
                candidate = await self.session.scalar(
                    select(ContentCandidate).where(
                        ContentCandidate.id == data.selected_candidate_id,
                        ContentCandidate.brand_id == brand_id,
                        ContentCandidate.run_id == run_id,
                    )
                )
                if candidate is None:
                    raise ValidationError("selected candidate does not belong to this run")
                version = await self.session.scalar(
                    select(ContentVersion).where(
                        ContentVersion.candidate_id == candidate.id,
                        ContentVersion.version == candidate.current_version,
                    )
                )
                if version is None:
                    raise ValidationError("selected candidate current version is missing")
                content_version_id = version.id
                if data.decision == ReviewDecision.APPROVED:
                    report = await self.session.scalar(
                        select(ComplianceReport).where(
                            ComplianceReport.content_version_id == version.id
                        )
                    )
                    if report is None or report.has_blockers or not report.semantic_pass:
                        raise ValidationError("a blocked candidate cannot be approved")

            review = HumanReview(
                brand_id=brand_id,
                run_id=run_id,
                reviewer_id=reviewer_id,
                decision=data.decision.value,
                selected_candidate_id=data.selected_candidate_id,
                content_version_id=content_version_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
            self.session.add(review)
            await self.session.flush()
            job.payload = {
                **job.payload,
                "resume": {
                    "review_id": str(review.id),
                    "decision": data.decision.value,
                    "selected_candidate_id": (
                        str(data.selected_candidate_id)
                        if data.selected_candidate_id is not None
                        else None
                    ),
                },
            }
            # A human decision starts a new execution segment. The content-generation
            # segment may legitimately have consumed every retry before reaching the
            # interrupt, so carrying that counter forward can make the queued resume
            # permanently unclaimable (`attempts < max_attempts`).
            job.attempts = 0
            job.last_error = None
            job.status = JobStatus.QUEUED
            job.lease_until = None
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=reviewer_id,
                action="growth_run.review_submitted",
                resource_type="human_review",
                resource_id=review.id,
                details={"run_id": str(run_id), "decision": data.decision.value},
            )
            return review
