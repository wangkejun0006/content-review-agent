from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy import select

from smart_growth_agent.db.models import ContentCandidate, ContentVersion
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState
from smart_growth_agent.services.compliance import ComplianceService
from smart_growth_agent.services.scoring import ScoringService


class CandidateReviewState(TypedDict, total=False):
    run_id: uuid.UUID
    brand_id: uuid.UUID
    candidate_id: uuid.UUID
    reviewed_version_id: uuid.UUID
    compliance_report_id: uuid.UUID
    iteration: int
    needs_revision: bool
    score_report_id: uuid.UUID
    score_passed: bool
    revision_suggestions: list[str]


async def review_candidate_version(
    state: CandidateReviewState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    context = runtime.context
    async with context.session_factory() as session:
        version = await session.scalar(
            select(ContentVersion)
            .join(ContentCandidate, ContentCandidate.id == ContentVersion.candidate_id)
            .where(
                ContentCandidate.id == state["candidate_id"],
                ContentCandidate.brand_id == state["brand_id"],
                ContentCandidate.run_id == state["run_id"],
                ContentVersion.version == ContentCandidate.current_version,
            )
        )
    if version is None:
        raise RuntimeError("candidate current content version is missing")
    service = ComplianceService(context.session_factory, context.llm_gateway)
    report_id = await service.review_content_version(
        brand_id=state["brand_id"], content_version_id=version.id
    )
    report = await service.get_report(brand_id=state["brand_id"], report_id=report_id)
    return {
        "reviewed_version_id": version.id,
        "compliance_report_id": report_id,
        "needs_revision": report.has_blockers or not report.semantic_pass,
        "iteration": version.version - 1,
    }

def route_after_compliance(state: CandidateReviewState) -> str:
    if state["needs_revision"] and state["iteration"] < 2:
        return "rewrite_candidate_version"
    return "score_candidate_version"


async def score_candidate_version(
    state: CandidateReviewState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    service = ScoringService(runtime.context.session_factory, runtime.context.llm_gateway)
    report_id = await service.score_content_version(
        brand_id=state["brand_id"],
        content_version_id=state["reviewed_version_id"],
    )
    report = await service.get_report(brand_id=state["brand_id"], report_id=report_id)
    return {
        "score_report_id": report_id,
        "score_passed": report.passed,
        "revision_suggestions": report.revision_suggestions,
    }


def route_after_scoring(state: CandidateReviewState) -> str:
    if not state["score_passed"] and state["iteration"] < 2:
        return "rewrite_candidate_version"
    return "candidate_review_complete"


async def rewrite_candidate_version(
    state: CandidateReviewState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    context = runtime.context
    await ComplianceService(
        context.session_factory, context.llm_gateway
    ).rewrite_content_version(
        brand_id=state["brand_id"],
        candidate_id=state["candidate_id"],
        source_version_id=state["reviewed_version_id"],
        revision_instructions="\n".join(state.get("revision_suggestions", [])) or None,
    )
    return {}


def build_candidate_review_graph() -> object:
    builder = StateGraph(CandidateReviewState, context_schema=GrowthRuntimeContext)
    builder.add_node("review_candidate_version", review_candidate_version)
    builder.add_node("rewrite_candidate_version", rewrite_candidate_version)
    builder.add_node("score_candidate_version", score_candidate_version)
    builder.add_node("candidate_review_complete", lambda _state: {})
    builder.add_edge(START, "review_candidate_version")
    builder.add_conditional_edges("review_candidate_version", route_after_compliance)
    builder.add_conditional_edges("score_candidate_version", route_after_scoring)
    builder.add_edge("rewrite_candidate_version", "review_candidate_version")
    builder.add_edge("candidate_review_complete", END)
    return builder.compile()


CANDIDATE_REVIEW_GRAPH = build_candidate_review_graph()


async def review_candidate_compliance(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    candidate_id = state["candidate_id"]
    result = await CANDIDATE_REVIEW_GRAPH.ainvoke(
        {
            "run_id": state["run_id"],
            "brand_id": state["brand_id"],
            "candidate_id": candidate_id,
        },
        context=runtime.context,
    )
    return {
        "compliance_report_ids": {candidate_id: result["compliance_report_id"]},
        "reviewed_version_ids": {candidate_id: result["reviewed_version_id"]},
        "iteration_by_candidate": {candidate_id: result["iteration"]},
        "score_report_ids": {candidate_id: result["score_report_id"]},
    }
