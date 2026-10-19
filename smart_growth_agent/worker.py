from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import socket
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.config import get_settings
from smart_growth_agent.db.models import (
    FeedbackRun,
    FeedbackRunRegistrySnapshot,
    GrowthRun,
    Job,
    RunRegistrySnapshot,
)
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.domain.enums import (
    FeedbackRunStatus,
    JobStatus,
    JobType,
    RunStatus,
)
from smart_growth_agent.graph.feedback_graph import build_feedback_graph
from smart_growth_agent.graph.feedback_state import FeedbackState
from smart_growth_agent.graph.growth_graph import build_growth_graph
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.llm.unavailable import UnavailableLLMGateway
from smart_growth_agent.repositories.jobs import JobRepository
from smart_growth_agent.research.gateway import NullResearchGateway

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        graph: Any,
        worker_id: str,
        session_factory: async_sessionmaker[AsyncSession] = SessionFactory,
        runtime_context: GrowthRuntimeContext | None = None,
        feedback_graph: Any | None = None,
    ) -> None:
        self.graph = graph
        self.feedback_graph = feedback_graph
        self.worker_id = worker_id
        self.settings = get_settings()
        self.session_factory = session_factory
        self.runtime_context = runtime_context or GrowthRuntimeContext(
            session_factory=session_factory,
            llm_gateway=UnavailableLLMGateway(),
            research_gateway=NullResearchGateway(),
        )
        self.jobs = JobRepository(session_factory)
        self.started_at = datetime.now(UTC)
        self.current_job_id: uuid.UUID | None = None

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.worker_heartbeat_seconds)
            try:
                await self.jobs.heartbeat(
                    worker_id=self.worker_id,
                    started_at=self.started_at,
                    status="busy" if self.current_job_id is not None else "idle",
                    current_job_id=self.current_job_id,
                )
            except Exception:
                logger.exception("worker heartbeat update failed")

    async def run_forever(self, *, once: bool = False) -> None:
        await self.jobs.heartbeat(
            worker_id=self.worker_id,
            started_at=self.started_at,
            status="idle",
            current_job_id=None,
        )
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        try:
            while True:
                job = await self.jobs.claim_next(
                    worker_id=self.worker_id, lease_seconds=self.settings.job_lease_seconds
                )
                if job is None:
                    if once:
                        return
                    await asyncio.sleep(self.settings.worker_poll_seconds)
                    continue
                self.current_job_id = job.id
                await self.jobs.heartbeat(
                    worker_id=self.worker_id,
                    started_at=self.started_at,
                    status="busy",
                    current_job_id=job.id,
                )
                await self.execute(job)
                self.current_job_id = None
                await self.jobs.heartbeat(
                    worker_id=self.worker_id,
                    started_at=self.started_at,
                    status="idle",
                    current_job_id=None,
                )
                if once:
                    return
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            with contextlib.suppress(Exception):
                await self.jobs.mark_stopped(worker_id=self.worker_id)

    async def execute(self, job: Job) -> None:
        try:
            if job.job_type == JobType.GROWTH_RUN:
                await self._execute_growth_run(job)
            elif job.job_type == JobType.FEEDBACK_RUN:
                await self._execute_feedback_run(job)
            else:
                raise RuntimeError(f"unsupported job type: {job.job_type}")
        except Exception as exc:
            await self._mark_failed(job.id, exc)

    async def _execute_growth_run(self, job: Job) -> None:
        run_id = uuid.UUID(job.payload["run_id"])
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(GrowthRun).where(GrowthRun.id == run_id, GrowthRun.brand_id == job.brand_id)
            )
            if run is None:
                raise RuntimeError("growth run not found")
            run.status = RunStatus.RUNNING
            revisions = list(
                await session.scalars(
                    select(RunRegistrySnapshot.revision_id).where(
                        RunRegistrySnapshot.run_id == run.id
                    )
                )
            )
            state: GrowthState = {
                "run_id": run.id,
                "thread_id": run.thread_id,
                "brand_id": run.brand_id,
                "brief_id": run.brief_id,
                "registry_revision_ids": revisions,
                "candidate_ids": [],
                "candidate_refs": {},
                "creative_route_keys": [],
                "iteration_by_candidate": {},
                "compliance_report_ids": {},
                "reviewed_version_ids": {},
                "score_report_ids": {},
                "ranked_candidate_ids": [],
                "errors": [],
            }
            thread_id = run.thread_id

        resume = job.payload.get("resume")
        graph_input = Command(resume=resume) if resume is not None else state
        result = await self.graph.ainvoke(
            graph_input,
            config={"configurable": {"thread_id": thread_id}},
            context=self.runtime_context,
        )
        async with self.session_factory() as session, session.begin():
            run = await session.get(GrowthRun, run_id)
            persisted_job = await session.get(Job, job.id)
            assert run is not None and persisted_job is not None
            run.gate_status = result["gate_status"]
            run.recommended_candidate_id = result.get("recommended_candidate_id")
            run.selected_candidate_id = result.get("selected_candidate_id")
            if result["gate_status"] == "waiting_knowledge_review":
                run.status = RunStatus.WAITING_KNOWLEDGE_REVIEW
                persisted_job.status = JobStatus.WAITING_HUMAN
            elif result["gate_status"] == "waiting_human_review":
                run.status = RunStatus.WAITING_HUMAN
                persisted_job.status = JobStatus.WAITING_HUMAN
            elif result["gate_status"] == "ready_for_manual_publish":
                run.status = RunStatus.READY_FOR_MANUAL_PUBLISH
                persisted_job.status = JobStatus.SUCCEEDED
            elif result["gate_status"] == "rejected":
                run.status = RunStatus.REJECTED
                persisted_job.status = JobStatus.SUCCEEDED
            else:
                raise RuntimeError("growth graph ended at an unsupported gate")
            persisted_job.lease_until = None

    async def _execute_feedback_run(self, job: Job) -> None:
        if self.feedback_graph is None:
            raise RuntimeError("feedback graph is not configured")
        feedback_run_id = uuid.UUID(job.payload["feedback_run_id"])
        async with self.session_factory() as session, session.begin():
            run = await session.scalar(
                select(FeedbackRun).where(
                    FeedbackRun.id == feedback_run_id,
                    FeedbackRun.brand_id == job.brand_id,
                )
            )
            if run is None:
                raise RuntimeError("feedback run not found")
            run.status = FeedbackRunStatus.RUNNING
            revisions = list(
                await session.scalars(
                    select(FeedbackRunRegistrySnapshot.revision_id).where(
                        FeedbackRunRegistrySnapshot.feedback_run_id == run.id
                    )
                )
            )
            state: FeedbackState = {
                "feedback_run_id": run.id,
                "thread_id": run.thread_id,
                "brand_id": run.brand_id,
                "publication_ids": [uuid.UUID(value) for value in run.publication_ids],
                "metric_snapshot_ids": [
                    uuid.UUID(value) for value in run.metric_snapshot_ids
                ],
                "commerce_snapshot_ids": [
                    uuid.UUID(value) for value in run.commerce_snapshot_ids
                ],
                "attribution_evidence_ids": [
                    uuid.UUID(value) for value in run.attribution_evidence_ids
                ],
                "registry_revision_ids": revisions,
                "errors": [],
            }
            thread_id = run.thread_id

        result = await self.feedback_graph.ainvoke(
            state,
            config={"configurable": {"thread_id": thread_id}},
            context=self.runtime_context,
        )
        if result.get("gate_status") != "feedback_ready":
            raise RuntimeError("feedback graph ended at an unsupported gate")
        async with self.session_factory() as session, session.begin():
            run = await session.get(FeedbackRun, feedback_run_id)
            persisted_job = await session.get(Job, job.id)
            assert run is not None and persisted_job is not None
            run.status = FeedbackRunStatus.SUCCEEDED
            run.error = None
            persisted_job.status = JobStatus.SUCCEEDED
            persisted_job.lease_until = None

    async def _mark_failed(self, job_id: uuid.UUID, exc: Exception) -> None:
        async with self.session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return
            job.last_error = {"type": type(exc).__name__, "message": str(exc)}
            job.lease_until = None
            if job.attempts < job.max_attempts:
                job.status = JobStatus.QUEUED
            else:
                job.status = JobStatus.FAILED
                if job.job_type == JobType.GROWTH_RUN:
                    run = await session.get(GrowthRun, uuid.UUID(job.payload["run_id"]))
                    if run is not None:
                        run.status = RunStatus.FAILED
                        run.error = job.last_error
                elif job.job_type == JobType.FEEDBACK_RUN:
                    run = await session.get(
                        FeedbackRun, uuid.UUID(job.payload["feedback_run_id"])
                    )
                    if run is not None:
                        run.status = FeedbackRunStatus.FAILED
                        run.error = job.last_error


async def async_main(*, once: bool = False) -> None:
    settings = get_settings()
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    llm_gateway = build_llm_gateway(settings, SessionFactory)
    runtime_context = GrowthRuntimeContext(
        session_factory=SessionFactory,
        llm_gateway=llm_gateway,
        research_gateway=NullResearchGateway(),
    )
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as saver:
        await saver.setup()
        graph = build_growth_graph(saver)
        feedback_graph = build_feedback_graph(saver)
        try:
            await Worker(
                graph,
                worker_id,
                runtime_context=runtime_context,
                feedback_graph=feedback_graph,
            ).run_forever(once=once)
        finally:
            if hasattr(llm_gateway, "aclose"):
                await llm_gateway.aclose()


def run() -> None:
    parser = argparse.ArgumentParser(description="Smart Growth PostgreSQL job worker")
    parser.add_argument("--once", action="store_true", help="process at most one job")
    args = parser.parse_args()
    asyncio.run(async_main(once=args.once))


if __name__ == "__main__":
    run()
