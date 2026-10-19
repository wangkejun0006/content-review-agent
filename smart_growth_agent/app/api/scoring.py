from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal
from smart_growth_agent.db.models import (
    ContentCandidate,
    ContentVersion,
    ScoreDimension,
    ScoreReport,
)
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.scoring import ScoreDimensionRead, ScoreReportRead

router = APIRouter(tags=["scoring"])


@router.get(
    "/growth-runs/{run_id}/score-reports",
    response_model=list[ScoreReportRead],
)
async def list_score_reports(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[ScoreReportRead]:
    reports = list(
        await session.scalars(
            select(ScoreReport)
            .join(ContentVersion, ContentVersion.id == ScoreReport.content_version_id)
            .join(ContentCandidate, ContentCandidate.id == ContentVersion.candidate_id)
            .where(
                ScoreReport.brand_id == principal.brand_id,
                ContentCandidate.run_id == run_id,
            )
            .order_by(ScoreReport.created_at)
        )
    )
    result: list[ScoreReportRead] = []
    for report in reports:
        dimensions = list(
            await session.scalars(
                select(ScoreDimension)
                .where(ScoreDimension.report_id == report.id)
                .order_by(ScoreDimension.created_at)
            )
        )
        result.append(
            ScoreReportRead(
                id=report.id,
                content_version_id=report.content_version_id,
                rubric_revision_id=report.rubric_revision_id,
                prompt_revision_id=report.prompt_revision_id,
                total_score=report.total_score,
                pass_threshold=report.pass_threshold,
                passed=report.total_score >= report.pass_threshold,
                summary=report.summary,
                revision_suggestions=report.revision_suggestions,
                dimensions=[
                    ScoreDimensionRead(
                        name=item.dimension,
                        score=item.score,
                        rationale=item.rationale,
                    )
                    for item in dimensions
                ],
            )
        )
    return result
