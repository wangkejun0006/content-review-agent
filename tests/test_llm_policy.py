import json
import uuid

import httpx
import pytest
from pydantic import SecretStr

from smart_growth_agent.config import Settings
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.llm.openai_compatible import LLMGatewayError, OpenAICompatibleGateway
from smart_growth_agent.llm.policy import provider_settings
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.llm_config import LLMProviderTestOutput
from smart_growth_agent.schemas.phase2 import ProductContextOutput
from smart_growth_agent.schemas.scoring import ScoringOutput


def request(purpose="xhs_product_context", **kwargs):
    return LLMRequest(
        brand_id=uuid.uuid4(),
        purpose=purpose,
        messages=[ChatMessage(role="user", content="fictional JSON")],
        **kwargs,
    )


def test_provider_policy_inherits_every_limit(tmp_path):
    source = Settings(
        llm_max_calls=2,
        llm_budget_path=tmp_path / "shared.json",
        llm_max_output_tokens=777,
        llm_no_network_retry=True,
        llm_request_timeout_seconds=42,
    )
    copied = provider_settings(
        source,
        base_url="https://fixture.example",
        api_key=SecretStr("synthetic-not-a-key"),
        model="fixture",
    )
    for name in [
        "llm_max_calls",
        "llm_budget_path",
        "llm_max_output_tokens",
        "llm_no_network_retry",
        "llm_request_timeout_seconds",
    ]:
        assert getattr(copied, name) == getattr(source, name)


@pytest.mark.asyncio
async def test_direct_contract_rejects_before_budget_or_http(tmp_path):
    path = tmp_path / "budget.json"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("contract must block HTTP")),
        base_url="https://fixture.example",
    ) as client:
        gateway = OpenAICompatibleGateway(
            Settings(openai_api_key="fixture", openai_model="fixture", llm_budget_path=path), client
        )
        for req, schema in [
            (request(), ScoringOutput),
            (request("unknown"), ProductContextOutput),
            (request("configuration_test"), ProductContextOutput),
        ]:
            with pytest.raises(LLMGatewayError):
                await gateway.generate(req, schema)
    assert not path.exists()


@pytest.mark.asyncio
async def test_factory_validates_prompt_before_fake_or_direct(session_factory, tmp_path):
    for mode in ["fake", "openai_compatible"]:
        settings = Settings(
            llm_mode=mode,
            openai_api_key="fixture",
            openai_model="fixture",
            llm_budget_path=tmp_path / "budget.json",
        )
        gateway = build_llm_gateway(settings, session_factory)
        try:
            with pytest.raises(LLMGatewayError, match="Prompt Revision"):
                await gateway.generate(request(), ProductContextOutput)
        finally:
            await gateway.aclose()
    assert not (tmp_path / "budget.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["schema", "repair", "rate_limit", "timeout"])
async def test_all_retries_share_single_budget(tmp_path, failure):
    calls = []

    def handle(req):
        calls.append(json.loads(req.content))
        if failure == "schema":
            return httpx.Response(400, json={"error": {"code": "unsupported"}})
        if failure == "repair":
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture", request=req)
        return httpx.Response(429)

    path = tmp_path / "shared.json"
    settings = Settings(
        openai_api_key="fixture",
        openai_model="fixture",
        llm_budget_path=path,
        llm_max_calls=1,
        llm_no_network_retry=False,
    )
    async with httpx.AsyncClient(
        base_url="https://fixture.example", transport=httpx.MockTransport(handle)
    ) as client:
        gateway = OpenAICompatibleGateway(settings, client)
        with pytest.raises(LLMGatewayError, match="预算"):
            await gateway.generate(request("configuration_test"), LLMProviderTestOutput)
    assert len(calls) == 1
    assert len(json.loads(path.read_text())["calls"]) == 1
    assert calls[0]["max_tokens"] == 4096


def test_budget_and_output_limit_cannot_be_disabled():
    from pydantic import ValidationError

    for values in [{"llm_budget_path": None}, {"llm_max_output_tokens": None}]:
        with pytest.raises(ValidationError):
            Settings(**values)
