from __future__ import annotations

import pytest

from smart_growth_agent.domain.errors import ForbiddenError, NotFoundError
from smart_growth_agent.services.auth import AuthService


@pytest.mark.asyncio
async def test_local_admin_can_reset_password(session_factory) -> None:
    async with session_factory() as session:
        brand, user = await AuthService(session).bootstrap_admin(
            brand_name="Auth Brand",
            brand_slug="auth-brand",
            email="admin@example.com",
            display_name="Admin",
            password="original-secure-password",
        )

    async with session_factory() as session:
        await AuthService(session).reset_password(
            email="ADMIN@example.com",
            password="replacement-secure-password",
        )

    async with session_factory() as session:
        principal = await AuthService(session).authenticate(
            email=user.email,
            password="replacement-secure-password",
            brand_id=brand.id,
        )
        assert principal.user_id == user.id
        with pytest.raises(ForbiddenError):
            await AuthService(session).authenticate(
                email=user.email,
                password="original-secure-password",
                brand_id=brand.id,
            )


@pytest.mark.asyncio
async def test_local_admin_password_reset_rejects_unknown_email(session_factory) -> None:
    async with session_factory() as session:
        with pytest.raises(NotFoundError, match="user email not found"):
            await AuthService(session).reset_password(
                email="missing@example.com",
                password="replacement-secure-password",
            )
