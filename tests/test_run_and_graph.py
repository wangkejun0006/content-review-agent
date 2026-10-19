from __future__ import annotations

import pytest
from sqlalchemy import select

from smart_growth_agent.db.models import Brand, GrowthRun, User
from smart_growth_agent.domain.enums import RegistryType, RunStatus
from smart_growth_agent.domain.errors import ConflictError
from smart_growth_agent.schemas.registry import RegistryItemCreate
from smart_growth_agent.schemas.runs import CampaignBriefCreate
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.services.runs import RunService


@pytest.mark.asyncio
async def test_run_snapshots_active_revisions_and_is_idempotent(session_factory) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Run Brand", slug="run-brand")
        user = User(email="run@example.com", password_hash="unused", display_name="Run User")
        session.add_all([brand, user])
        await session.flush()
        brand_id, user_id = brand.id, user.id

    async with session_factory() as session:
        registry = RegistryService(session)
        product, revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PRODUCT,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="bracelet-01",
                payload={
                    "name": "点阵笔记本",
                    "product_type": "stationery",
                    "description": "模块化科技美学文具",
                    "features": ["NFC 数字体验"],
                    "materials": ["天然材料"],
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id, revision_id=revision.id, actor_id=user_id
        )
        _xhs_rule, xhs_revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PLATFORM_RULE,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="xhs-test-rule",
                payload={
                    "platform": "xhs",
                    "category": "content_compliance",
                    "rule_text": "小红书内容应保持真实。",
                    "severity": "warning",
                    "source_url": "https://example.com/xhs-rule",
                    "verified_at": "2026-07-16T00:00:00+08:00",
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id, revision_id=xhs_revision.id, actor_id=user_id
        )
        _douyin_rule, douyin_revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PLATFORM_RULE,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="douyin-test-rule",
                payload={
                    "platform": "douyin",
                    "category": "content_compliance",
                    "rule_text": "抖音规则预留。",
                    "severity": "warning",
                    "source_url": "https://example.com/douyin-rule",
                    "verified_at": "2026-07-16T00:00:00+08:00",
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id, revision_id=douyin_revision.id, actor_id=user_id
        )
        runs = RunService(session)
        brief = await runs.create_brief(
            brand_id=brand_id,
            actor_id=user_id,
            data=CampaignBriefCreate(
                name="首发种草",
                objective="验证科技美学内容方向",
                product_item_ids=[product.id],
            ),
        )
        run, job, snapshots = await runs.create_growth_run(
            brand_id=brand_id,
            brief_id=brief.id,
            actor_id=user_id,
            idempotency_key="same-request-key",
            max_attempts=3,
        )
        repeated_run, repeated_job, repeated_snapshots = await runs.create_growth_run(
            brand_id=brand_id,
            brief_id=brief.id,
            actor_id=user_id,
            idempotency_key="same-request-key",
            max_attempts=3,
        )
        assert repeated_run.id == run.id
        assert repeated_job.id == job.id
        assert set(snapshots) == set(repeated_snapshots)
        assert revision.id in snapshots
        assert xhs_revision.id in snapshots
        assert douyin_revision.id not in snapshots


@pytest.mark.asyncio
async def test_brief_edit_and_run_archive_preserve_history(session_factory) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Archive Brand", slug="archive-brand")
        user = User(
            email="archive@example.com",
            password_hash="unused",
            display_name="Archive User",
        )
        session.add_all([brand, user])
        await session.flush()
        brand_id, user_id = brand.id, user.id

    async with session_factory() as session:
        registry = RegistryService(session)
        product, revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PRODUCT,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="archive-bracelet",
                payload={
                    "name": "归档测试手链",
                    "product_type": "stationery",
                    "description": "归档测试产品",
                    "features": ["NFC"],
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id,
            revision_id=revision.id,
            actor_id=user_id,
        )
        runs = RunService(session)
        brief = await runs.create_brief(
            brand_id=brand_id,
            actor_id=user_id,
            data=CampaignBriefCreate(
                name="初始 Brief",
                objective="初始目标",
                product_item_ids=[product.id],
            ),
        )
        updated = await runs.update_brief(
            brand_id=brand_id,
            brief_id=brief.id,
            actor_id=user_id,
            data=CampaignBriefCreate(
                name="更新 Brief",
                objective="更新后的内容目标",
                product_item_ids=[product.id],
            ),
        )
        assert updated.name == "更新 Brief"
        brief_id = brief.id

        run, _job, _snapshots = await runs.create_growth_run(
            brand_id=brand_id,
            brief_id=brief_id,
            actor_id=user_id,
            idempotency_key="archive-run-key",
            max_attempts=3,
        )
        run_id = run.id
        with pytest.raises(ConflictError, match="active growth run"):
            await runs.set_run_archived(
                brand_id=brand_id,
                run_id=run_id,
                archived=True,
                actor_id=user_id,
            )
        await session.rollback()

        async with session.begin():
            persisted = await session.scalar(
                select(GrowthRun).where(GrowthRun.id == run_id).with_for_update()
            )
            assert persisted is not None
            persisted.status = RunStatus.FAILED

        archived_run = await runs.set_run_archived(
            brand_id=brand_id,
            run_id=run_id,
            archived=True,
            actor_id=user_id,
        )
        assert archived_run.archived_at is not None
        restored_run = await runs.set_run_archived(
            brand_id=brand_id,
            run_id=run_id,
            archived=False,
            actor_id=user_id,
        )
        assert restored_run.archived_at is None

        archived_brief = await runs.set_brief_archived(
            brand_id=brand_id,
            brief_id=brief_id,
            archived=True,
            actor_id=user_id,
        )
        assert archived_brief.archived_at is not None
        with pytest.raises(ConflictError, match="archived campaign brief"):
            await runs.create_growth_run(
                brand_id=brand_id,
                brief_id=brief_id,
                actor_id=user_id,
                idempotency_key="archived-brief-run",
                max_attempts=3,
            )
        with pytest.raises(ConflictError, match="still has growth runs"):
            await runs.permanently_delete_brief(
                brand_id=brand_id,
                brief_id=brief_id,
                actor_id=user_id,
            )
        await session.rollback()
        await runs.set_run_archived(
            brand_id=brand_id,
            run_id=run_id,
            archived=True,
            actor_id=user_id,
        )
        await runs.permanently_delete_run(
            brand_id=brand_id,
            run_id=run_id,
            actor_id=user_id,
        )
        await runs.permanently_delete_brief(
            brand_id=brand_id,
            brief_id=brief_id,
            actor_id=user_id,
        )
        assert await session.get(GrowthRun, run_id) is None
