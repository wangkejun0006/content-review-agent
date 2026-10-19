from __future__ import annotations

import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import Job, WorkerHeartbeat
from smart_growth_agent.domain.enums import JobStatus


class JobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def claim_next(self, *, worker_id: str, lease_seconds: int) -> Job | None:
        now = datetime.now(UTC)
        async with self.session_factory() as session, session.begin():
            job = await session.scalar(
                select(Job)
                .where(
                    Job.attempts < Job.max_attempts,
                    or_(
                        Job.status == JobStatus.QUEUED,
                        (Job.status == JobStatus.RUNNING) & (Job.lease_until < now),
                    ),
                )
                .order_by(Job.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status = JobStatus.RUNNING
            job.attempts += 1
            job.worker_id = worker_id
            job.lease_until = now + timedelta(seconds=lease_seconds)
            await session.flush()
            session.expunge(job)
            return job

    async def heartbeat(
        self,
        *,
        worker_id: str,
        started_at: datetime,
        status: str,
        current_job_id: uuid.UUID | None,
    ) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session, session.begin():
            row = await session.scalar(
                select(WorkerHeartbeat)
                .where(WorkerHeartbeat.worker_id == worker_id)
                .with_for_update()
            )
            if row is None:
                row = WorkerHeartbeat(
                    worker_id=worker_id,
                    hostname=socket.gethostname(),
                    process_id=os.getpid(),
                    status=status,
                    current_job_id=current_job_id,
                    started_at=started_at,
                    last_seen_at=now,
                )
                session.add(row)
            else:
                row.status = status
                row.current_job_id = current_job_id
                row.last_seen_at = now
                row.process_id = os.getpid()
            await session.execute(
                delete(WorkerHeartbeat).where(
                    WorkerHeartbeat.worker_id != worker_id,
                    WorkerHeartbeat.last_seen_at < now - timedelta(days=30),
                )
            )

    async def mark_stopped(self, *, worker_id: str) -> None:
        async with self.session_factory() as session, session.begin():
            row = await session.scalar(
                select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id)
            )
            if row is not None:
                row.status = "stopped"
                row.current_job_id = None
                row.last_seen_at = datetime.now(UTC)
