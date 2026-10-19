from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.ingestion import IngestionRecordRead, IngestionResolve
from smart_growth_agent.services.ingestion import IngestionDedupService

router = APIRouter(tags=["ingestion"])


@router.post("/ingestions/{ingestion_id}/resolve", response_model=IngestionRecordRead)
async def resolve_ingestion(
    ingestion_id: uuid.UUID,
    data: IngestionResolve,
    principal: Principal = Depends(require_permission("registry:write")),
) -> IngestionRecordRead:
    record = await IngestionDedupService(SessionFactory).resolve(
        brand_id=principal.brand_id,
        ingestion_id=ingestion_id,
        data=data,
    )
    return IngestionRecordRead.model_validate(record)
