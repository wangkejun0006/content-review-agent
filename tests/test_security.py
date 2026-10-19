from __future__ import annotations

import uuid

from smart_growth_agent.config import Settings
from smart_growth_agent.domain.enums import Role
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.security import (
    create_access_token,
    decode_access_token,
    role_allows,
)


def test_role_matrix() -> None:
    assert role_allows(Role.ADMIN, "registry:activate")
    assert role_allows(Role.ADMIN, "assets:delete")
    assert role_allows(Role.EDITOR, "registry:write")
    assert not role_allows(Role.EDITOR, "assets:delete")
    assert not role_allows(Role.EDITOR, "registry:activate")
    assert role_allows(Role.REVIEWER, "review")
    assert not role_allows(Role.REVIEWER, "assets:delete")
    assert not role_allows(Role.REVIEWER, "brief:write")


def test_jwt_preserves_brand_scope_and_role() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="a-secure-test-secret-that-is-long-enough",
    )
    principal = Principal(
        user_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        role=Role.REVIEWER,
        email="reviewer@example.com",
    )
    token, _ = create_access_token(principal, settings)
    decoded = decode_access_token(token, settings)
    assert decoded == principal
