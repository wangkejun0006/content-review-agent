from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import (
    AuditEvent,
    Brand,
    CampaignBrief,
    GrowthRun,
    Job,
    User,
    WorkerHeartbeat,
)
from smart_growth_agent.domain.enums import JobStatus, JobType, RunStatus
from smart_growth_agent.domain.errors import ConflictError
from smart_growth_agent.services.operations import OperationsService
from smart_growth_agent.worker import Worker


async def _failed_growth_job(session_factory):
    async with session_factory() as session, session.begin():
        brand = Brand(name="Operations Brand", slug="operations-brand")
        user = User(
            email="operations@example.com",
            password_hash="unused",
            display_name="Operations",
        )
        session.add_all([brand, user])
        await session.flush()
        brief = CampaignBrief(
            brand_id=brand.id,
            name="失败任务",
            objective="测试重试",
            product_item_ids=[],
            audience_item_ids=[],
            constraints={},
            created_by=user.id,
        )
        session.add(brief)
        await session.flush()
        run = GrowthRun(
            brand_id=brand.id,
            brief_id=brief.id,
            thread_id="operations-failed-run",
            status=RunStatus.FAILED,
            gate_status="failed",
            error={"message": "provider timeout"},
            created_by=user.id,
        )
        session.add(run)
        await session.flush()
        job = Job(
            brand_id=brand.id,
            job_type=JobType.GROWTH_RUN,
            status=JobStatus.FAILED,
            payload={"run_id": str(run.id)},
            idempotency_key="operations-failed-job",
            attempts=3,
            max_attempts=3,
            last_error={"message": "provider timeout"},
        )
        session.add(job)
        await session.flush()
        return brand.id, user.id, run.id, job.id


@pytest.mark.asyncio
async def test_operations_status_reports_worker_and_brand_queue(session_factory) -> None:
    brand_id, _user_id, _run_id, job_id = await _failed_growth_job(session_factory)
    async with session_factory() as session, session.begin():
        session.add(
            WorkerHeartbeat(
                worker_id="worker-status-test",
                hostname="test-host",
                process_id=123,
                status="idle",
                current_job_id=None,
                started_at=datetime.now(UTC) - timedelta(minutes=2),
                last_seen_at=datetime.now(UTC),
            )
        )

    async with session_factory() as session:
        status = await OperationsService(
            session,
            Settings(worker_stale_seconds=20),
        ).get_status(brand_id=brand_id)

    assert status.worker.online is True
    assert status.worker.worker_id == "worker-status-test"
    assert status.queue.failed == 1
    assert status.failed_jobs[0].id == job_id


@pytest.mark.asyncio
async def test_manual_retry_resets_failed_growth_job_and_audits(session_factory) -> None:
    brand_id, user_id, run_id, job_id = await _failed_growth_job(session_factory)

    async with session_factory() as session:
        retried = await OperationsService(session, Settings()).retry_failed_job(
            brand_id=brand_id,
            job_id=job_id,
            actor_id=user_id,
        )

    assert retried.status == JobStatus.QUEUED
    assert retried.attempts == 0
    assert retried.manual_retries == 1
    assert retried.last_error is None
    async with session_factory() as session:
        run = await session.get(GrowthRun, run_id)
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.action == "job.manually_retried")
        )
        assert run is not None and run.status == RunStatus.QUEUED
        assert run.error is None
        assert event is not None
        assert event.details["previous_error"]["message"] == "provider timeout"

    async with session_factory() as session:
        with pytest.raises(ConflictError, match="only failed jobs"):
            await OperationsService(session, Settings()).retry_failed_job(
                brand_id=brand_id,
                job_id=job_id,
                actor_id=user_id,
            )


@pytest.mark.asyncio
async def test_worker_once_persists_stopped_heartbeat(session_factory) -> None:
    worker = Worker(
        graph=None,
        worker_id="once-heartbeat-test",
        session_factory=session_factory,
    )
    await worker.run_forever(once=True)

    async with session_factory() as session:
        heartbeat = await session.scalar(
            select(WorkerHeartbeat).where(
                WorkerHeartbeat.worker_id == "once-heartbeat-test"
            )
        )
        assert heartbeat is not None
        assert heartbeat.status == "stopped"
        assert heartbeat.current_job_id is None
