from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, TypedDict


def merge_candidate_refs(
    left: dict[str, uuid.UUID], right: dict[str, uuid.UUID]
) -> dict[str, uuid.UUID]:
    merged = dict(left)
    for route_key, candidate_id in right.items():
        existing = merged.get(route_key)
        if existing is not None and existing != candidate_id:
            raise ValueError(f"route {route_key} produced multiple candidate IDs")
        merged[route_key] = candidate_id
    return merged


def merge_uuid_maps(
    left: dict[uuid.UUID, uuid.UUID], right: dict[uuid.UUID, uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    merged = dict(left)
    for key, value in right.items():
        existing = merged.get(key)
        if existing is not None and existing != value:
            raise ValueError(f"{key} produced multiple asset IDs")
        merged[key] = value
    return merged


def update_uuid_maps(
    left: dict[uuid.UUID, Any], right: dict[uuid.UUID, Any]
) -> dict[uuid.UUID, Any]:
    return {**left, **right}


class GrowthState(TypedDict, total=False):
    run_id: uuid.UUID
    thread_id: str
    brand_id: uuid.UUID
    brief_id: uuid.UUID
    registry_revision_ids: list[uuid.UUID]
    strategy_plan_id: uuid.UUID | None
    product_context_package_id: uuid.UUID | None
    policy_context_package_id: uuid.UUID | None
    trend_context_package_id: uuid.UUID | None
    creative_route_keys: list[str]
    route_key: str
    candidate_id: uuid.UUID
    candidate_refs: Annotated[dict[str, uuid.UUID], merge_candidate_refs]
    candidate_ids: list[uuid.UUID]
    iteration_by_candidate: Annotated[dict[uuid.UUID, int], update_uuid_maps]
    compliance_report_ids: Annotated[dict[uuid.UUID, uuid.UUID], update_uuid_maps]
    reviewed_version_ids: Annotated[dict[uuid.UUID, uuid.UUID], update_uuid_maps]
    score_report_ids: Annotated[dict[uuid.UUID, uuid.UUID], update_uuid_maps]
    recommended_candidate_id: uuid.UUID | None
    ranked_candidate_ids: list[uuid.UUID]
    selected_candidate_id: uuid.UUID | None
    gate_status: str
    review_decision: dict[str, Any] | None
    errors: Annotated[list[dict[str, Any]], operator.add]
