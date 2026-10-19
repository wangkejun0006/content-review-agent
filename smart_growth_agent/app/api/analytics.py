from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.db.models import (
    AttributionEvidence,
    CommerceSnapshot,
    MetricSnapshot,
    Publication,
)
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.analytics import (
    AttributionEvidenceCreate,
    AttributionEvidenceRead,
    CommerceSnapshotCreate,
    CommerceSnapshotRead,
    MetricSnapshotCreate,
    MetricSnapshotRead,
    PublicationCreate,
    PublicationRead,
)
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.services.analytics import AnalyticsService

router = APIRouter(tags=["analytics"])


@router.post("/publications", response_model=PublicationRead, status_code=status.HTTP_201_CREATED)
async def create_publication(
    data: PublicationCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("analytics:write")),
) -> PublicationRead:
    publication = await AnalyticsService(session).create_publication(
        brand_id=principal.brand_id,
        data=data,
        actor_id=principal.user_id,
    )
    return PublicationRead.model_validate(publication)


@router.get("/publications", response_model=list[PublicationRead])
async def list_publications(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[PublicationRead]:
    rows = list(
        await session.scalars(
            select(Publication)
            .where(Publication.brand_id == principal.brand_id)
            .order_by(Publication.published_at.desc())
        )
    )
    return [PublicationRead.model_validate(row) for row in rows]


@router.post(
    "/publications/{publication_id}/metric-snapshots",
    response_model=MetricSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_metric_snapshot(
    publication_id: uuid.UUID,
    data: MetricSnapshotCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("analytics:write")),
) -> MetricSnapshotRead:
    snapshot = await AnalyticsService(session).create_metric_snapshot(
        brand_id=principal.brand_id,
        publication_id=publication_id,
        data=data,
        actor_id=principal.user_id,
    )
    return MetricSnapshotRead.model_validate(snapshot)


@router.get(
    "/publications/{publication_id}/metric-snapshots",
    response_model=list[MetricSnapshotRead],
)
async def list_metric_snapshots(
    publication_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[MetricSnapshotRead]:
    rows = list(
        await session.scalars(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.brand_id == principal.brand_id,
                MetricSnapshot.publication_id == publication_id,
            )
            .order_by(MetricSnapshot.captured_at)
        )
    )
    return [MetricSnapshotRead.model_validate(row) for row in rows]


@router.post(
    "/commerce-snapshots",
    response_model=CommerceSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_commerce_snapshot(
    data: CommerceSnapshotCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("analytics:write")),
) -> CommerceSnapshotRead:
    snapshot = await AnalyticsService(session).create_commerce_snapshot(
        brand_id=principal.brand_id,
        data=data,
        actor_id=principal.user_id,
    )
    return CommerceSnapshotRead.model_validate(snapshot)


@router.get("/commerce-snapshots", response_model=list[CommerceSnapshotRead])
async def list_commerce_snapshots(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[CommerceSnapshotRead]:
    rows = list(
        await session.scalars(
            select(CommerceSnapshot)
            .where(CommerceSnapshot.brand_id == principal.brand_id)
            .order_by(CommerceSnapshot.captured_at.desc())
        )
    )
    return [CommerceSnapshotRead.model_validate(row) for row in rows]


@router.post(
    "/attribution-evidence",
    response_model=AttributionEvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_attribution_evidence(
    data: AttributionEvidenceCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("analytics:write")),
) -> AttributionEvidenceRead:
    evidence = await AnalyticsService(session).create_attribution_evidence(
        brand_id=principal.brand_id,
        data=data,
        actor_id=principal.user_id,
    )
    return AttributionEvidenceRead.model_validate(evidence)


@router.get("/attribution-evidence", response_model=list[AttributionEvidenceRead])
async def list_attribution_evidence(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[AttributionEvidenceRead]:
    rows = list(
        await session.scalars(
            select(AttributionEvidence)
            .where(AttributionEvidence.brand_id == principal.brand_id)
            .order_by(AttributionEvidence.created_at.desc())
        )
    )
    return [AttributionEvidenceRead.model_validate(row) for row in rows]
