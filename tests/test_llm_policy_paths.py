import json
import uuid
from concurrent.futures import ProcessPoolExecutor

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from smart_growth_agent.app.api.llm_config import test_provider as connection_test
from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import RegistryItem, RegistryRevision
from smart_growth_agent.demo_seed import seed_demo
from smart_growth_agent.domain.enums import Role
from smart_growth_agent.llm.budget import reserve
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.llm.managed import ManagedLLMGateway
from smart_growth_agent.llm.openai_compatible import LLMGatewayError, OpenAICompatibleGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.llm_config import AgentLLMBindingUpsert, LLMProviderCreate
from smart_growth_agent.schemas.phase2 import ProductContextOutput
from smart_growth_agent.services.llm_config import LLMConfigService


def process_reservation(args):
    try:
        return reserve(*args)
    except RuntimeError:
        return None


def test_budget_shared_between_actual_os_processes(tmp_path):
    path = tmp_path / "shared.json"
    with ProcessPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(process_reservation, [(path, 3, "fixture")] * 12))
    assert sum(item is not None for item in results) == 3
    assert len(json.loads(path.read_text())["calls"]) == 3


@pytest.mark.asyncio
async def test_managed_connection_test_and_direct_share_budget(
    session_factory, tmp_path, monkeypatch
):
    state = await seed_demo(
        "offline-fixture-password",
        session_factory=session_factory,
        state_path=tmp_path / "state.json",
    )
    brand = uuid.UUID(state["brand_id"])
    admin = uuid.UUID(state["users"]["admin"])
    settings = Settings(
        credential_encryption_key=SecretStr("offline-fixture-encryption"),
        llm_budget_path=tmp_path / "shared.json",
        llm_max_calls=2,
        llm_max_output_tokens=789,
        llm_request_timeout_seconds=43,
        llm_no_network_retry=True,
    )
    async with session_factory() as session:
        service = LLMConfigService(session, settings)
        provider = await service.create_provider(
            brand_id=brand,
            actor_id=admin,
            data=LLMProviderCreate(
                name="Fictional",
                base_url="https://fixture.example/v1",
                api_key="fixture-never-real",
                default_model="fixture",
            ),
        )
        provider_id = provider.id
        await service.upsert_binding(
            brand_id=brand,
            actor_id=admin,
            purpose="xhs_product_context",
            data=AgentLLMBindingUpsert(provider_config_id=provider_id),
        )
    async with session_factory() as session:
        prompt = await session.scalar(
            select(RegistryRevision)
            .join(RegistryItem, RegistryItem.current_revision_id == RegistryRevision.id)
            .where(RegistryItem.brand_id == brand, RegistryItem.stable_key == "xhs_product_context")
        )
        prompt_id = prompt.id
    captured = []

    def handle(req):
        payload = json.loads(req.content)
        captured.append(payload)
        schema = payload["response_format"]["json_schema"]["name"]
        content = (
            {"status": "ok", "message": "fixture connection"}
            if schema == "LLMProviderTestOutput"
            else ProductContextOutput(summary="fixture").model_dump(mode="json")
        )
        return httpx.Response(
            200,
            json={
                "model": "fixture",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
            },
        )

    original_init = OpenAICompatibleGateway.__init__

    def mock_init(self, dynamic, client=None):
        assert dynamic.llm_budget_path == settings.llm_budget_path
        assert dynamic.llm_max_calls == 2
        assert dynamic.llm_request_timeout_seconds == 43
        assert dynamic.llm_no_network_retry is True
        mock_client = httpx.AsyncClient(
            base_url="https://fixture.example/v1", transport=httpx.MockTransport(handle)
        )
        original_init(self, dynamic, mock_client)
        self._owns_client = True

    monkeypatch.setattr(OpenAICompatibleGateway, "__init__", mock_init)
    req = LLMRequest(
        brand_id=brand,
        purpose="xhs_product_context",
        prompt_revision_id=prompt_id,
        messages=[ChatMessage(role="user", content="fictional JSON")],
    )
    await ManagedLLMGateway(session_factory, settings).generate(req, ProductContextOutput)
    async with session_factory() as session:
        output = await connection_test(
            provider_id=provider_id,
            session=session,
            settings=settings,
            principal=Principal(
                user_id=admin, brand_id=brand, email="admin@paper-orbit.example", role=Role.ADMIN
            ),
        )
    assert output.status == "ok"
    direct = build_llm_gateway(
        settings.model_copy(
            update={
                "llm_mode": "openai_compatible",
                "openai_api_key": SecretStr("fixture"),
                "openai_model": "fixture",
            }
        ),
        session_factory,
    )
    try:
        with pytest.raises(LLMGatewayError, match="预算"):
            await direct.generate(req, ProductContextOutput)
    finally:
        await direct.aclose()
    assert len(captured) == 2
    assert all(p["max_tokens"] == 789 for p in captured)
    assert len(json.loads(settings.llm_budget_path.read_text())["calls"]) == 2
