from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import (
    CampaignBrief,
    ContentCandidate,
    ContentVersion,
    GrowthRun,
    HumanReview,
    Job,
    LLMCallLog,
    Publication,
    RegistryItem,
    RegistryRevision,
    RunRegistrySnapshot,
)
from smart_growth_agent.domain.enums import JobStatus, JobType, RegistryType, RunStatus
from smart_growth_agent.domain.errors import ConflictError, NotFoundError, ValidationError
from smart_growth_agent.schemas.runs import CampaignBriefCreate
from smart_growth_agent.services.audit import record_audit

GLOBAL_SNAPSHOT_TYPES = {
    RegistryType.BRAND_PROFILE,
    RegistryType.PLATFORM_RULE,
    RegistryType.PLATFORM_MARKETING_PROGRAM,
    RegistryType.CONTENT_PATTERN,
    RegistryType.STRATEGY_INSIGHT,
    RegistryType.SCORING_RUBRIC,
}
RUNTIME_PROMPT_KEYS = {
    "xhs_product_context",
    "xhs_strategy",
    "xhs_writer",
    "xhs_compliance",
    "xhs_scoring",
}


class RunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_brief(
        self, *, brand_id: uuid.UUID, data: CampaignBriefCreate, actor_id: uuid.UUID
    ) -> CampaignBrief:
        async with self.session.begin():
            await self._validate_selected_items(
                brand_id=brand_id,
                item_ids=data.product_item_ids,
                expected_type=RegistryType.PRODUCT,
            )
            await self._validate_selected_items(
                brand_id=brand_id,
                item_ids=data.audience_item_ids,
                expected_type=RegistryType.AUDIENCE,
            )
            brief = CampaignBrief(
                brand_id=brand_id,
                name=data.name,
                objective=data.objective,
                product_item_ids=[str(item_id) for item_id in data.product_item_ids],
                audience_item_ids=[str(item_id) for item_id in data.audience_item_ids],
                constraints=data.constraints.model_dump(mode="json"),
                created_by=actor_id,
            )
            self.session.add(brief)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="brief.created",
                resource_type="campaign_brief",
                resource_id=brief.id,
            )
        return brief

    async def update_brief(
        self,
        *,
        brand_id: uuid.UUID,
        brief_id: uuid.UUID,
        data: CampaignBriefCreate,
        actor_id: uuid.UUID,
    ) -> CampaignBrief:
        async with self.session.begin():
            brief = await self.session.scalar(
                select(CampaignBrief)
                .where(
                    CampaignBrief.id == brief_id,
                    CampaignBrief.brand_id == brand_id,
                    CampaignBrief.archived_at.is_(None),
                )
                .with_for_update()
            )
            if brief is None:
                raise NotFoundError("campaign brief not found")
            active_runs = await self.session.scalar(
                select(func.count(GrowthRun.id)).where(
                    GrowthRun.brief_id == brief_id,
                    GrowthRun.status.in_(
                        [
                            RunStatus.QUEUED,
                            RunStatus.RUNNING,
                            RunStatus.WAITING_HUMAN,
                            RunStatus.WAITING_KNOWLEDGE_REVIEW,
                        ]
                    ),
                )
            )
            if active_runs:
                raise ConflictError("brief cannot be edited while a run is still active")
            await self._validate_selected_items(
                brand_id=brand_id,
                item_ids=data.product_item_ids,
                expected_type=RegistryType.PRODUCT,
            )
            await self._validate_selected_items(
                brand_id=brand_id,
                item_ids=data.audience_item_ids,
                expected_type=RegistryType.AUDIENCE,
            )
            brief.name = data.name
            brief.objective = data.objective
            brief.product_item_ids = [str(item_id) for item_id in data.product_item_ids]
            brief.audience_item_ids = [str(item_id) for item_id in data.audience_item_ids]
            brief.constraints = data.constraints.model_dump(mode="json")
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="brief.updated",
                resource_type="campaign_brief",
                resource_id=brief.id,
            )
            await self.session.flush()
            await self.session.refresh(brief)
        return brief

    async def set_brief_archived(
        self,
        *,
        brand_id: uuid.UUID,
        brief_id: uuid.UUID,
        archived: bool,
        actor_id: uuid.UUID,
    ) -> CampaignBrief:
        async with self.session.begin():
            brief = await self.session.scalar(
                select(CampaignBrief)
                .where(CampaignBrief.id == brief_id, CampaignBrief.brand_id == brand_id)
                .with_for_update()
            )
            if brief is None:
                raise NotFoundError("campaign brief not found")
            if archived:
                active_runs = await self.session.scalar(
                    select(func.count(GrowthRun.id)).where(
                        GrowthRun.brief_id == brief_id,
                        GrowthRun.status.in_(
                            [
                                RunStatus.QUEUED,
                                RunStatus.RUNNING,
                                RunStatus.WAITING_HUMAN,
                                RunStatus.WAITING_KNOWLEDGE_REVIEW,
                            ]
                        ),
                    )
                )
                if active_runs:
                    raise ConflictError("brief cannot be archived while a run is still active")
            brief.archived_at = datetime.now(UTC) if archived else None
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="brief.archived" if archived else "brief.restored",
                resource_type="campaign_brief",
                resource_id=brief.id,
            )
            await self.session.flush()
            await self.session.refresh(brief)
        return brief

    async def permanently_delete_brief(
        self,
        *,
        brand_id: uuid.UUID,
        brief_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        async with self.session.begin():
            brief = await self.session.scalar(
                select(CampaignBrief)
                .where(CampaignBrief.id == brief_id, CampaignBrief.brand_id == brand_id)
                .with_for_update()
            )
            if brief is None:
                raise NotFoundError("campaign brief not found")
            if brief.archived_at is None:
                raise ConflictError("campaign brief must be in the recycle bin before deletion")
            run_count = await self.session.scalar(
                select(func.count(GrowthRun.id)).where(GrowthRun.brief_id == brief.id)
            )
            if run_count:
                raise ConflictError(
                    "campaign brief still has growth runs; permanently delete those runs first"
                )
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="brief.permanently_deleted",
                resource_type="campaign_brief",
                resource_id=brief.id,
                details={"name": brief.name},
            )
            await self.session.delete(brief)

    async def set_run_archived(
        self,
        *,
        brand_id: uuid.UUID,
        run_id: uuid.UUID,
        archived: bool,
        actor_id: uuid.UUID,
    ) -> GrowthRun:
        async with self.session.begin():
            run = await self.session.scalar(
                select(GrowthRun)
                .where(GrowthRun.id == run_id, GrowthRun.brand_id == brand_id)
                .with_for_update()
            )
            if run is None:
                raise NotFoundError("growth run not found")
            if archived and run.status in {
                RunStatus.QUEUED,
                RunStatus.RUNNING,
                RunStatus.WAITING_HUMAN,
                RunStatus.WAITING_KNOWLEDGE_REVIEW,
            }:
                raise ConflictError("active growth run cannot be archived")
            run.archived_at = datetime.now(UTC) if archived else None
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="growth_run.archived" if archived else "growth_run.restored",
                resource_type="growth_run",
                resource_id=run.id,
            )
            await self.session.flush()
            await self.session.refresh(run)
        return run

    async def permanently_delete_run(
        self,
        *,
        brand_id: uuid.UUID,
        run_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        async with self.session.begin():
            run = await self.session.scalar(
                select(GrowthRun)
                .where(GrowthRun.id == run_id, GrowthRun.brand_id == brand_id)
                .with_for_update()
            )
            if run is None:
                raise NotFoundError("growth run not found")
            if run.archived_at is None:
                raise ConflictError("growth run must be in the recycle bin before deletion")
            publication_count = await self.session.scalar(
                select(func.count(Publication.id))
                .join(ContentVersion, ContentVersion.id == Publication.content_version_id)
                .join(ContentCandidate, ContentCandidate.id == ContentVersion.candidate_id)
                .where(ContentCandidate.run_id == run.id)
            )
            if publication_count:
                raise ConflictError(
                    "growth run has publication or metric history and cannot be permanently deleted"
                )
            jobs = list(
                await self.session.scalars(
                    select(Job).where(
                        Job.brand_id == brand_id,
                        Job.job_type == JobType.GROWTH_RUN,
                    )
                )
            )
            for job in jobs:
                if job.payload.get("run_id") == str(run.id):
                    await self.session.delete(job)
            await self.session.execute(
                delete(HumanReview).where(
                    HumanReview.brand_id == brand_id,
                    HumanReview.run_id == run.id,
                )
            )
            await self.session.execute(
                delete(LLMCallLog).where(
                    LLMCallLog.brand_id == brand_id,
                    LLMCallLog.run_id == run.id,
                )
            )
            if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
                for table_name in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    await self.session.execute(
                        text(f"DELETE FROM {table_name} WHERE thread_id = :thread_id"),
                        {"thread_id": run.thread_id},
                    )
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="growth_run.permanently_deleted",
                resource_type="growth_run",
                resource_id=run.id,
                details={"brief_id": str(run.brief_id)},
            )
            await self.session.delete(run)

    async def create_growth_run(
        self,
        *,
        brand_id: uuid.UUID,
        brief_id: uuid.UUID,
        actor_id: uuid.UUID,
        idempotency_key: str,
        max_attempts: int,
    ) -> tuple[GrowthRun, Job, list[uuid.UUID]]:
        async with self.session.begin():
            existing_job = await self.session.scalar(
                select(Job).where(Job.brand_id == brand_id, Job.idempotency_key == idempotency_key)
            )
            if existing_job is not None:
                existing_run_id = uuid.UUID(existing_job.payload["run_id"])
                existing_run = await self.session.get(GrowthRun, existing_run_id)
                if existing_run is None or existing_run.brand_id != brand_id:
                    raise ConflictError("idempotency key is attached to an invalid run")
                revision_ids = list(
                    await self.session.scalars(
                        select(RunRegistrySnapshot.revision_id).where(
                            RunRegistrySnapshot.run_id == existing_run.id
                        )
                    )
                )
                return existing_run, existing_job, revision_ids

            brief = await self.session.scalar(
                select(CampaignBrief).where(
                    CampaignBrief.id == brief_id, CampaignBrief.brand_id == brand_id
                )
            )
            if brief is None:
                raise NotFoundError("campaign brief not found")
            if brief.archived_at is not None:
                raise ConflictError("archived campaign brief cannot start a new run")

            selected_product_ids = {uuid.UUID(value) for value in brief.product_item_ids}
            selected_audience_ids = {uuid.UUID(value) for value in brief.audience_item_ids}
            active_rows = list(
                (
                    await self.session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(
                            RegistryRevision,
                            RegistryRevision.id == RegistryItem.current_revision_id,
                        )
                        .where(RegistryItem.brand_id == brand_id)
                        .where(RegistryItem.archived_at.is_(None))
                    )
                ).all()
            )
            snapshots: list[tuple[RegistryItem, RegistryRevision, str]] = []
            found_products: set[uuid.UUID] = set()
            found_audiences: set[uuid.UUID] = set()
            for item, revision in active_rows:
                purpose: str | None = None
                if item.id in selected_product_ids and item.registry_type == RegistryType.PRODUCT:
                    purpose = "selected_product"
                    found_products.add(item.id)
                elif (
                    item.id in selected_audience_ids and item.registry_type == RegistryType.AUDIENCE
                ):
                    purpose = "selected_audience"
                    found_audiences.add(item.id)
                elif item.registry_type == RegistryType.PRODUCT_CLAIM:
                    claim_products = {
                        uuid.UUID(value) for value in revision.payload.get("product_item_ids", [])
                    }
                    if claim_products & selected_product_ids:
                        purpose = "product_claim"
                elif item.registry_type == RegistryType.PLATFORM_RULE:
                    if revision.payload.get("platform") == brief.constraints.get(
                        "platform", "xhs"
                    ):
                        purpose = "active_context"
                elif item.registry_type in GLOBAL_SNAPSHOT_TYPES or (
                    item.registry_type == RegistryType.PROMPT_TEMPLATE
                    and item.stable_key in RUNTIME_PROMPT_KEYS
                ):
                    purpose = "active_context"
                if purpose:
                    snapshots.append((item, revision, purpose))

            if found_products != selected_product_ids:
                raise ValidationError("all brief products must still have an active revision")
            if found_audiences != selected_audience_ids:
                raise ValidationError("all brief audiences must still have an active revision")

            run_id = uuid.uuid4()
            run = GrowthRun(
                id=run_id,
                brand_id=brand_id,
                brief_id=brief.id,
                thread_id=str(run_id),
                status=RunStatus.QUEUED,
                gate_status="pending",
                created_by=actor_id,
            )
            self.session.add(run)
            for item, revision, purpose in snapshots:
                self.session.add(
                    RunRegistrySnapshot(
                        brand_id=brand_id,
                        run_id=run_id,
                        item_id=item.id,
                        revision_id=revision.id,
                        purpose=purpose,
                    )
                )
            job = Job(
                brand_id=brand_id,
                job_type=JobType.GROWTH_RUN,
                status=JobStatus.QUEUED,
                payload={"run_id": str(run_id)},
                idempotency_key=idempotency_key,
                max_attempts=max_attempts,
            )
            self.session.add(job)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="growth_run.created",
                resource_type="growth_run",
                resource_id=run.id,
                details={
                    "job_id": str(job.id),
                    "registry_revision_count": len(snapshots),
                },
            )
        return run, job, [revision.id for _, revision, _ in snapshots]

    async def get_growth_run(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[GrowthRun, Job | None, list[uuid.UUID]]:
        run = await self.session.scalar(
            select(GrowthRun).where(GrowthRun.id == run_id, GrowthRun.brand_id == brand_id)
        )
        if run is None:
            raise NotFoundError("growth run not found")
        job = await self.session.scalar(
            select(Job).where(
                Job.brand_id == brand_id,
                Job.job_type == JobType.GROWTH_RUN,
                Job.payload["run_id"].as_string() == str(run_id),
            )
        )
        revision_ids = list(
            await self.session.scalars(
                select(RunRegistrySnapshot.revision_id).where(RunRegistrySnapshot.run_id == run_id)
            )
        )
        return run, job, revision_ids

    async def _validate_selected_items(
        self,
        *,
        brand_id: uuid.UUID,
        item_ids: list[uuid.UUID],
        expected_type: RegistryType,
    ) -> None:
        if not item_ids:
            return
        items = list(
            await self.session.scalars(
                select(RegistryItem).where(
                    RegistryItem.brand_id == brand_id,
                    RegistryItem.id.in_(item_ids),
                    RegistryItem.registry_type == expected_type,
                    RegistryItem.current_revision_id.is_not(None),
                    RegistryItem.archived_at.is_(None),
                )
            )
        )
        if len(items) != len(set(item_ids)):
            raise ValidationError(
                f"all selected {expected_type.value} items must be active in the same brand"
            )
