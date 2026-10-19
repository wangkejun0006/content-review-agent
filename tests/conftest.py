from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smart_growth_agent.db import models  # noqa: F401
from smart_growth_agent.db.base import Base


@pytest_asyncio.fixture
async def session_factory(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "smart-growth-test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 30},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()
    database_path.unlink(missing_ok=True)


@pytest_asyncio.fixture(autouse=True)
async def offline_model_boundary(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setenv("SMART_GROWTH_LLM_BUDGET_PATH", str(tmp_path / "model-budget.json"))
    async def reject_network(*args, **kwargs):
        raise AssertionError("Offline test attempted external HTTP; use MockTransport")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_network)
