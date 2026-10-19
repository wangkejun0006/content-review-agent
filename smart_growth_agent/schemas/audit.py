from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEventRead(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_display_name: str | None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    details: dict[str, Any]
    created_at: datetime


class AuditEventPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditEventRead]
