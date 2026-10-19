from __future__ import annotations

import uuid

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy import select

from smart_growth_agent.agents.compliance_agent import CANDIDATE_REVIEW_GRAPH
from smart_growth_agent.db.models import ContentCandidate, ContentVersion, HumanReview
from smart_growth_agent.domain.enums import ReviewDecision
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState
from smart_growth_agent.schemas.phase2 import WriterOutput
from smart_growth_agent.services.compliance import ComplianceService
from smart_growth_agent.services.scoring import ScoringService


async def prepare_human_review(_state: GrowthState) -> dict:
    return {"gate_status": "waiting_human_review"}


async def human_review(state: GrowthState) -> dict:
    decision = interrupt(
        {
            "run_id": str(state["run_id"]),
            "candidate_ids": [str(value) for value in state["candidate_ids"]],
            "compliance_report_ids": {
                str(key): str(value)
                for key, value in state.get("compliance_report_ids", {}).items()
            },
            "score_report_ids": {
                str(key): str(value) for key, value in state.get("score_report_ids", {}).items()
            },
            "ranked_candidate_ids": [
                str(value) for value in state.get("ranked_candidate_ids", [])
            ],
            "recommended_candidate_id": (
                str(state["recommended_candidate_id"])
                if state.get("recommended_candidate_id") is not None
                else None
            ),
        }
    )
    return {"review_decision": decision}


def route_review_decision(state: GrowthState) -> str:
    decision = ReviewDecision(state["review_decision"]["decision"])
    if decision == ReviewDecision.APPROVED:
        return "approve_content"
    if decision == ReviewDecision.REJECTED:
        return "reject_content"
    if decision == ReviewDecision.APPROVED_WITH_EDIT:
        return "apply_human_edit"
    if decision == ReviewDecision.REQUEST_CHANGES:
        return "apply_requested_changes"
    raise ValueError(f"unsupported review decision: {decision.value}")


async def approve_content(state: GrowthState) -> dict:
    raw_candidate_id = state["review_decision"].get("selected_candidate_id")
    if raw_candidate_id is None:
        raise ValueError("approved review requires selected_candidate_id")
    candidate_id = uuid.UUID(raw_candidate_id)
    if candidate_id not in state["candidate_ids"]:
        raise ValueError("selected candidate is outside this growth run")
    return {
        "selected_candidate_id": candidate_id,
        "gate_status": "ready_for_manual_publish",
    }


async def reject_content(_state: GrowthState) -> dict:
    return {"gate_status": "rejected"}


async def apply_requested_changes(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    review = await _load_review(state, runtime)
    if review.selected_candidate_id is None:
        raise ValueError("request_changes requires selected candidate")
    context = runtime.context
    async with context.session_factory() as session:
        source = await session.scalar(
            select(ContentVersion)
            .join(ContentCandidate, ContentCandidate.id == ContentVersion.candidate_id)
            .where(
                ContentCandidate.id == review.selected_candidate_id,
                ContentCandidate.brand_id == state["brand_id"],
                ContentCandidate.run_id == state["run_id"],
                ContentVersion.version == ContentCandidate.current_version,
            )
        )
    if source is None:
        raise RuntimeError("request changes source version is missing")
    service = ComplianceService(context.session_factory, context.llm_gateway)
    await service.rewrite_content_version(
        brand_id=state["brand_id"],
        candidate_id=review.selected_candidate_id,
        source_version_id=source.id,
        revision_instructions=review.payload["change_request"],
    )
    result = await CANDIDATE_REVIEW_GRAPH.ainvoke(
        {
            "run_id": state["run_id"],
            "brand_id": state["brand_id"],
            "candidate_id": review.selected_candidate_id,
        },
        context=context,
    )
    return {
        "compliance_report_ids": {
            review.selected_candidate_id: result["compliance_report_id"]
        },
        "reviewed_version_ids": {
            review.selected_candidate_id: result["reviewed_version_id"]
        },
        "iteration_by_candidate": {review.selected_candidate_id: result["iteration"]},
        "score_report_ids": {review.selected_candidate_id: result["score_report_id"]},
        "gate_status": "changes_reviewed",
    }


async def apply_human_edit(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    review = await _load_review(state, runtime)
    if review.selected_candidate_id is None:
        raise ValueError("approved_with_edit requires selected candidate")
    edited = WriterOutput.model_validate(review.payload["edited_content"])
    context = runtime.context
    service = ComplianceService(context.session_factory, context.llm_gateway)
    version_id = await service.save_human_edit(
        brand_id=state["brand_id"],
        candidate_id=review.selected_candidate_id,
        edited_content=edited,
        review_id=review.id,
    )
    report_id = await service.review_content_version(
        brand_id=state["brand_id"], content_version_id=version_id
    )
    report = await service.get_report(brand_id=state["brand_id"], report_id=report_id)
    scoring = ScoringService(context.session_factory, context.llm_gateway)
    score_report_id = await scoring.score_content_version(
        brand_id=state["brand_id"], content_version_id=version_id
    )
    return {
        "selected_candidate_id": review.selected_candidate_id,
        "compliance_report_ids": {review.selected_candidate_id: report_id},
        "reviewed_version_ids": {review.selected_candidate_id: version_id},
        "score_report_ids": {review.selected_candidate_id: score_report_id},
        "gate_status": (
            "human_edit_requires_review"
            if report.has_blockers or not report.semantic_pass
            else "ready_for_manual_publish"
        ),
    }


def route_after_human_edit(state: GrowthState) -> str:
    if state["gate_status"] == "ready_for_manual_publish":
        return "human_edit_approved"
    return "prepare_human_review"


async def human_edit_approved(_state: GrowthState) -> dict:
    return {"gate_status": "ready_for_manual_publish"}


async def _load_review(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> HumanReview:
    review_id = uuid.UUID(state["review_decision"]["review_id"])
    async with runtime.context.session_factory() as session:
        review = await session.scalar(
            select(HumanReview).where(
                HumanReview.id == review_id,
                HumanReview.brand_id == state["brand_id"],
                HumanReview.run_id == state["run_id"],
            )
        )
    if review is None:
        raise RuntimeError("submitted human review is missing")
    if review.decision != state["review_decision"]["decision"]:
        raise ValueError("resume decision does not match persisted human review")
    return review
