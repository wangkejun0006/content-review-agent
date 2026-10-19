from __future__ import annotations

from datetime import UTC, datetime

import pytest

from smart_growth_agent.db.models import Brand, RegistryItem
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.llm.fake import DevelopmentFakeLLMGateway
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import LLMResult, LLMUsage
from smart_growth_agent.schemas.registry import RegistryItemCreate
from smart_growth_agent.services.platform_rule_import import PlatformRuleImportService
from smart_growth_agent.services.registry import RegistryService


class InvalidExcerptGateway(LLMGateway):
    async def generate(self, request, response_model):
        value = response_model.model_validate(
            {
                "stable_key": "invalid-source-rule",
                "category": "content_compliance",
                "rule_text": "不得虚构内容。",
                "severity": "blocker",
                "confidence": 0.9,
                "source_excerpt": "原文中不存在的句子",
                "warnings": [],
            }
        )
        return LLMResult(
            value=value,
            provider="fake",
            model="fake",
            usage=LLMUsage(input_tokens=1, output_tokens=1),
            latency_ms=1,
        )


@pytest.mark.asyncio
async def test_platform_rule_ai_import_returns_draft_without_creating_rule(
    session_factory,
) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Rule Import Brand", slug="rule-import-brand")
        session.add(brand)
        await session.flush()
        brand_id = brand.id

    async with session_factory() as session:
        registry = RegistryService(session)
        _item, prompt = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PROMPT_TEMPLATE,
            actor_id=brand_id,
            data=RegistryItemCreate(
                stable_key="platform_rule_import",
                payload={
                    "purpose": "platform_rule_import",
                    "template": "只整理规则原文。",
                    "variables": [],
                    "output_schema_name": "PlatformRuleAIOutput",
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id,
            revision_id=prompt.id,
            actor_id=brand_id,
        )

    draft = await PlatformRuleImportService(
        session_factory,
        DevelopmentFakeLLMGateway(),
    ).create_draft(
        brand_id=brand_id,
        source_text="非医疗设备不得宣传疾病治疗功效。",
        source_url="https://example.com/official-rule",
        verified_at=datetime.now(UTC),
    )
    assert draft.payload["category"] == "health_claim"
    assert draft.payload["source_url"] == "https://example.com/official-rule"

    async with session_factory() as session:
        rules = await session.scalars(
            RegistryItem.__table__.select().where(
                RegistryItem.registry_type == RegistryType.PLATFORM_RULE
            )
        )
        assert list(rules) == []


@pytest.mark.asyncio
async def test_platform_rule_import_rejects_unverifiable_excerpt(session_factory) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Citation Brand", slug="citation-brand")
        session.add(brand)
        await session.flush()
        brand_id = brand.id

    async with session_factory() as session:
        registry = RegistryService(session)
        _item, prompt = await registry.create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PROMPT_TEMPLATE,
            actor_id=brand_id,
            data=RegistryItemCreate(
                stable_key="platform_rule_import",
                payload={
                    "purpose": "platform_rule_import",
                    "template": "只整理规则原文。",
                    "variables": [],
                    "output_schema_name": "PlatformRuleAIOutput",
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id,
            revision_id=prompt.id,
            actor_id=brand_id,
        )

    with pytest.raises(ValidationError, match="无法在原文中定位"):
        await PlatformRuleImportService(
            session_factory,
            InvalidExcerptGateway(),
        ).create_draft(
            brand_id=brand_id,
            source_text="平台要求内容真实。",
            source_url="https://example.com/rule",
            verified_at=datetime.now(UTC),
        )
