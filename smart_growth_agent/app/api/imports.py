from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.imports import ImportBatchResult
from smart_growth_agent.services.imports import ImportService

router = APIRouter(tags=["imports"])


@router.post("/imports/xhs", response_model=ImportBatchResult)
async def import_xhs_metrics(
    content: str = Body(media_type="text/csv"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    principal: Principal = Depends(require_permission("analytics:write")),
) -> ImportBatchResult:
    return await ImportService(SessionFactory).import_xhs(
        brand_id=principal.brand_id,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
        content=content,
    )


@router.post("/imports/jd", response_model=ImportBatchResult)
async def import_jd_metrics(
    content: str = Body(media_type="text/csv"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    principal: Principal = Depends(require_permission("analytics:write")),
) -> ImportBatchResult:
    return await ImportService(SessionFactory).import_jd(
        brand_id=principal.brand_id,
        actor_id=principal.user_id,
        idempotency_key=idempotency_key,
        content=content,
    )
