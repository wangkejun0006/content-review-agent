import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import RegistryItem, RegistryRevision
from smart_growth_agent.demo_seed import seed_demo
from smart_growth_agent.domain.enums import RevisionStatus
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.llm.openai_compatible import LLMGatewayError
from smart_growth_agent.llm.policy import validate_registry_contract
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.phase2 import ProductContextOutput
from smart_growth_agent.schemas.registry import RegistryRevisionCreate
from smart_growth_agent.services.registry import RegistryService


@pytest.mark.asyncio
async def test_prompt_schema_brand_and_status_before_any_paid_call(session_factory, tmp_path):
    state = await seed_demo(
        "offline-fixture-password",
        session_factory=session_factory,
        state_path=tmp_path / "state.json",
    )
    brand = uuid.UUID(state["brand_id"])
    actor = uuid.UUID(state["users"]["admin"])
    async with session_factory() as session:
        item = await session.scalar(
            select(RegistryItem).where(
                RegistryItem.brand_id == brand, RegistryItem.stable_key == "xhs_product_context"
            )
        )
        old = await session.get(RegistryRevision, item.current_revision_id)
        item_id, old_id, payload = item.id, old.id, old.payload.copy()
    req = LLMRequest(
        brand_id=brand,
        purpose="xhs_product_context",
        prompt_revision_id=old_id,
        messages=[ChatMessage(role="user", content="{}")],
    )
    async with session_factory() as session:
        service = RegistryService(session)
        new = await service.create_revision(
            brand_id=brand,
            item_id=item_id,
            actor_id=actor,
            data=RegistryRevisionCreate(
                payload={**payload, "template": payload["template"] + "\nV2"}
            ),
        )
        new_id = new.id
        await service.activate_revision(brand_id=brand, revision_id=new_id, actor_id=actor)
    # An immutable older revision remains valid for historical runs.
    await validate_registry_contract(session_factory, req, ProductContextOutput)
    for mode in ["fake", "managed", "openai_compatible"]:
        settings = Settings(
            llm_mode=mode,
            openai_api_key="fixture",
            openai_model="fixture",
            credential_encryption_key=SecretStr("fixture-encryption"),
            llm_budget_path=tmp_path / "budget.json",
        )
        gateway = build_llm_gateway(settings, session_factory)
        try:
            with pytest.raises(LLMGatewayError):
                await gateway.generate(
                    req.model_copy(update={"brand_id": uuid.uuid4()}), ProductContextOutput
                )
            async with session_factory() as session, session.begin():
                revision = await session.get(RegistryRevision, new_id)
                revision.payload = {**payload, "output_schema_name": "WriterOutput"}
            with pytest.raises(LLMGatewayError, match="输出契约"):
                await gateway.generate(
                    req.model_copy(update={"prompt_revision_id": new_id}), ProductContextOutput
                )
            async with session_factory() as session, session.begin():
                revision = await session.get(RegistryRevision, new_id)
                revision.payload = payload
                revision.status = RevisionStatus.DRAFT
            with pytest.raises(LLMGatewayError):
                await gateway.generate(
                    req.model_copy(update={"prompt_revision_id": new_id}), ProductContextOutput
                )
            async with session_factory() as session, session.begin():
                revision = await session.get(RegistryRevision, new_id)
                revision.status = RevisionStatus.ACTIVE
        finally:
            close = getattr(gateway, "aclose", None)
            if close:
                await close()
    assert not (tmp_path / "budget.json").exists()
