from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import AuditEvent


def record_audit(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            brand_id=brand_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
    )
