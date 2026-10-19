from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from smart_growth_agent.db.models import Brand, RegistryItem, RegistryRevision, User
from smart_growth_agent.domain.enums import (
    KnowledgeCriticality,
    RegistryType,
    RetrievalMethod,
    RevisionStatus,
    VerificationStatus,
)
from smart_growth_agent.llm.unavailable import UnavailableLLMGateway
from smart_growth_agent.research.gateway import NullResearchGateway
from smart_growth_agent.schemas.knowledge import KnowledgeSourceCreate
from smart_growth_agent.schemas.phase2 import ProductContextOutput
from smart_growth_agent.schemas.registry import RegistryItemCreate
from smart_growth_agent.schemas.runs import CampaignBriefCreate
from smart_growth_agent.services.knowledge import KnowledgeService
from smart_growth_agent.services.phase2 import Phase2Service
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.services.runs import RunService


@pytest.mark.asyncio
async def test_critical_stale_rule_warns_without_blocking_local_run(session_factory) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Knowledge Brand", slug="knowledge-brand")
        user = User(email="knowledge@example.com", password_hash="unused", display_name="Reviewer")
        session.add_all([brand, user])
        await session.flush()
        brand_id, user_id = brand.id, user.id

    source_url = "https://example.com/xhs-rules"
    async with session_factory() as session:
        knowledge = KnowledgeService(session)
        await knowledge.create_source(
            brand_id=brand_id,
            actor_id=user_id,
            data=KnowledgeSourceCreate(
                name="小红书公开规则测试来源",
                source_type="platform_rule",
                platform="xhs",
                canonical_url=source_url,
                retrieval_method=RetrievalMethod.MANUAL,
                freshness_days=90,
                criticality=KnowledgeCriticality.CRITICAL,
            ),
        )
        registry = RegistryService(session)
        product, product_revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PRODUCT,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="governance-product",
                payload={
                    "name": "测试手链",
                    "product_type": "stationery",
                    "description": "测试资料",
                    "features": ["待确认"],
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id, revision_id=product_revision.id, actor_id=user_id
        )
        _rule, rule_revision = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PLATFORM_RULE,
            actor_id=user_id,
            data=RegistryItemCreate(
                stable_key="xhs-basic-health-rule",
                source_uri=source_url,
                payload={
                    "platform": "xhs",
                    "category": "health_claim",
                    "rule_text": "不得夸大健康效果",
                    "severity": "blocker",
                    "source_url": source_url,
                    "verified_at": datetime(2020, 1, 1, tzinfo=UTC).isoformat(),
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id, revision_id=rule_revision.id, actor_id=user_id
        )
        runs = RunService(session)
        brief = await runs.create_brief(
            brand_id=brand_id,
            actor_id=user_id,
            data=CampaignBriefCreate(
                name="Knowledge freshness",
                objective="验证规则时效",
                product_item_ids=[product.id],
            ),
        )
        run, _job, _snapshots = await runs.create_growth_run(
            brand_id=brand_id,
            brief_id=brief.id,
            actor_id=user_id,
            idempotency_key="freshness-local-run",
            max_attempts=3,
        )
        issues = await knowledge.evaluate_run_freshness(
            brand_id=brand_id, run_id=run.id
        )
        assert len(issues) == 1
        assert issues[0].critical is True
        assert issues[0].stale is True

    phase2 = Phase2Service(
        session_factory, UnavailableLLMGateway(), NullResearchGateway()
    )
    blocked, serialized = await phase2.check_knowledge_freshness(
        brand_id=brand_id,
        run_id=run.id,
    )
    assert blocked is False
    assert serialized[0]["stable_key"] == "xhs-basic-health-rule"


def test_product_context_drops_invented_claim_when_snapshot_has_no_claims() -> None:
    brand_id = uuid.uuid4()
    product_item_id = uuid.uuid4()
    product_item = RegistryItem(
        id=product_item_id,
        brand_id=brand_id,
        registry_type=RegistryType.PRODUCT,
        stable_key="ring-without-claims",
    )
    product_revision = RegistryRevision(
        id=uuid.uuid4(),
        item_id=product_item.id,
        version=1,
        status=RevisionStatus.DRAFT,
        verification_status=VerificationStatus.PROVISIONAL,
        payload={
            "name": "测试戒指",
            "description": "消费级桌面收纳夹",
            "features": ["睡眠趋势记录"],
            "materials": ["纸质内页"],
            "non_medical_disclaimer": "本产品不是医疗器械",
        },
        checksum="0" * 64,
        created_by=uuid.uuid4(),
    )
    output = ProductContextOutput.model_validate(
        {
            "summary": "测试上下文",
            "relevant_facts": [
                {
                    "revision_id": str(product_revision.id),
                    "statement": "这是一款消费级智能桌面收纳夹",
                }
            ],
            "allowed_claims": [
                {
                    "claim_revision_id": str(uuid.uuid4()),
                    "statement": "未经证实的声明",
                    "allowed_expression": "未经证实的表达",
                }
            ],
        }
    )

    governed = Phase2Service._apply_product_context_governance(
        output, [(product_item, product_revision, "selected_product")]
    )

    assert governed.allowed_claims == []
    assert governed.relevant_facts == []
    assert {fact.statement for fact in governed.provisional_facts} == {
        "测试戒指",
        "消费级桌面收纳夹",
        "睡眠趋势记录",
        "纸质内页",
        "本产品不是医疗器械",
    }
    assert "ring-without-claims" not in governed.summary
    assert any("没有已激活的 Product Claim" in item for item in governed.missing_information)
    assert any("未能逐字映射" in item for item in governed.missing_information)
