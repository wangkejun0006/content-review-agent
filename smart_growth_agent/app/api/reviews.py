from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.reviews import HumanReviewCreate, HumanReviewRead
from smart_growth_agent.services.reviews import ReviewService

router = APIRouter(tags=["human-review"])


@router.post(
    "/growth-runs/{run_id}/reviews",
    response_model=HumanReviewRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_human_review(
    run_id: uuid.UUID,
    data: HumanReviewCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("review")),
) -> HumanReviewRead:
    review = await ReviewService(session).submit(
        brand_id=principal.brand_id,
        run_id=run_id,
        data=data,
        reviewer_id=principal.user_id,
        idempotency_key=idempotency_key,
    )
    return HumanReviewRead.model_validate(review)
