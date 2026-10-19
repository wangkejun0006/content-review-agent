from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from smart_growth_agent.db.models import (
    Brand,
    ComplianceReport,
    ContentCandidate,
    ContentVersion,
    Job,
    RunContextPackage,
    ScoreReport,
    StrategyPlan,
    User,
)
from smart_growth_agent.domain.enums import (
    ContextType,
    JobStatus,
    RegistryType,
    ReviewDecision,
    RunStatus,
)
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.graph.growth_graph import build_growth_graph
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.llm.fake import DevelopmentFakeLLMGateway
from smart_growth_agent.repositories.jobs import JobRepository
from smart_growth_agent.schemas.phase2 import WriterOutput
from smart_growth_agent.schemas.registry import DEFAULT_SCORING_RUBRIC, RegistryItemCreate
from smart_growth_agent.schemas.reviews import HumanReviewCreate
from smart_growth_agent.schemas.runs import CampaignBriefCreate
from smart_growth_agent.services.compliance import ComplianceService
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.services.reviews import ReviewService
from smart_growth_agent.services.runs import RunService
from smart_growth_agent.services.scoring import ScoringService
from smart_growth_agent.worker import Worker
from tests.phase2_support import FakePhase2LLM, FakeResearchGateway


@pytest.mark.asyncio
async def test_worker_completes_phase2_with_three_idempotent_candidates(session_factory) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Worker Brand", slug="worker-brand")
        user = User(email="worker@example.com", password_hash="unused", display_name="Worker")
        session.add_all([brand, user])
        await session.flush()
        brand_id, user_id = brand.id, user.id

    async with session_factory() as session:
        registry = RegistryService(session)
        product, revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PRODUCT,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="worker-ring",
                payload={
                    "name": "Worker 戒指",
                    "product_type": "desk_accessory",
                    "description": "消费级设备",
                    "features": ["活动趋势"],
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id, revision_id=revision.id, actor_id=user_id
        )
        for stable_key, purpose, output_schema in [
            ("xhs_product_context", "xhs_product_context", "ProductContextOutput"),
            ("xhs_strategy", "xhs_strategy", "StrategyOutput"),
            ("xhs_writer", "xhs_writer", "WriterOutput"),
            (
                "xhs_compliance",
                "xhs_compliance_semantic",
                "ComplianceSemanticOutput",
            ),
            ("xhs_scoring", "xhs_scoring", "ScoringOutput"),
        ]:
            _item, prompt_revision = await registry.create_item(
                brand_id=brand_id,
                registry_type=RegistryType.PROMPT_TEMPLATE,
                actor_id=user_id,
                data=RegistryItemCreate(
                    stable_key=stable_key,
                    payload={
                        "purpose": purpose,
                        "template": f"Return strict JSON for {purpose}.",
                        "variables": [],
                        "output_schema_name": output_schema,
                    },
                ),
            )
            await registry.activate_revision(
                brand_id=brand_id, revision_id=prompt_revision.id, actor_id=user_id
            )
        _rubric_item, rubric_revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.SCORING_RUBRIC,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="xhs_content_score",
                payload=DEFAULT_SCORING_RUBRIC.model_dump(mode="json"),
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id, revision_id=rubric_revision.id, actor_id=user_id
        )
        runs = RunService(session)
        brief = await runs.create_brief(
            brand_id=brand_id,
            actor_id=user_id,
            data=CampaignBriefCreate(
                name="Worker 验证",
                objective="建立创意文具品牌认知",
                product_item_ids=[product.id],
            ),
        )
        run, queued_job, _ = await runs.create_growth_run(
            brand_id=brand_id,
            brief_id=brief.id,
            actor_id=user_id,
            idempotency_key="worker-request-key",
            max_attempts=3,
        )
        run_id, job_id = run.id, queued_job.id

    claimed = await JobRepository(session_factory).claim_next(
        worker_id="test-worker", lease_seconds=60
    )
    assert claimed is not None
    fake_llm = FakePhase2LLM(
        unsafe_draft_routes={"aesthetic-detail"},
        always_unsafe_routes={"aesthetic-question"},
        score_by_route={"daily-object": 60},
    )
    fake_research = FakeResearchGateway()
    runtime = GrowthRuntimeContext(
        session_factory=session_factory,
        llm_gateway=fake_llm,
        research_gateway=fake_research,
    )
    worker = Worker(
        build_growth_graph(InMemorySaver()),
        "test-worker",
        session_factory=session_factory,
        runtime_context=runtime,
    )
    await worker.execute(claimed)

    async with session_factory() as session:
        persisted_run = await session.get(type(run), run_id)
        persisted_job = await session.get(Job, job_id)
        assert persisted_run is not None and persisted_job is not None
        assert persisted_run.status == RunStatus.WAITING_HUMAN, persisted_job.last_error
        assert persisted_run.gate_status == "waiting_human_review"
        assert persisted_job.status == JobStatus.WAITING_HUMAN
        assert len(list(await session.scalars(select(ContentCandidate)))) == 3
        assert len(list(await session.scalars(select(StrategyPlan)))) == 1
        product_context = await session.scalar(
            select(RunContextPackage).where(
                RunContextPackage.run_id == run_id,
                RunContextPackage.context_type == ContextType.PRODUCT,
            )
        )
        assert product_context is not None
        assert any(
            "没有已激活的 Product Claim 或可验证证据" in warning
            for warning in product_context.payload["missing_information"]
        )
        candidates = list(await session.scalars(select(ContentCandidate)))
        assert {candidate.route_key: candidate.current_version for candidate in candidates} == {
            "aesthetic-detail": 2,
            "aesthetic-question": 3,
            "daily-object": 3,
        }
        assert len(list(await session.scalars(select(ContentVersion)))) == 8
        assert len(list(await session.scalars(select(ComplianceReport)))) == 8
        assert len(list(await session.scalars(select(ScoreReport)))) == 5
        final_reports = list(
            (
                await session.execute(
                    select(ContentCandidate.route_key, ComplianceReport.has_blockers)
                    .join(ContentVersion, ContentVersion.candidate_id == ContentCandidate.id)
                    .join(
                        ComplianceReport,
                        ComplianceReport.content_version_id == ContentVersion.id,
                    )
                    .where(ContentVersion.version == ContentCandidate.current_version)
                )
            ).all()
        )
        assert dict(final_reports) == {
            "aesthetic-detail": False,
            "aesthetic-question": True,
            "daily-object": False,
        }
        change_candidate_id = next(
            candidate.id for candidate in candidates if candidate.route_key == "aesthetic-detail"
        )
        alternative_candidate_id = next(
            candidate.id for candidate in candidates if candidate.route_key == "daily-object"
        )
        assert persisted_run.recommended_candidate_id == change_candidate_id
        blocked_candidate_id = next(
            candidate.id
            for candidate in candidates
            if candidate.route_key == "aesthetic-question"
        )
    assert fake_llm.calls.count("xhs_product_context") == 1
    assert fake_llm.calls.count("xhs_strategy") == 1
    assert fake_llm.calls.count("xhs_writer") == 8
    assert fake_llm.calls.count("xhs_compliance_semantic") == 8
    assert fake_llm.calls.count("xhs_scoring") == 5
    assert fake_research.calls == 1

    with pytest.raises(ValidationError, match="blocked candidate"):
        async with session_factory() as session:
            await ReviewService(session).submit(
                brand_id=brand_id,
                run_id=run_id,
                data=HumanReviewCreate(
                    decision=ReviewDecision.APPROVED,
                    selected_candidate_id=blocked_candidate_id,
                ),
                reviewer_id=user_id,
                idempotency_key="reject-blocked-approval",
            )

    # Reaching the interrupt on the final allowed attempt must not make a valid human
    # resume unclaimable. Review submission starts a fresh execution segment.
    async with session_factory() as session, session.begin():
        exhausted_job = await session.get(Job, job_id)
        assert exhausted_job is not None
        exhausted_job.attempts = exhausted_job.max_attempts
        exhausted_job.last_error = {"message": "stale generation error"}

    async with session_factory() as session:
        await ReviewService(session).submit(
            brand_id=brand_id,
            run_id=run_id,
            data=HumanReviewCreate(
                decision=ReviewDecision.REQUEST_CHANGES,
                selected_candidate_id=change_candidate_id,
                change_request="保留科技美学角度，但让开头更直接。",
            ),
            reviewer_id=user_id,
            idempotency_key="request-detail-change",
        )
    async with session_factory() as session:
        reset_job = await session.get(Job, job_id)
        assert reset_job is not None
        assert reset_job.attempts == 0
        assert reset_job.last_error is None
    resumed = await JobRepository(session_factory).claim_next(
        worker_id="test-worker-resume", lease_seconds=60
    )
    assert resumed is not None
    await worker.execute(resumed)
    async with session_factory() as session:
        persisted_run = await session.get(type(run), run_id)
        persisted_job = await session.get(Job, job_id)
        assert persisted_run is not None and persisted_job is not None
        assert persisted_run.status == RunStatus.WAITING_HUMAN, persisted_job.last_error
        assert persisted_run.gate_status == "waiting_human_review"
        assert persisted_job.status == JobStatus.WAITING_HUMAN
        assert len(list(await session.scalars(select(ContentCandidate)))) == 3
        assert len(list(await session.scalars(select(StrategyPlan)))) == 1
        assert len(list(await session.scalars(select(ContentVersion)))) == 9
        assert len(list(await session.scalars(select(ComplianceReport)))) == 9
        assert len(list(await session.scalars(select(ScoreReport)))) == 6
        changed = await session.get(ContentCandidate, change_candidate_id)
        alternative = await session.get(ContentCandidate, alternative_candidate_id)
        assert changed is not None and changed.current_version == 3
        assert alternative is not None and alternative.current_version == 3
        selected_version = await session.scalar(
            select(ContentVersion).where(
                ContentVersion.candidate_id == alternative.id,
                ContentVersion.version == alternative.current_version,
            )
        )
        assert selected_version is not None
        edited_payload = dict(selected_version.payload)
    assert len(fake_llm.calls) == 26

    edited_payload["title_options"] = ["人工标题一", "人工标题二", "人工标题三"]
    edited_payload["recommended_title"] = "人工标题一"
    edited_content = WriterOutput.model_validate(edited_payload)
    async with session_factory() as session:
        edit_review = await ReviewService(session).submit(
            brand_id=brand_id,
            run_id=run_id,
            data=HumanReviewCreate(
                decision=ReviewDecision.APPROVED_WITH_EDIT,
                selected_candidate_id=alternative_candidate_id,
                edited_content=edited_content,
            ),
            reviewer_id=user_id,
            idempotency_key="approve-human-edit",
        )
    edit_resume = await JobRepository(session_factory).claim_next(
        worker_id="test-worker-edit-resume", lease_seconds=60
    )
    assert edit_resume is not None
    await worker.execute(edit_resume)
    async with session_factory() as session:
        persisted_run = await session.get(type(run), run_id)
        persisted_job = await session.get(Job, job_id)
        selected = await session.get(ContentCandidate, alternative_candidate_id)
        assert persisted_run is not None and persisted_job is not None and selected is not None
        assert persisted_run.status == RunStatus.READY_FOR_MANUAL_PUBLISH
        assert persisted_run.gate_status == "ready_for_manual_publish"
        assert persisted_job.status == JobStatus.SUCCEEDED
        assert selected.current_version == 4
        assert persisted_run.recommended_candidate_id == change_candidate_id
        assert persisted_run.selected_candidate_id == alternative_candidate_id
        assert len(list(await session.scalars(select(ContentVersion)))) == 10
        assert len(list(await session.scalars(select(ComplianceReport)))) == 10
        assert len(list(await session.scalars(select(ScoreReport)))) == 7
    assert len(fake_llm.calls) == 28

    async with session_factory() as session:
        repeated = await ReviewService(session).submit(
            brand_id=brand_id,
            run_id=run_id,
            data=HumanReviewCreate(
                decision=ReviewDecision.APPROVED_WITH_EDIT,
                selected_candidate_id=alternative_candidate_id,
                edited_content=edited_content,
            ),
            reviewer_id=user_id,
            idempotency_key="approve-human-edit",
        )
    assert repeated.id == edit_review.id

    async with session_factory() as session:
        first_version_id = await session.scalar(
            select(ContentVersion.id)
            .join(ContentCandidate)
            .where(
                ContentCandidate.route_key == "daily-object",
                ContentVersion.version == ContentCandidate.current_version,
            )
        )
        assert first_version_id is not None
    compliance = ComplianceService(session_factory, DevelopmentFakeLLMGateway())
    report_id = await compliance.review_content_version(
        brand_id=brand_id, content_version_id=first_version_id
    )
    repeated_report_id = await compliance.review_content_version(
        brand_id=brand_id, content_version_id=first_version_id
    )
    assert repeated_report_id == report_id
    async with session_factory() as session:
        report = await session.get(ComplianceReport, report_id)
        assert report is not None
        assert report.deterministic_pass is True
        assert report.semantic_pass is True
        assert report.has_blockers is False

    scoring = ScoringService(session_factory, DevelopmentFakeLLMGateway())
    score_report_id = await scoring.score_content_version(
        brand_id=brand_id, content_version_id=first_version_id
    )
    repeated_score_id = await scoring.score_content_version(
        brand_id=brand_id, content_version_id=first_version_id
    )
    assert repeated_score_id == score_report_id
    score = await scoring.get_report(brand_id=brand_id, report_id=score_report_id)
    assert score.total_score == 60
    assert score.passed is False
    assert len(score.dimensions) == 6
