from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from smart_growth_agent.domain.enums import JobStatus, JobType


class WorkerStatusRead(BaseModel):
    online: bool
    worker_id: str | None
    hostname: str | None
    process_id: int | None
    status: str
    current_job_id: uuid.UUID | None
    started_at: datetime | None
    last_seen_at: datetime | None
    stale_after_seconds: int


class QueueStatusRead(BaseModel):
    queued: int
    running: int
    waiting_human: int
    succeeded: int
    failed: int


class OperationalJobRead(BaseModel):
    id: uuid.UUID
    job_type: JobType
    status: JobStatus
    attempts: int
    max_attempts: int
    manual_retries: int
    related_resource_id: uuid.UUID | None
    last_error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class OperationsStatusRead(BaseModel):
    checked_at: datetime
    worker: WorkerStatusRead
    queue: QueueStatusRead
    failed_jobs: list[OperationalJobRead]
