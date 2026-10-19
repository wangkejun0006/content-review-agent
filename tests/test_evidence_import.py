from __future__ import annotations

import pytest

from smart_growth_agent.db.models import Brand
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.llm.fake import DevelopmentFakeLLMGateway
from smart_growth_agent.schemas.registry import RegistryItemCreate
from smart_growth_agent.services.evidence_import import EvidenceImportService
from smart_growth_agent.services.registry import RegistryService


@pytest.mark.asyncio
async def test_fake_evidence_import_preserves_original_content(session_factory) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Evidence Brand", slug="evidence-brand")
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
                stable_key="evidence_registry_import",
                payload={
                    "purpose": "evidence_registry_import",
                    "template": "只整理证据原文，不核验、不改写。",
                    "variables": [],
                    "output_schema_name": "EvidenceImportAIOutput",
                },
            ),
        )
        await registry.activate_revision(
            brand_id=brand_id,
            revision_id=prompt.id,
            actor_id=brand_id,
        )

    original = "规格表第 3 节：NOTE01 支持 NFC 信息交互。"
    draft = await EvidenceImportService(
        session_factory,
        DevelopmentFakeLLMGateway(),
    ).create_draft(
        brand_id=brand_id,
        source_uri="repo://knowledge/products/NOTE01/spec-v1.pdf",
        source_text=original,
        source_name="spec-v1.pdf",
    )

    assert draft.content == original
    assert draft.source_uri.endswith("spec-v1.pdf")
    assert draft.relevant_excerpts == [original]
    assert draft.warnings
