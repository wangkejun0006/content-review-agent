from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.models import (
    CampaignBrief,
    ContentCandidate,
    ContentVersion,
    GrowthRun,
    RunContextPackage,
    StrategyPlan,
)
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.phase2 import (
    ContentCandidateRead,
    ContextPackageRead,
    StrategyOutput,
    StrategyPlanRead,
    WriterOutput,
)
from smart_growth_agent.schemas.runs import (
    CampaignBriefCreate,
    CampaignBriefRead,
    GrowthRunCreate,
    GrowthRunRead,
)
from smart_growth_agent.services.runs import RunService

router = APIRouter(tags=["growth"])


@router.post("/briefs", response_model=CampaignBriefRead, status_code=status.HTTP_201_CREATED)
async def create_brief(
    data: CampaignBriefCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("brief:write")),
) -> CampaignBriefRead:
    brief = await RunService(session).create_brief(
        brand_id=principal.brand_id, data=data, actor_id=principal.user_id
    )
    return CampaignBriefRead.model_validate(brief)

@router.get("/briefs", response_model=list[CampaignBriefRead])
async def list_briefs(
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[CampaignBriefRead]:
    statement = select(CampaignBrief).where(CampaignBrief.brand_id == principal.brand_id)
    if not include_archived:
        statement = statement.where(CampaignBrief.archived_at.is_(None))
    briefs = list(
        await session.scalars(statement.order_by(CampaignBrief.created_at.desc()))
    )
    return [CampaignBriefRead.model_validate(brief) for brief in briefs]


@router.put("/briefs/{brief_id}", response_model=CampaignBriefRead)
async def update_brief(
    brief_id: uuid.UUID,
    data: CampaignBriefCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("brief:write")),
) -> CampaignBriefRead:
    brief = await RunService(session).update_brief(
        brand_id=principal.brand_id,
        brief_id=brief_id,
        data=data,
        actor_id=principal.user_id,
    )
    return CampaignBriefRead.model_validate(brief)


@router.post("/briefs/{brief_id}/archive", response_model=CampaignBriefRead)
async def archive_brief(
    brief_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("brief:write")),
) -> CampaignBriefRead:
    brief = await RunService(session).set_brief_archived(
        brand_id=principal.brand_id,
        brief_id=brief_id,
        archived=True,
        actor_id=principal.user_id,
    )
    return CampaignBriefRead.model_validate(brief)


@router.post("/briefs/{brief_id}/restore", response_model=CampaignBriefRead)
async def restore_brief(
    brief_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("brief:write")),
) -> CampaignBriefRead:
    brief = await RunService(session).set_brief_archived(
        brand_id=principal.brand_id,
        brief_id=brief_id,
        archived=False,
        actor_id=principal.user_id,
    )
    return CampaignBriefRead.model_validate(brief)


@router.delete("/briefs/{brief_id}", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_brief(
    brief_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("assets:delete")),
) -> None:
    await RunService(session).permanently_delete_brief(
        brand_id=principal.brand_id,
        brief_id=brief_id,
        actor_id=principal.user_id,
    )


@router.post("/growth-runs", response_model=GrowthRunRead, status_code=status.HTTP_202_ACCEPTED)
async def create_growth_run(
    data: GrowthRunCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("run:write")),
) -> GrowthRunRead:
    run, job, revision_ids = await RunService(session).create_growth_run(
        brand_id=principal.brand_id,
        brief_id=data.brief_id,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
        max_attempts=settings.job_max_attempts,
    )
    return GrowthRunRead(
        **GrowthRunRead.model_validate(run).model_dump(exclude={"registry_revision_ids", "job_id"}),
        registry_revision_ids=revision_ids,
        job_id=job.id,
    )


@router.get("/growth-runs", response_model=list[GrowthRunRead])
async def list_growth_runs(
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[GrowthRunRead]:
    statement = select(GrowthRun).where(GrowthRun.brand_id == principal.brand_id)
    if not include_archived:
        statement = statement.where(GrowthRun.archived_at.is_(None))
    runs = list(
        await session.scalars(statement.order_by(GrowthRun.created_at.desc()).limit(100))
    )
    result: list[GrowthRunRead] = []
    service = RunService(session)
    for run in runs:
        _persisted, job, revision_ids = await service.get_growth_run(
            brand_id=principal.brand_id,
            run_id=run.id,
        )
        result.append(
            GrowthRunRead(
                **GrowthRunRead.model_validate(run).model_dump(
                    exclude={"registry_revision_ids", "job_id"}
                ),
                registry_revision_ids=revision_ids,
                job_id=job.id if job else None,
            )
        )
    return result


@router.post("/growth-runs/{run_id}/archive", response_model=GrowthRunRead)
async def archive_growth_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("run:write")),
) -> GrowthRunRead:
    run = await RunService(session).set_run_archived(
        brand_id=principal.brand_id,
        run_id=run_id,
        archived=True,
        actor_id=principal.user_id,
    )
    _run, job, revision_ids = await RunService(session).get_growth_run(
        brand_id=principal.brand_id,
        run_id=run.id,
    )
    return GrowthRunRead(
        **GrowthRunRead.model_validate(run).model_dump(
            exclude={"registry_revision_ids", "job_id"}
        ),
        registry_revision_ids=revision_ids,
        job_id=job.id if job else None,
    )


@router.post("/growth-runs/{run_id}/restore", response_model=GrowthRunRead)
async def restore_growth_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("run:write")),
) -> GrowthRunRead:
    run = await RunService(session).set_run_archived(
        brand_id=principal.brand_id,
        run_id=run_id,
        archived=False,
        actor_id=principal.user_id,
    )
    _run, job, revision_ids = await RunService(session).get_growth_run(
        brand_id=principal.brand_id,
        run_id=run.id,
    )
    return GrowthRunRead(
        **GrowthRunRead.model_validate(run).model_dump(
            exclude={"registry_revision_ids", "job_id"}
        ),
        registry_revision_ids=revision_ids,
        job_id=job.id if job else None,
    )


@router.delete("/growth-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_growth_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("assets:delete")),
) -> None:
    await RunService(session).permanently_delete_run(
        brand_id=principal.brand_id,
        run_id=run_id,
        actor_id=principal.user_id,
    )


@router.get("/growth-runs/{run_id}", response_model=GrowthRunRead)
async def get_growth_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> GrowthRunRead:
    run, job, revision_ids = await RunService(session).get_growth_run(
        brand_id=principal.brand_id, run_id=run_id
    )
    return GrowthRunRead(
        **GrowthRunRead.model_validate(run).model_dump(exclude={"registry_revision_ids", "job_id"}),
        registry_revision_ids=revision_ids,
        job_id=job.id if job else None,
    )


@router.get("/growth-runs/{run_id}/contexts", response_model=list[ContextPackageRead])
async def list_run_contexts(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[ContextPackageRead]:
    run = await session.scalar(
        select(GrowthRun.id).where(
            GrowthRun.id == run_id,
            GrowthRun.brand_id == principal.brand_id,
        )
    )
    if run is None:
        from smart_growth_agent.domain.errors import NotFoundError

        raise NotFoundError("growth run not found")
    packages = list(
        await session.scalars(
            select(RunContextPackage)
            .where(RunContextPackage.run_id == run_id)
            .order_by(RunContextPackage.created_at)
        )
    )
    return [
        ContextPackageRead(
            id=package.id,
            context_type=package.context_type.value,
            payload=package.payload,
        )
        for package in packages
    ]


@router.get("/growth-runs/{run_id}/strategy", response_model=StrategyPlanRead)
async def get_run_strategy(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> StrategyPlanRead:
    plan = await session.scalar(
        select(StrategyPlan).where(
            StrategyPlan.run_id == run_id,
            StrategyPlan.brand_id == principal.brand_id,
        )
    )
    if plan is None:
        from smart_growth_agent.domain.errors import NotFoundError

        raise NotFoundError("strategy plan not found")
    return StrategyPlanRead(id=plan.id, payload=StrategyOutput.model_validate(plan.payload))


@router.get("/growth-runs/{run_id}/candidates", response_model=list[ContentCandidateRead])
async def list_run_candidates(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[ContentCandidateRead]:
    rows = list(
        (
            await session.execute(
                select(ContentCandidate, ContentVersion)
                .join(
                    ContentVersion,
                    (ContentVersion.candidate_id == ContentCandidate.id)
                    & (ContentVersion.version == ContentCandidate.current_version),
                )
                .where(
                    ContentCandidate.run_id == run_id,
                    ContentCandidate.brand_id == principal.brand_id,
                )
            )
        ).all()
    )
    plan = await session.scalar(
        select(StrategyPlan).where(
            StrategyPlan.run_id == run_id,
            StrategyPlan.brand_id == principal.brand_id,
        )
    )
    route_order = (
        {
            route.route_key: index
            for index, route in enumerate(
                StrategyOutput.model_validate(plan.payload).creative_routes
            )
        }
        if plan is not None
        else {}
    )
    rows.sort(key=lambda row: route_order.get(row[0].route_key, 999))
    return [
        ContentCandidateRead(
            id=candidate.id,
            route_key=candidate.route_key,
            angle_key=candidate.angle_key,
            current_version=candidate.current_version,
            content_version_id=version.id,
            payload=WriterOutput.model_validate(version.payload),
        )
        for candidate, version in rows
    ]
