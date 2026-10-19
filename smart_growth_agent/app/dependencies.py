from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.models import BrandMembership, User
from smart_growth_agent.db.session import get_session
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.security import decode_access_token, role_allows

bearer = HTTPBearer(auto_error=False)


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        principal = decode_access_token(credentials.credentials, settings)
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        ) from exc
    membership = await session.scalar(
        select(BrandMembership)
        .join(User, User.id == BrandMembership.user_id)
        .where(
            BrandMembership.brand_id == principal.brand_id,
            BrandMembership.user_id == principal.user_id,
            User.is_active.is_(True),
        )
    )
    membership_role = membership.role if membership is not None else None
    if membership_role != principal.role:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="membership changed")
    # Authentication is read-only. End SQLAlchemy's implicit transaction so
    # application services can own a clear, atomic transaction boundary.
    await session.rollback()
    return principal


def require_permission(permission: str) -> Callable:
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not role_allows(principal.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        return principal

    return dependency
