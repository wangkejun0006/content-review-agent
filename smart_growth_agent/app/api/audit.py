from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.audit import AuditEventPage
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.services.audit_query import AuditQueryService

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=AuditEventPage)
async def list_audit_events(
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("audit:read")),
) -> AuditEventPage:
    return await AuditQueryService(session).list_events(
        brand_id=principal.brand_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
