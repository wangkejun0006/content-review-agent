from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import RegistryItem, RegistryRevision
from smart_growth_agent.domain.enums import RegistryType


class RegistryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_item(
        self, brand_id: uuid.UUID, item_id: uuid.UUID, *, for_update: bool = False
    ) -> RegistryItem | None:
        statement: Select[tuple[RegistryItem]] = select(RegistryItem).where(
            RegistryItem.id == item_id, RegistryItem.brand_id == brand_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_items(
        self,
        brand_id: uuid.UUID,
        registry_type: RegistryType,
        *,
        include_archived: bool = False,
    ) -> list[RegistryItem]:
        statement = select(RegistryItem).where(
            RegistryItem.brand_id == brand_id,
            RegistryItem.registry_type == registry_type,
        )
        if not include_archived:
            statement = statement.where(RegistryItem.archived_at.is_(None))
        result = await self.session.scalars(statement.order_by(RegistryItem.stable_key))
        return list(result)

    async def get_revision(
        self,
        brand_id: uuid.UUID,
        revision_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> RegistryRevision | None:
        statement = (
            select(RegistryRevision)
            .join(RegistryItem, RegistryItem.id == RegistryRevision.item_id)
            .where(RegistryRevision.id == revision_id, RegistryItem.brand_id == brand_id)
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_revisions(
        self, brand_id: uuid.UUID, item_id: uuid.UUID
    ) -> list[RegistryRevision]:
        result = await self.session.scalars(
            select(RegistryRevision)
            .join(RegistryItem, RegistryItem.id == RegistryRevision.item_id)
            .where(RegistryRevision.item_id == item_id, RegistryItem.brand_id == brand_id)
            .order_by(RegistryRevision.version.desc())
        )
        return list(result)
