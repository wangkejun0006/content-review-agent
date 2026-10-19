from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.operations import OperationalJobRead, OperationsStatusRead
from smart_growth_agent.services.operations import OperationsService

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/status", response_model=OperationsStatusRead)
async def operations_status(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(get_principal),
) -> OperationsStatusRead:
    return await OperationsService(session, settings).get_status(brand_id=principal.brand_id)


@router.post("/jobs/{job_id}/retry", response_model=OperationalJobRead)
async def retry_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("run:write")),
) -> OperationalJobRead:
    return await OperationsService(session, settings).retry_failed_job(
        brand_id=principal.brand_id,
        job_id=job_id,
        actor_id=principal.user_id,
    )
