"""Local-only demo login, disabled outside the dedicated launcher."""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from smart_growth_agent.config import get_settings
from smart_growth_agent.db.models import BrandMembership, User
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.security import create_access_token

router = APIRouter(prefix="/auth", tags=["local-demo"])
DEMO_STATE = Path(
    os.environ.get(
        "SMART_GROWTH_DEMO_STATE_PATH",
        Path(__file__).resolve().parents[3] / ".runtime/demo-state.json",
    )
)


class DemoSessionRequest(BaseModel):
    role: Literal["admin", "editor", "reviewer"] = "admin"


def boundary(request):
    if not get_settings().local_demo:
        raise HTTPException(404)
    from urllib.parse import urlsplit

    origin = get_settings().frontend_origin
    port = urlsplit(origin).port
    allowed_origins = {f"http://localhost:{port}", f"http://127.0.0.1:{port}"}
    if request.headers.get("host", "") not in {
        f"localhost:{port}",
        f"127.0.0.1:{port}",
        "testserver",
    }:
        raise HTTPException(403, "local_demo_only")
    if request.headers.get("origin") not in {None, *allowed_origins}:
        raise HTTPException(403, "local_demo_origin_rejected")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "local_demo_cross_site_rejected")


@router.get("/demo-context")
async def context(request: Request):
    boundary(request)
    settings = get_settings()
    used = 0
    if settings.llm_budget_path and settings.llm_budget_path.exists():
        try:
            used = len(json.loads(settings.llm_budget_path.read_text()).get("calls", []))
        except ValueError:
            pass
    return {
        "enabled": True,
        "fictional": True,
        "mode": settings.llm_mode,
        "model": settings.openai_model,
        "max_calls": settings.llm_max_calls,
        "used_calls": used,
    }


@router.post("/demo-session")
async def session(request: Request, body: DemoSessionRequest):
    boundary(request)
    state = json.loads(await asyncio.to_thread(DEMO_STATE.read_text))
    brand_id = uuid.UUID(state["brand_id"])
    user_id = uuid.UUID(state["users"][body.role])
    async with SessionFactory() as db:
        row = (
            await db.execute(
                select(User, BrandMembership)
                .join(BrandMembership, BrandMembership.user_id == User.id)
                .where(
                    User.id == user_id,
                    User.is_active.is_(True),
                    BrandMembership.brand_id == brand_id,
                )
            )
        ).one()
    principal = Principal(
        user_id=user_id, brand_id=brand_id, email=row.User.email, role=row.BrandMembership.role
    )
    token, expires = create_access_token(principal, get_settings())
    return {"access_token": token, "token_type": "bearer", "expires_at": expires}
