from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from smart_growth_agent.app.api.feedback import list_feedback_runs
from smart_growth_agent.db.models import (
    FeedbackRecommendation,
    FeedbackRun,
    Job,
    RegistryItem,
    RegistryRevision,
)
from smart_growth_agent.domain.enums import (
    AttributionStrength,
    FeedbackRunStatus,
    JobStatus,
    RegistryType,
    RevisionStatus,
    Role,
)
from smart_growth_agent.graph.feedback_graph import build_feedback_graph
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.llm.fake import DevelopmentFakeLLMGateway
from smart_growth_agent.repositories.jobs import JobRepository
from smart_growth_agent.research.gateway import NullResearchGateway
from smart_growth_agent.schemas.analytics import MetricSnapshotCreate, PublicationCreate
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.feedback import FeedbackOutput, FeedbackRunCreate
from smart_growth_agent.schemas.registry import RegistryItemCreate
from smart_growth_agent.services.analytics import AnalyticsService
from smart_growth_agent.services.feedback import FeedbackService
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.worker import Worker
from tests.test_analytics import _seed_selected_content


@pytest.mark.asyncio
async def test_list_feedback_runs_is_brand_scoped(session_factory) -> None:
    brand_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        expected = FeedbackRun(
            brand_id=brand_id,
            thread_id=str(uuid.uuid4()),
            status=FeedbackRunStatus.QUEUED,
            publication_ids=[str(uuid.uuid4())],
            metric_snapshot_ids=[str(uuid.uuid4())],
            commerce_snapshot_ids=[],
            attribution_evidence_ids=[],
            created_by=actor_id,
        )
        session.add_all(
            [
                expected,
                FeedbackRun(
                    brand_id=uuid.uuid4(),
                    thread_id=str(uuid.uuid4()),
                    status=FeedbackRunStatus.QUEUED,
                    publication_ids=[str(uuid.uuid4())],
                    metric_snapshot_ids=[str(uuid.uuid4())],
                    commerce_snapshot_ids=[],
                    attribution_evidence_ids=[],
                    created_by=actor_id,
                ),
            ]
        )

    async with session_factory() as session:
        rows = await list_feedback_runs(
            session=session,
            principal=Principal(
                user_id=actor_id,
                brand_id=brand_id,
                role=Role.ADMIN,
                email="admin@example.com",
            ),
        )
    assert [row.id for row in rows] == [expected.id]
    assert rows[0].recommendation_id is None
    assert rows[0].job_id is None


def test_feedback_rejects_evidence_ids_outside_frozen_input() -> None:
    output = FeedbackOutput(
        summary="测试",
        observations=[
            {
                "statement": "编造引用",
                "evidence_ids": [uuid.uuid4()],
                "confidence": 0.5,
            }
        ],
        actions=[
            {
                "action": "继续测试",
                "rationale": "验证假设",
                "priority": "low",
                "expected_signal": "互动变化",
            }
        ],
        confidence=0.5,
        attribution_scope=AttributionStrength.CORRELATIVE,
    )
    with pytest.raises(RuntimeError, match="outside the frozen input"):
        FeedbackService._validate_evidence_ids(
            output,
            {
                "publications": [{"metric_snapshots": []}],
                "attribution_evidence": [],
            },
        )


@pytest.mark.asyncio
async def test_feedback_worker_creates_governed_draft_insight(session_factory) -> None:
    brand_id, actor_id, version_id = await _seed_selected_content(session_factory)
    published_at = datetime.now(UTC) - timedelta(days=3)
    async with session_factory() as session:
        publication = await AnalyticsService(session).create_publication(
            brand_id=brand_id,
            actor_id=actor_id,
            data=PublicationCreate(
                content_version_id=version_id,
                platform_content_id="feedback-note",
                url="https://www.xiaohongshu.com/explore/feedback-note",
                published_at=published_at,
            ),
        )
        await AnalyticsService(session).create_metric_snapshot(
            brand_id=brand_id,
            publication_id=publication.id,
            actor_id=actor_id,
            data=MetricSnapshotCreate(
                captured_at=published_at + timedelta(days=1),
                views=100,
                likes=10,
            ),
        )
        await AnalyticsService(session).create_metric_snapshot(
            brand_id=brand_id,
            publication_id=publication.id,
            actor_id=actor_id,
            data=MetricSnapshotCreate(
                captured_at=published_at + timedelta(days=2),
                views=180,
                likes=22,
            ),
        )
        publication_id = publication.id

    async with session_factory() as session:
        registry = RegistryService(session)
        _item, prompt = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PROMPT_TEMPLATE,
            actor_id=actor_id,
            data=RegistryItemCreate(
                stable_key="xhs_feedback",
                payload={
                    "purpose": "xhs_feedback",
                    "template": "Return governed feedback JSON.",
                    "variables": [],
                    "output_schema_name": "FeedbackOutput",
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id,
            revision_id=prompt.id,
            actor_id=actor_id,
        )

    run, job, revision_ids = await FeedbackService(session_factory).create_run(
        brand_id=brand_id,
        actor_id=actor_id,
        data=FeedbackRunCreate(publication_ids=[publication_id]),
        idempotency_key="feedback-test-key",
        max_attempts=3,
    )
    assert len(run.metric_snapshot_ids) == 2
    assert prompt.id in revision_ids

    claimed = await JobRepository(session_factory).claim_next(
        worker_id="feedback-test-worker", lease_seconds=60
    )
    assert claimed is not None and claimed.id == job.id
    llm = DevelopmentFakeLLMGateway()
    runtime = GrowthRuntimeContext(
        session_factory=session_factory,
        llm_gateway=llm,
        research_gateway=NullResearchGateway(),
    )
    worker = Worker(
        object(),
        "feedback-test-worker",
        session_factory=session_factory,
        runtime_context=runtime,
        feedback_graph=build_feedback_graph(InMemorySaver()),
    )
    await worker.execute(claimed)

    async with session_factory() as session:
        persisted_run = await session.get(FeedbackRun, run.id)
        persisted_job = await session.get(Job, job.id)
        recommendation = await session.scalar(
            select(FeedbackRecommendation).where(
                FeedbackRecommendation.feedback_run_id == run.id
            )
        )
        assert persisted_run is not None and persisted_job is not None
        assert persisted_run.status == FeedbackRunStatus.SUCCEEDED
        assert persisted_job.status == JobStatus.SUCCEEDED
        assert recommendation is not None
        assert recommendation.attribution_scope == AttributionStrength.CORRELATIVE
        assert "不得表述为该内容导致" in "".join(
            recommendation.recommendation["limitations"]
        )
        insight = await session.get(
            RegistryRevision, recommendation.strategy_insight_revision_id
        )
        assert insight is not None
        assert insight.status == RevisionStatus.DRAFT
        item = await session.get(RegistryItem, insight.item_id)
        assert item is not None
        assert item.registry_type == RegistryType.STRATEGY_INSIGHT
        assert item.current_revision_id is None

    async with session_factory() as session:
        activated = await RegistryService(session).activate_revision(
            brand_id=brand_id,
            revision_id=insight.id,
            actor_id=actor_id,
            expected_type=RegistryType.STRATEGY_INSIGHT,
        )
        assert activated.status == RevisionStatus.ACTIVE
