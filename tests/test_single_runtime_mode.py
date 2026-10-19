from __future__ import annotations

from smart_growth_agent.db.models import Brand
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.schemas.registry import RegistryItemCreate
from smart_growth_agent.schemas.runs import CampaignBriefCreate
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.services.runs import RunService


async def test_run_can_start_without_product_claims(session_factory) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Single Mode Brand", slug="single-mode-brand")
        session.add(brand)
        await session.flush()
        brand_id = brand.id
        actor_id = brand.id

    async with session_factory() as session:
        registry = RegistryService(session)
        product, revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PRODUCT,
            actor_id=actor_id,
            data=RegistryItemCreate(
                stable_key="claimless-product",
                payload={
                    "name": "无 Claim 测试产品",
                    "product_type": "stationery",
                    "description": "仅用于验证缺少证据时仍可启动内容任务。",
                    "features": ["基础外观描述"],
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id,
            revision_id=revision.id,
            actor_id=actor_id,
        )
        runs = RunService(session)
        brief = await runs.create_brief(
            brand_id=brand_id,
            actor_id=actor_id,
            data=CampaignBriefCreate(
                name="无 Claim 内容任务",
                objective="生成不涉及未证实功效的内容",
                product_item_ids=[product.id],
            ),
        )
        run, _job, snapshots = await runs.create_growth_run(
            brand_id=brand_id,
            brief_id=brief.id,
            actor_id=actor_id,
            idempotency_key="claimless-product-run",
            max_attempts=3,
        )

    assert run.id is not None
    assert revision.id in snapshots
