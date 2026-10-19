from __future__ import annotations

import operator
import uuid
from typing import Annotated, TypedDict


class FeedbackState(TypedDict, total=False):
    feedback_run_id: uuid.UUID
    thread_id: str
    brand_id: uuid.UUID
    publication_ids: list[uuid.UUID]
    metric_snapshot_ids: list[uuid.UUID]
    commerce_snapshot_ids: list[uuid.UUID]
    attribution_evidence_ids: list[uuid.UUID]
    registry_revision_ids: list[uuid.UUID]
    recommendation_id: uuid.UUID
    strategy_insight_revision_id: uuid.UUID
    gate_status: str
    errors: Annotated[list[dict], operator.add]
