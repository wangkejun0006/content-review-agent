from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class ImportRowResult(BaseModel):
    row_number: int
    status: Literal["succeeded", "failed"]
    resource_id: uuid.UUID | None = None
    error: str | None = None


class ImportBatchResult(BaseModel):
    import_type: Literal["xhs_metrics", "jd_commerce"]
    total_rows: int
    succeeded_rows: int
    failed_rows: int
    rows: list[ImportRowResult]
