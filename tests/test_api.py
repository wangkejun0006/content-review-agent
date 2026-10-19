from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from smart_growth_agent.app.dependencies import get_session
from smart_growth_agent.app.main import app
from smart_growth_agent.db.models import Brand, BrandMembership, User
from smart_growth_agent.domain.enums import Role
from smart_growth_agent.security import hash_password


@pytest.mark.asyncio
async def test_registry_permissions_and_lifecycle_via_api(session_factory) -> None:
    password = "a-secure-test-password"
    async with session_factory() as session, session.begin():
        brand = Brand(name="API Brand", slug="api-brand")
        editor = User(
            email="editor@example.com",
            password_hash=hash_password(password),
            display_name="Editor",
        )
        reviewer = User(
            email="reviewer@example.com",
            password_hash=hash_password(password),
            display_name="Reviewer",
        )
        session.add_all([brand, editor, reviewer])
        await session.flush()
        session.add_all(
            [
                BrandMembership(brand_id=brand.id, user_id=editor.id, role=Role.EDITOR),
                BrandMembership(brand_id=brand.id, user_id=reviewer.id, role=Role.REVIEWER),
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
            context = await client.get("/v1/auth/login-context")
            assert context.status_code == 200
            assert context.json() == {
                "brand_id": str(brand_id),
                "brand_name": "API Brand",
                "requires_brand_id": False,
            }
            editor_login = await client.post(
                "/v1/auth/token",
                json={"email": editor.email, "password": password, "brand_id": str(brand_id)},
            )
            reviewer_login = await client.post(
                "/v1/auth/token",
                json={"email": reviewer.email, "password": password, "brand_id": str(brand_id)},
            )
            assert editor_login.status_code == reviewer_login.status_code == 200
            editor_headers = {"Authorization": f"Bearer {editor_login.json()['access_token']}"}
            reviewer_headers = {"Authorization": f"Bearer {reviewer_login.json()['access_token']}"}

            created = await client.post(
                "/v1/registry/product",
                headers=editor_headers,
                json={
                    "stable_key": "api-ring",
                    "payload": {
                        "name": "API 桌面收纳夹",
                        "product_type": "desk_accessory",
                        "description": "消费级趋势记录设备",
                        "features": ["睡眠趋势记录"],
                    },
                },
            )
            assert created.status_code == 201, created.text
            body = created.json()
            item_id = body["id"]
            revision_id = body["revisions"][0]["id"]

            denied = await client.post(
                f"/v1/registry/product/{item_id}/revisions/{revision_id}/activate",
                headers=editor_headers,
            )
            assert denied.status_code == 403

            activated = await client.post(
                f"/v1/registry/product/{item_id}/revisions/{revision_id}/activate",
                headers=reviewer_headers,
            )
            assert activated.status_code == 200, activated.text
            assert activated.json()["status"] == "active"

            fetched = await client.get(f"/v1/registry/product/{item_id}", headers=reviewer_headers)
            assert fetched.status_code == 200
            assert fetched.json()["current_revision_id"] == revision_id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_product_assets_do_not_expose_source_documents() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/product-assets/private-source.xlsx")
        assert response.status_code == 404
