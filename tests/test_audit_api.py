from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from smart_growth_agent.app.dependencies import get_session
from smart_growth_agent.app.main import app
from smart_growth_agent.db.models import AuditEvent, Brand, BrandMembership, User
from smart_growth_agent.domain.enums import Role
from smart_growth_agent.security import hash_password


@pytest.mark.asyncio
async def test_audit_api_is_admin_only_filtered_and_brand_isolated(session_factory) -> None:
    password = "a-secure-audit-password"
    async with session_factory() as session, session.begin():
        brand = Brand(name="Audit Brand", slug="audit-brand")
        other_brand = Brand(name="Other Brand", slug="other-audit-brand")
        admin = User(
            email="audit-admin@example.com",
            password_hash=hash_password(password),
            display_name="Audit Admin",
        )
        editor = User(
            email="audit-editor@example.com",
            password_hash=hash_password(password),
            display_name="Audit Editor",
        )
        session.add_all([brand, other_brand, admin, editor])
        await session.flush()
        session.add_all(
            [
                BrandMembership(brand_id=brand.id, user_id=admin.id, role=Role.ADMIN),
                BrandMembership(brand_id=brand.id, user_id=editor.id, role=Role.EDITOR),
                AuditEvent(
                    brand_id=brand.id,
                    actor_id=editor.id,
                    action="brief.created",
                    resource_type="campaign_brief",
                    details={"source": "test"},
                ),
                AuditEvent(
                    brand_id=brand.id,
                    actor_id=admin.id,
                    action="evidence.verified",
                    resource_type="evidence_document",
                    details={},
                ),
                AuditEvent(
                    brand_id=other_brand.id,
                    actor_id=admin.id,
                    action="brief.created",
                    resource_type="campaign_brief",
                    details={"secret": "other brand"},
                ),
            ]
        )
        brand_id = brand.id

    async def override_session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            admin_token = await client.post(
                "/v1/auth/token",
                json={
                    "email": admin.email,
                    "password": password,
                    "brand_id": str(brand_id),
                },
            )
            editor_token = await client.post(
                "/v1/auth/token",
                json={
                    "email": editor.email,
                    "password": password,
                    "brand_id": str(brand_id),
                },
            )
            admin_headers = {
                "Authorization": f"Bearer {admin_token.json()['access_token']}"
            }
            editor_headers = {
                "Authorization": f"Bearer {editor_token.json()['access_token']}"
            }
            denied = await client.get("/v1/audit-events", headers=editor_headers)
            assert denied.status_code == 403

            response = await client.get(
                "/v1/audit-events?action=brief&limit=20",
                headers=admin_headers,
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["total"] == 1
            assert len(payload["items"]) == 1
            assert payload["items"][0]["actor_email"] == editor.email
            assert payload["items"][0]["details"] == {"source": "test"}
    finally:
        app.dependency_overrides.clear()
