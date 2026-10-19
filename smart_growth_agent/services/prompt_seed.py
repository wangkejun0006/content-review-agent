from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import BrandMembership, RegistryItem, RegistryRevision
from smart_growth_agent.domain.enums import (
    RegistryType,
    RevisionStatus,
    Role,
    VerificationStatus,
)
from smart_growth_agent.domain.errors import ConflictError, ForbiddenError
from smart_growth_agent.schemas.registry import (
    RegistryItemCreate,
    RegistryRevisionCreate,
    validate_registry_payload,
)
from smart_growth_agent.services.registry import RegistryService, payload_checksum


class PromptSeedEntry(BaseModel):
    stable_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,199}$")
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    payload: dict
    search_text: str = ""


@dataclass(frozen=True)
class PromptSeedResult:
    stable_key: str
    item_id: uuid.UUID
    revision_id: uuid.UUID
    action: str


def load_prompt_seed_file(path: Path) -> list[PromptSeedEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("prompt seed file must contain a JSON array")
    return [PromptSeedEntry.model_validate(entry) for entry in raw]


def load_single_seed_file(path: Path) -> PromptSeedEntry:
    return PromptSeedEntry.model_validate(json.loads(path.read_text(encoding="utf-8")))


async def seed_prompts(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    brand_id: uuid.UUID,
    actor_id: uuid.UUID,
    entries: Sequence[PromptSeedEntry],
    source_uri: str,
    replace_changed_active: bool = False,
) -> list[PromptSeedResult]:
    await _require_admin(session_factory, brand_id=brand_id, actor_id=actor_id)
    results: list[PromptSeedResult] = []
    for entry in entries:
        results.append(
            await _seed_one(
                session_factory=session_factory,
                brand_id=brand_id,
                actor_id=actor_id,
                entry=entry,
                source_uri=source_uri,
                registry_type=RegistryType.PROMPT_TEMPLATE,
                replace_changed_active=replace_changed_active,
            )
        )
    return results


async def seed_scoring_rubric(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    brand_id: uuid.UUID,
    actor_id: uuid.UUID,
    entry: PromptSeedEntry,
    source_uri: str,
    replace_changed_active: bool = False,
) -> PromptSeedResult:
    await _require_admin(session_factory, brand_id=brand_id, actor_id=actor_id)
    return await _seed_one(
        session_factory=session_factory,
        brand_id=brand_id,
        actor_id=actor_id,
        entry=entry,
        source_uri=source_uri,
        registry_type=RegistryType.SCORING_RUBRIC,
        replace_changed_active=replace_changed_active,
    )


async def seed_registry_entries(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    brand_id: uuid.UUID,
    actor_id: uuid.UUID,
    entries: Sequence[PromptSeedEntry],
    source_uri: str,
    registry_type: RegistryType,
    replace_changed_active: bool = False,
) -> list[PromptSeedResult]:
    await _require_admin(session_factory, brand_id=brand_id, actor_id=actor_id)
    results: list[PromptSeedResult] = []
    for entry in entries:
        results.append(
            await _seed_one(
                session_factory=session_factory,
                brand_id=brand_id,
                actor_id=actor_id,
                entry=entry,
                source_uri=source_uri,
                registry_type=registry_type,
                replace_changed_active=replace_changed_active,
            )
        )
    return results


async def _require_admin(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    brand_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        role = await session.scalar(
            select(BrandMembership.role).where(
                BrandMembership.brand_id == brand_id,
                BrandMembership.user_id == actor_id,
            )
        )
    if role != Role.ADMIN:
        raise ForbiddenError("an admin membership is required to seed prompts")


async def _seed_one(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    brand_id: uuid.UUID,
    actor_id: uuid.UUID,
    entry: PromptSeedEntry,
    source_uri: str,
    registry_type: RegistryType,
    replace_changed_active: bool = False,
) -> PromptSeedResult:
    expected_checksum = payload_checksum(validate_registry_payload(registry_type, entry.payload))
    async with session_factory() as session:
        item = await session.scalar(
            select(RegistryItem).where(
                RegistryItem.brand_id == brand_id,
                RegistryItem.registry_type == registry_type,
                RegistryItem.stable_key == entry.stable_key,
            )
        )
        active = None
        matching_draft = None
        if item is not None:
            revisions = list(
                await session.scalars(
                    select(RegistryRevision)
                    .where(RegistryRevision.item_id == item.id)
                    .order_by(RegistryRevision.version.desc())
                )
            )
            active = next(
                (revision for revision in revisions if revision.status == RevisionStatus.ACTIVE),
                None,
            )
            matching_draft = next(
                (
                    revision
                    for revision in revisions
                    if revision.status == RevisionStatus.DRAFT
                    and _matches(revision, entry, expected_checksum, source_uri)
                ),
                None,
            )

    if item is not None and active is not None:
        if (
            not _matches(active, entry, expected_checksum, source_uri)
            and not replace_changed_active
        ):
            raise ConflictError(
                f"active prompt {entry.stable_key!r} differs from the seed file; "
                "existing content was not overwritten"
            )
        if _matches(active, entry, expected_checksum, source_uri):
            return PromptSeedResult(entry.stable_key, item.id, active.id, "reused")

    if item is None:
        async with session_factory() as session:
            item, draft = await RegistryService(session).create_item(
                brand_id=brand_id,
                registry_type=registry_type,
                data=RegistryItemCreate(
                    stable_key=entry.stable_key,
                    payload=entry.payload,
                    search_text=entry.search_text,
                    source_uri=source_uri,
                    verification_status=entry.verification_status,
                ),
                actor_id=actor_id,
            )
        action = "created"
    elif matching_draft is not None:
        draft = matching_draft
        action = "activated_existing_draft"
    else:
        async with session_factory() as session:
            draft = await RegistryService(session).create_revision(
                brand_id=brand_id,
                item_id=item.id,
                data=RegistryRevisionCreate(
                    payload=entry.payload,
                    search_text=entry.search_text,
                    source_uri=source_uri,
                    verification_status=entry.verification_status,
                ),
                actor_id=actor_id,
                expected_type=registry_type,
            )
        action = "created_revision"

    async with session_factory() as session:
        active = await RegistryService(session).activate_revision(
            brand_id=brand_id,
            revision_id=draft.id,
            actor_id=actor_id,
            expected_type=registry_type,
        )
    return PromptSeedResult(entry.stable_key, item.id, active.id, action)


def _matches(
    revision: RegistryRevision,
    entry: PromptSeedEntry,
    checksum: str,
    source_uri: str,
) -> bool:
    return (
        revision.checksum == checksum
        and revision.verification_status == entry.verification_status
        and revision.source_uri == source_uri
        and revision.search_text == entry.search_text
    )
