from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal
from smart_growth_agent.db.models import (
    ComplianceFinding,
    ComplianceReport,
    ContentCandidate,
    ContentVersion,
)
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.compliance import (
    ComplianceFindingRead,
    ComplianceReportRead,
)

router = APIRouter(tags=["compliance"])


@router.get(
    "/growth-runs/{run_id}/compliance-reports",
    response_model=list[ComplianceReportRead],
)
async def list_compliance_reports(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[ComplianceReportRead]:
    reports = list(
        await session.scalars(
            select(ComplianceReport)
            .join(ContentVersion, ContentVersion.id == ComplianceReport.content_version_id)
            .join(ContentCandidate, ContentCandidate.id == ContentVersion.candidate_id)
            .where(
                ComplianceReport.brand_id == principal.brand_id,
                ContentCandidate.run_id == run_id,
            )
            .order_by(ComplianceReport.created_at)
        )
    )
    result: list[ComplianceReportRead] = []
    for report in reports:
        findings = list(
            await session.scalars(
                select(ComplianceFinding)
                .where(ComplianceFinding.report_id == report.id)
                .order_by(ComplianceFinding.created_at)
            )
        )
        result.append(
            ComplianceReportRead(
                id=report.id,
                content_version_id=report.content_version_id,
                deterministic_pass=report.deterministic_pass,
                semantic_pass=report.semantic_pass,
                has_blockers=report.has_blockers,
                summary=report.summary,
                findings=[ComplianceFindingRead.model_validate(item) for item in findings],
            )
        )
    return result
