from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import ConflictError
from smart_growth_agent.schemas.registry import RegistryRevisionCreate
from smart_growth_agent.services.auth import AuthService
from smart_growth_agent.services.prompt_seed import (
    load_prompt_seed_file,
    load_single_seed_file,
    seed_prompts,
    seed_registry_entries,
    seed_scoring_rubric,
)
from smart_growth_agent.services.registry import RegistryService

PROMPT_FILE = (
    Path(__file__).parents[1]
    / "smart_growth_agent"
    / "prompts"
    / "phase2_templates.json"
)
SOURCE_URI = "repo://smart_growth_agent/prompts/phase2_templates.json"
RUBRIC_FILE = (
    Path(__file__).parents[1]
    / "smart_growth_agent"
    / "knowledge"
    / "brand"
    / "phase4_rubric.json"
)
PLATFORM_RULES_FILE = (
    Path(__file__).parents[1]
    / "smart_growth_agent"
    / "knowledge"
    / "platform"
    / "xhs_demo_rules.json"
)


async def _admin(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as session:
        brand, user = await AuthService(session).bootstrap_admin(
            brand_name="Test Brand",
            brand_slug="test-brand",
            email="admin@example.com",
            display_name="Admin",
            password="a-secure-test-password",
        )
    return brand.id, user.id


async def test_seed_prompts_is_idempotent(session_factory) -> None:
    brand_id, actor_id = await _admin(session_factory)
    entries = load_prompt_seed_file(PROMPT_FILE)

    first = await seed_prompts(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entries=entries,
        source_uri=SOURCE_URI,
    )
    second = await seed_prompts(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entries=entries,
        source_uri=SOURCE_URI,
    )

    assert len(first) == 9
    assert {result.action for result in first} == {"created"}
    assert {result.action for result in second} == {"reused"}
    assert [(row.item_id, row.revision_id) for row in first] == [
        (row.item_id, row.revision_id) for row in second
    ]


async def test_seed_does_not_overwrite_different_active_prompt(session_factory) -> None:
    brand_id, actor_id = await _admin(session_factory)
    entry = load_prompt_seed_file(PROMPT_FILE)[0]
    await seed_prompts(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entries=[entry],
        source_uri=SOURCE_URI,
    )

    async with session_factory() as session:
        service = RegistryService(session)
        item = (await service.repository.list_items(brand_id, RegistryType.PROMPT_TEMPLATE))[0]
        await session.commit()
        replacement = await service.create_revision(
            brand_id=brand_id,
            item_id=item.id,
            data=RegistryRevisionCreate(payload={**entry.payload, "template": "changed"}),
            actor_id=actor_id,
        )
        await service.activate_revision(
            brand_id=brand_id,
            revision_id=replacement.id,
            actor_id=actor_id,
        )

    with pytest.raises(ConflictError, match="was not overwritten"):
        await seed_prompts(
            session_factory=session_factory,
            brand_id=brand_id,
            actor_id=actor_id,
            entries=[entry],
            source_uri=SOURCE_URI,
        )


async def test_seed_scoring_rubric_is_idempotent(session_factory) -> None:
    brand_id, actor_id = await _admin(session_factory)
    entry = load_single_seed_file(RUBRIC_FILE)
    source_uri = "repo://smart_growth_agent/knowledge/brand/phase4_rubric.json"

    first = await seed_scoring_rubric(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entry=entry,
        source_uri=source_uri,
    )
    second = await seed_scoring_rubric(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entry=entry,
        source_uri=source_uri,
    )

    assert first.action == "created"
    assert second.action == "reused"
    assert (first.item_id, first.revision_id) == (second.item_id, second.revision_id)


async def test_seed_platform_rules_is_concise_and_idempotent(session_factory) -> None:
    brand_id, actor_id = await _admin(session_factory)
    entries = load_prompt_seed_file(PLATFORM_RULES_FILE)
    source_uri = "synthetic://paper-orbit/demo-rules-v1"

    first = await seed_registry_entries(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entries=entries,
        source_uri=source_uri,
        registry_type=RegistryType.PLATFORM_RULE,
    )
    second = await seed_registry_entries(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entries=entries,
        source_uri=source_uri,
        registry_type=RegistryType.PLATFORM_RULE,
    )

    assert len(first) == 10
    assert {result.action for result in first} == {"created"}
    assert {result.action for result in second} == {"reused"}
