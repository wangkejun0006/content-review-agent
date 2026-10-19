from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductMediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_item_id: uuid.UUID
    media_type: str
    file_name: str
    mime_type: str
    byte_size: int
    width: int
    height: int
    alt_text: str
    is_primary: bool
    url: str = ""
    created_at: datetime
