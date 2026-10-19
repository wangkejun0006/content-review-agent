from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.db.models import KnowledgeSource
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.knowledge import (
    ClaimCoverageRead,
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
    RegistryVerificationCreate,
    RegistryVerificationRead,
    SourceCaptureCreate,
    SourceCaptureRead,
)
from smart_growth_agent.services.claim_coverage import ClaimCoverageService
from smart_growth_agent.services.knowledge import KnowledgeService

router = APIRouter(tags=["knowledge"])


@router.get("/claim-coverage", response_model=ClaimCoverageRead)
async def claim_coverage(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> ClaimCoverageRead:
    return await ClaimCoverageService(session).current(brand_id=principal.brand_id)


@router.get(
    "/growth-runs/{run_id}/claim-coverage",
    response_model=ClaimCoverageRead,
)
async def run_claim_coverage(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> ClaimCoverageRead:
    return await ClaimCoverageService(session).for_run(
        brand_id=principal.brand_id,
        run_id=run_id,
    )


@router.post(
    "/knowledge-sources",
    response_model=KnowledgeSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_source(
    data: KnowledgeSourceCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> KnowledgeSourceRead:
    source = await KnowledgeService(session).create_source(
        brand_id=principal.brand_id, data=data, actor_id=principal.user_id
    )
    return KnowledgeSourceRead.model_validate(source)


@router.get("/knowledge-sources", response_model=list[KnowledgeSourceRead])
async def list_knowledge_sources(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[KnowledgeSourceRead]:
    sources = list(
        await session.scalars(
            select(KnowledgeSource)
            .where(KnowledgeSource.brand_id == principal.brand_id)
            .order_by(KnowledgeSource.created_at.desc())
        )
    )
    return [KnowledgeSourceRead.model_validate(source) for source in sources]


@router.post(
    "/knowledge-sources/{source_id}/captures",
    response_model=SourceCaptureRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_capture(
    source_id: uuid.UUID,
    data: SourceCaptureCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> SourceCaptureRead:
    capture = await KnowledgeService(session).create_capture(
        brand_id=principal.brand_id,
        source_id=source_id,
        data=data,
        actor_id=principal.user_id,
    )
    return SourceCaptureRead.model_validate(capture)


@router.post(
    "/registry-revisions/{revision_id}/verifications",
    response_model=RegistryVerificationRead,
    status_code=status.HTTP_201_CREATED,
)
async def verify_registry_revision(
    revision_id: uuid.UUID,
    data: RegistryVerificationCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:activate")),
) -> RegistryVerificationRead:
    verification = await KnowledgeService(session).verify_revision(
        brand_id=principal.brand_id,
        revision_id=revision_id,
        data=data,
        actor_id=principal.user_id,
    )
    return RegistryVerificationRead.model_validate(verification)
