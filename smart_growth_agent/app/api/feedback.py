from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.models import FeedbackRecommendation, FeedbackRun, Job
from smart_growth_agent.db.session import SessionFactory, get_session
from smart_growth_agent.domain.enums import JobType, RegistryType
from smart_growth_agent.domain.errors import NotFoundError
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.feedback import (
    FeedbackRecommendationRead,
    FeedbackRunCreate,
    FeedbackRunRead,
)
from smart_growth_agent.schemas.registry import RegistryRevisionRead
from smart_growth_agent.services.feedback import FeedbackService
from smart_growth_agent.services.registry import RegistryService

router = APIRouter(tags=["feedback"])


def _run_read(
    run: FeedbackRun,
    *,
    job: Job | None,
    recommendation: FeedbackRecommendation | None,
) -> FeedbackRunRead:
    return FeedbackRunRead(
        **FeedbackRunRead.model_validate(run).model_dump(
            exclude={"job_id", "recommendation_id", "strategy_insight_revision_id"}
        ),
        job_id=job.id if job is not None else None,
        recommendation_id=recommendation.id if recommendation is not None else None,
        strategy_insight_revision_id=(
            recommendation.strategy_insight_revision_id
            if recommendation is not None
            else None
        ),
    )


@router.post(
    "/feedback-runs",
    response_model=FeedbackRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_feedback_run(
    data: FeedbackRunCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("analytics:write")),
) -> FeedbackRunRead:
    run, job, _revision_ids = await FeedbackService(SessionFactory).create_run(
        brand_id=principal.brand_id,
        data=data,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
        max_attempts=settings.job_max_attempts,
    )
    return _run_read(run, job=job, recommendation=None)


@router.get("/feedback-runs", response_model=list[FeedbackRunRead])
async def list_feedback_runs(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[FeedbackRunRead]:
    runs = list(
        await session.scalars(
            select(FeedbackRun)
            .where(FeedbackRun.brand_id == principal.brand_id)
            .order_by(FeedbackRun.created_at.desc())
            .limit(100)
        )
    )
    if not runs:
        return []

    run_ids = {run.id for run in runs}
    recommendations = list(
        await session.scalars(
            select(FeedbackRecommendation).where(
                FeedbackRecommendation.brand_id == principal.brand_id,
                FeedbackRecommendation.feedback_run_id.in_(run_ids),
            )
        )
    )
    recommendation_by_run = {
        recommendation.feedback_run_id: recommendation
        for recommendation in recommendations
    }
    jobs = list(
        await session.scalars(
            select(Job).where(
                Job.brand_id == principal.brand_id,
                Job.job_type == JobType.FEEDBACK_RUN,
            )
        )
    )
    job_by_run: dict[uuid.UUID, Job] = {}
    for job in jobs:
        raw_run_id = job.payload.get("feedback_run_id")
        if raw_run_id is None:
            continue
        try:
            run_id = uuid.UUID(str(raw_run_id))
        except ValueError:
            continue
        if run_id in run_ids:
            job_by_run[run_id] = job

    return [
        _run_read(
            run,
            job=job_by_run.get(run.id),
            recommendation=recommendation_by_run.get(run.id),
        )
        for run in runs
    ]


@router.get("/feedback-runs/{feedback_run_id}", response_model=FeedbackRunRead)
async def get_feedback_run(
    feedback_run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> FeedbackRunRead:
    run = await session.scalar(
        select(FeedbackRun).where(
            FeedbackRun.id == feedback_run_id,
            FeedbackRun.brand_id == principal.brand_id,
        )
    )
    if run is None:
        raise NotFoundError("feedback run not found")
    job = await session.scalar(
        select(Job).where(
            Job.brand_id == principal.brand_id,
            Job.job_type == JobType.FEEDBACK_RUN,
            Job.payload["feedback_run_id"].as_string() == str(feedback_run_id),
        )
    )
    recommendation = await session.scalar(
        select(FeedbackRecommendation).where(
            FeedbackRecommendation.feedback_run_id == feedback_run_id
        )
    )
    return _run_read(run, job=job, recommendation=recommendation)


@router.get(
    "/feedback-runs/{feedback_run_id}/recommendation",
    response_model=FeedbackRecommendationRead,
)
async def get_feedback_recommendation(
    feedback_run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> FeedbackRecommendationRead:
    recommendation = await session.scalar(
        select(FeedbackRecommendation).where(
            FeedbackRecommendation.feedback_run_id == feedback_run_id,
            FeedbackRecommendation.brand_id == principal.brand_id,
        )
    )
    if recommendation is None:
        raise NotFoundError("feedback recommendation not found")
    return FeedbackRecommendationRead.model_validate(recommendation)


@router.post(
    "/strategy-insights/{revision_id}/activate",
    response_model=RegistryRevisionRead,
)
async def activate_strategy_insight(
    revision_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:activate")),
) -> RegistryRevisionRead:
    revision = await RegistryService(session).activate_revision(
        brand_id=principal.brand_id,
        revision_id=revision_id,
        actor_id=principal.user_id,
        expected_type=RegistryType.STRATEGY_INSIGHT,
    )
    return RegistryRevisionRead.model_validate(revision)
