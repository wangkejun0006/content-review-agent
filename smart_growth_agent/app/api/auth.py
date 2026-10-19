from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.models import Brand, BrandMembership, User
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import (
    LoginContext,
    Principal,
    TokenRequest,
    TokenResponse,
    UserCreate,
    UserRead,
)
from smart_growth_agent.security import create_access_token
from smart_growth_agent.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login-context", response_model=LoginContext)
async def login_context(session: AsyncSession = Depends(get_session)) -> LoginContext:
    brands = list(
        await session.scalars(
            select(Brand).where(Brand.is_active.is_(True)).order_by(Brand.created_at).limit(2)
        )
    )
    if len(brands) != 1:
        return LoginContext(brand_id=None, brand_name=None, requires_brand_id=True)
    return LoginContext(
        brand_id=brands[0].id,
        brand_name=brands[0].name,
        requires_brand_id=False,
    )


@router.post("/token", response_model=TokenResponse)
async def create_token(
    data: TokenRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    principal = await AuthService(session).authenticate(
        email=data.email, password=data.password, brand_id=data.brand_id
    )
    token, expires_at = create_access_token(principal, settings)
    return TokenResponse(access_token=token, expires_at=expires_at)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("users:manage")),
) -> UserRead:
    user, membership = await AuthService(session).create_member(
        brand_id=principal.brand_id,
        email=data.email,
        display_name=data.display_name,
        password=data.password,
        role=data.role,
        actor_id=principal.user_id,
    )
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        brand_id=principal.brand_id,
        role=membership.role,
    )


@router.get("/users", response_model=list[UserRead])
async def list_users(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("users:manage")),
) -> list[UserRead]:
    rows = (
        await session.execute(
            select(User, BrandMembership)
            .join(BrandMembership, BrandMembership.user_id == User.id)
            .where(BrandMembership.brand_id == principal.brand_id)
            .order_by(User.email)
        )
    ).all()
    return [
        UserRead(
            id=row.User.id,
            email=row.User.email,
            display_name=row.User.display_name,
            brand_id=principal.brand_id,
            role=row.BrandMembership.role,
        )
        for row in rows
    ]
