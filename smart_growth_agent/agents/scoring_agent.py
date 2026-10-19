from __future__ import annotations

import uuid
from decimal import Decimal

from langgraph.runtime import Runtime
from sqlalchemy import select

from smart_growth_agent.db.models import (
    ComplianceReport,
    ContentCandidate,
    ContentVersion,
    ScoreReport,
    StrategyPlan,
)
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState
from smart_growth_agent.schemas.phase2 import StrategyOutput


async def aggregate_quality(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    candidate_ids = [uuid.UUID(str(value)) for value in state.get("candidate_ids", [])]
    compliance_ids = {
        uuid.UUID(str(key)): uuid.UUID(str(value))
        for key, value in state.get("compliance_report_ids", {}).items()
    }
    score_ids = {
        uuid.UUID(str(key)): uuid.UUID(str(value))
        for key, value in state.get("score_report_ids", {}).items()
    }
    if (
        len(candidate_ids) != 3
        or set(candidate_ids) != set(compliance_ids)
        or set(candidate_ids) != set(score_ids)
    ):
        raise RuntimeError("all three candidates must produce final compliance and score reports")

    async with runtime.context.session_factory() as session:
        candidates = list(
            await session.scalars(
                select(ContentCandidate).where(ContentCandidate.id.in_(candidate_ids))
            )
        )
        compliance_reports = {
            report.id: report
            for report in await session.scalars(
                select(ComplianceReport).where(
                    ComplianceReport.id.in_(compliance_ids.values())
                )
            )
        }
        score_reports = {
            report.id: report
            for report in await session.scalars(
                select(ScoreReport).where(ScoreReport.id.in_(score_ids.values()))
            )
        }
        plan = await session.scalar(
            select(StrategyPlan).where(StrategyPlan.run_id == state["run_id"])
        )
        current_versions = {
            version.id: version
            for version in await session.scalars(
                select(ContentVersion).where(
                    ContentVersion.candidate_id.in_(candidate_ids),
                    ContentVersion.version.in_([item.current_version for item in candidates]),
                )
            )
        }
    if len(candidates) != 3 or plan is None:
        raise RuntimeError("candidate ranking context is incomplete")
    route_order = {
        route.route_key: index
        for index, route in enumerate(
            StrategyOutput.model_validate(plan.payload).creative_routes
        )
    }
    ranking: list[tuple[ContentCandidate, bool, Decimal]] = []
    for candidate in candidates:
        version = next(
            (
                item
                for item in current_versions.values()
                if item.candidate_id == candidate.id and item.version == candidate.current_version
            ),
            None,
        )
        compliance = compliance_reports.get(compliance_ids[candidate.id])
        score = score_reports.get(score_ids[candidate.id])
        if (
            version is None
            or compliance is None
            or score is None
            or compliance.content_version_id != version.id
            or score.content_version_id != version.id
        ):
            raise RuntimeError("candidate final quality reports do not match its current version")
        eligible = not compliance.has_blockers and compliance.semantic_pass
        ranking.append((candidate, eligible, score.total_score))
    ranking.sort(
        key=lambda item: (
            not item[1],
            -item[2],
            route_order.get(item[0].route_key, 999),
        )
    )
    recommended = next((item[0].id for item in ranking if item[1]), None)
    return {
        "ranked_candidate_ids": [item[0].id for item in ranking],
        "recommended_candidate_id": recommended,
        "gate_status": "quality_review_complete",
    }
