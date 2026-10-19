from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import FeedbackRun, GrowthRun, Job, WorkerHeartbeat
from smart_growth_agent.domain.enums import FeedbackRunStatus, JobStatus, JobType, RunStatus
from smart_growth_agent.domain.errors import ConflictError, NotFoundError
from smart_growth_agent.schemas.operations import (
    OperationalJobRead,
    OperationsStatusRead,
    QueueStatusRead,
    WorkerStatusRead,
)
from smart_growth_agent.services.audit import record_audit


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _related_resource_id(job: Job) -> uuid.UUID | None:
    value = (
        job.payload.get("run_id")
        if job.job_type == JobType.GROWTH_RUN
        else job.payload.get("feedback_run_id")
    )
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _job_read(job: Job) -> OperationalJobRead:
    return OperationalJobRead(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        manual_retries=job.manual_retries,
        related_resource_id=_related_resource_id(job),
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


class OperationsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def get_status(self, *, brand_id: uuid.UUID) -> OperationsStatusRead:
        now = datetime.now(UTC)
        heartbeat = await self.session.scalar(
            select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()).limit(1)
        )
        online = bool(
            heartbeat
            and heartbeat.status != "stopped"
            and _as_utc(heartbeat.last_seen_at)
            >= now - timedelta(seconds=self.settings.worker_stale_seconds)
        )
        count_row = (
            await self.session.execute(
                select(
                    *[
                        func.sum(case((Job.status == status, 1), else_=0)).label(status.value)
                        for status in JobStatus
                    ]
                ).where(Job.brand_id == brand_id)
            )
        ).one()
        failed_jobs = list(
            await self.session.scalars(
                select(Job)
                .where(Job.brand_id == brand_id, Job.status == JobStatus.FAILED)
                .order_by(Job.updated_at.desc())
                .limit(20)
            )
        )
        return OperationsStatusRead(
            checked_at=now,
            worker=WorkerStatusRead(
                online=online,
                worker_id=heartbeat.worker_id if heartbeat else None,
                hostname=heartbeat.hostname if heartbeat else None,
                process_id=heartbeat.process_id if heartbeat else None,
                status=(heartbeat.status if heartbeat else "missing"),
                current_job_id=heartbeat.current_job_id if heartbeat else None,
                started_at=heartbeat.started_at if heartbeat else None,
                last_seen_at=heartbeat.last_seen_at if heartbeat else None,
                stale_after_seconds=self.settings.worker_stale_seconds,
            ),
            queue=QueueStatusRead(
                **{status.value: int(getattr(count_row, status.value) or 0) for status in JobStatus}
            ),
            failed_jobs=[_job_read(job) for job in failed_jobs],
        )

    async def retry_failed_job(
        self,
        *,
        brand_id: uuid.UUID,
        job_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> OperationalJobRead:
        async with self.session.begin():
            job = await self.session.scalar(
                select(Job)
                .where(Job.id == job_id, Job.brand_id == brand_id)
                .with_for_update()
            )
            if job is None:
                raise NotFoundError("job not found")
            if job.status != JobStatus.FAILED:
                raise ConflictError("only failed jobs can be manually retried")
            previous_error = job.last_error
            resource_id = _related_resource_id(job)
            if resource_id is None:
                raise ConflictError("job has no valid related resource")
            if job.job_type == JobType.GROWTH_RUN:
                run = await self.session.scalar(
                    select(GrowthRun)
                    .where(GrowthRun.id == resource_id, GrowthRun.brand_id == brand_id)
                    .with_for_update()
                )
                if run is None:
                    raise NotFoundError("growth run not found")
                if run.archived_at is not None:
                    raise ConflictError("restore the growth run before retrying its job")
                run.status = RunStatus.QUEUED
                run.error = None
            elif job.job_type == JobType.FEEDBACK_RUN:
                feedback_run = await self.session.scalar(
                    select(FeedbackRun)
                    .where(FeedbackRun.id == resource_id, FeedbackRun.brand_id == brand_id)
                    .with_for_update()
                )
                if feedback_run is None:
                    raise NotFoundError("feedback run not found")
                feedback_run.status = FeedbackRunStatus.QUEUED
                feedback_run.error = None
            job.status = JobStatus.QUEUED
            job.attempts = 0
            job.manual_retries += 1
            job.lease_until = None
            job.worker_id = None
            job.last_error = None
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="job.manually_retried",
                resource_type=job.job_type.value,
                resource_id=resource_id,
                details={
                    "job_id": str(job.id),
                    "manual_retries": job.manual_retries,
                    "previous_error": previous_error,
                },
            )
            await self.session.flush()
            await self.session.refresh(job)
        return _job_read(job)
