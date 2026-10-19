from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from smart_growth_agent.db.models import Brand, RegistryLink, User
from smart_growth_agent.domain.enums import RegistryType, RevisionStatus
from smart_growth_agent.domain.errors import ConflictError, ValidationError
from smart_growth_agent.schemas.registry import (
    EvidenceDocumentCreate,
    RegistryItemCreate,
    RegistryRevisionCreate,
    RegistryRevisionUpdate,
)
from smart_growth_agent.services.registry import RegistryService


async def create_identity(session_factory):
    async with session_factory() as session, session.begin():
        brand = Brand(name="Test Brand", slug=f"brand-{uuid.uuid4().hex[:8]}")
        user = User(
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password_hash="unused",
            display_name="Tester",
        )
        session.add_all([brand, user])
        await session.flush()
        return brand.id, user.id


async def create_active_product(service, brand_id, user_id):
    item, revision = await service.create_item(
        brand_id=brand_id,
        registry_type=RegistryType.PRODUCT,
        actor_id=user_id,
        data=RegistryItemCreate(
            stable_key="ring-01",
            payload={
                "name": "桌面收纳夹",
                "product_type": "desk_accessory",
                "description": "消费级健康趋势监测设备",
                "features": ["睡眠趋势记录"],
                "materials": ["钛合金"],
            },
        ),
    )
    active = await service.activate_revision(
        brand_id=brand_id, revision_id=revision.id, actor_id=user_id
    )
    return item, active


@pytest.mark.asyncio
async def test_revision_activation_is_immutable_and_retires_previous(session_factory) -> None:
    brand_id, user_id = await create_identity(session_factory)
    async with session_factory() as session:
        service = RegistryService(session)
        item, first = await create_active_product(service, brand_id, user_id)
        item_id = item.id
        first_id = first.id
        with pytest.raises(ConflictError):
            await service.update_revision(
                brand_id=brand_id,
                revision_id=first_id,
                actor_id=user_id,
                data=RegistryRevisionUpdate(search_text="must fail"),
            )

        second = await service.create_revision(
            brand_id=brand_id,
            item_id=item_id,
            actor_id=user_id,
            data=RegistryRevisionCreate(
                payload={
                    "name": "桌面收纳夹二版",
                    "product_type": "desk_accessory",
                    "description": "更新后的消费级设备",
                    "features": ["睡眠趋势记录", "活动趋势记录"],
                    "materials": ["钛合金"],
                }
            ),
        )
        await service.activate_revision(brand_id=brand_id, revision_id=second.id, actor_id=user_id)
        await session.refresh(first)
        await session.refresh(item)
        assert first.status == RevisionStatus.RETIRED
        assert second.status == RevisionStatus.ACTIVE
        assert item.current_revision_id == second.id


@pytest.mark.asyncio
async def test_claim_requires_verified_evidence_and_active_product(session_factory) -> None:
    brand_id, user_id = await create_identity(session_factory)
    async with session_factory() as session:
        service = RegistryService(session)
        product, _ = await create_active_product(service, brand_id, user_id)
        product_id = product.id
        unverified = await service.create_evidence(
            brand_id=brand_id,
            actor_id=user_id,
            data=EvidenceDocumentCreate(
                title="产品测试报告",
                document_type="test_report",
                source_uri="internal://reports/ring-01",
                content="测试记录",
            ),
        )
        claim, claim_revision = await service.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PRODUCT_CLAIM,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="sleep-trend",
                payload={
                    "statement": "记录睡眠趋势",
                    "allowed_expressions": ["帮助了解睡眠趋势"],
                    "forbidden_expressions": ["治疗失眠"],
                    "risk_level": "high",
                    "product_item_ids": [str(product_id)],
                    "evidence_document_ids": [str(unverified.id)],
                },
            ),
        )
        claim_id = claim.id
        claim_revision_id = claim_revision.id
        with pytest.raises(ValidationError):
            await service.activate_revision(
                brand_id=brand_id, revision_id=claim_revision_id, actor_id=user_id
            )

        verified = await service.create_evidence(
            brand_id=brand_id,
            actor_id=user_id,
            data=EvidenceDocumentCreate(
                title="已审核测试报告",
                document_type="test_report",
                source_uri="internal://reports/ring-01-verified",
                content="已审核的测试记录",
            ),
        )
        await service.verify_evidence(brand_id=brand_id, document_id=verified.id, actor_id=user_id)
        await service.update_revision(
            brand_id=brand_id,
            revision_id=claim_revision_id,
            actor_id=user_id,
            data=RegistryRevisionUpdate(
                payload={
                    "statement": "记录睡眠趋势",
                    "allowed_expressions": ["帮助了解睡眠趋势"],
                    "forbidden_expressions": ["治疗失眠"],
                    "risk_level": "high",
                    "product_item_ids": [str(product_id)],
                    "evidence_document_ids": [str(verified.id)],
                }
            ),
        )
        active = await service.activate_revision(
            brand_id=brand_id, revision_id=claim_revision_id, actor_id=user_id
        )
        assert active.status == RevisionStatus.ACTIVE
        claim_item = await service.repository.get_item(brand_id, claim_id)
        assert claim_item is not None
        assert claim_item.current_revision_id == active.id
        links = list(
            await session.scalars(
                select(RegistryLink).where(RegistryLink.source_revision_id == active.id)
            )
        )
        assert [link.target_item_id for link in links] == [product_id]


@pytest.mark.asyncio
async def test_registry_item_archive_is_reversible_and_hidden_by_default(
    session_factory,
) -> None:
    brand_id, user_id = await create_identity(session_factory)
    async with session_factory() as session:
        service = RegistryService(session)
        item, active = await create_active_product(service, brand_id, user_id)
        item_id = item.id

        archived = await service.set_item_archived(
            brand_id=brand_id,
            item_id=item_id,
            archived=True,
            actor_id=user_id,
            expected_type=RegistryType.PRODUCT,
        )
        assert archived.archived_at is not None
        assert archived.current_revision_id == active.id
        assert await service.repository.list_items(brand_id, RegistryType.PRODUCT) == []
        assert [
            row.id
            for row in await service.repository.list_items(
                brand_id,
                RegistryType.PRODUCT,
                include_archived=True,
            )
        ] == [item_id]
        await session.rollback()

        restored = await service.set_item_archived(
            brand_id=brand_id,
            item_id=item_id,
            archived=False,
            actor_id=user_id,
            expected_type=RegistryType.PRODUCT,
        )
        assert restored.archived_at is None
        assert [
            row.id
            for row in await service.repository.list_items(brand_id, RegistryType.PRODUCT)
        ] == [item_id]
        await session.rollback()
        await service.set_item_archived(
            brand_id=brand_id,
            item_id=item_id,
            archived=True,
            actor_id=user_id,
            expected_type=RegistryType.PRODUCT,
        )
        await service.permanently_delete_item(
            brand_id=brand_id,
            item_id=item_id,
            actor_id=user_id,
            expected_type=RegistryType.PRODUCT,
        )
        assert await service.repository.get_item(brand_id, item_id) is None
