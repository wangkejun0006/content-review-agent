from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import AuditEvent, User
from smart_growth_agent.schemas.audit import AuditEventPage, AuditEventRead


class AuditQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_events(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditEventPage:
        filters = [AuditEvent.brand_id == brand_id]
        if actor_id is not None:
            filters.append(AuditEvent.actor_id == actor_id)
        if action:
            filters.append(AuditEvent.action.ilike(f"%{action.strip()}%"))
        if resource_type:
            filters.append(AuditEvent.resource_type == resource_type)
        if created_from is not None:
            filters.append(AuditEvent.created_at >= created_from)
        if created_to is not None:
            filters.append(AuditEvent.created_at <= created_to)
        total = int(
            await self.session.scalar(
                select(func.count(AuditEvent.id)).where(*filters)
            )
            or 0
        )
        rows = list(
            (
                await self.session.execute(
                    select(AuditEvent, User)
                    .outerjoin(User, User.id == AuditEvent.actor_id)
                    .where(*filters)
                    .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        return AuditEventPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[
                AuditEventRead(
                    id=event.id,
                    actor_id=event.actor_id,
                    actor_email=user.email if user else None,
                    actor_display_name=user.display_name if user else None,
                    action=event.action,
                    resource_type=event.resource_type,
                    resource_id=event.resource_id,
                    details=event.details,
                    created_at=event.created_at,
                )
                for event, user in rows
            ],
        )
