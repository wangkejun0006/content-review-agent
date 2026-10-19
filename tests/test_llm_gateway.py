from __future__ import annotations

import json
import uuid

import httpx
import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy import func, select

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import (
    AgentLLMBinding,
    Brand,
    LLMCallLog,
    LLMProviderConfig,
    RegistryItem,
    RegistryRevision,
)
from smart_growth_agent.domain.enums import RegistryType, RevisionStatus, VerificationStatus
from smart_growth_agent.llm.managed import ManagedLLMGateway
from smart_growth_agent.llm.openai_compatible import LLMGatewayError, OpenAICompatibleGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest, LLMResult, LLMUsage
from smart_growth_agent.schemas.phase2 import ProductContextOutput
from smart_growth_agent.security import CredentialCipher


class ExampleOutput(BaseModel):
    direction: str


class MappingOutput(BaseModel):
    field_confidence: dict[str, float]


@pytest.mark.asyncio
async def test_managed_gateway_logs_success_before_business_validation(
    session_factory, monkeypatch
) -> None:
    settings = Settings(
        llm_mode="managed",
        credential_encryption_key=SecretStr("telemetry-test-encryption-key"),
    )
    async with session_factory() as session, session.begin():
        brand = Brand(name="Telemetry Brand", slug="telemetry-brand")
        session.add(brand)
        await session.flush()
        prompt_item = RegistryItem(
            brand_id=brand.id,
            registry_type=RegistryType.PROMPT_TEMPLATE,
            stable_key="xhs_product_context",
        )
        session.add(prompt_item)
        await session.flush()
        prompt = RegistryRevision(
            item_id=prompt_item.id,
            version=1,
            status=RevisionStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
            payload={
                "purpose": "xhs_product_context",
                "template": "test",
                "variables": [],
                "output_schema_name": "ProductContextOutput",
            },
            search_text="test",
            checksum="a" * 64,
            created_by=brand.id,
        )
        session.add(prompt)
        await session.flush()
        prompt_item.current_revision_id = prompt.id
        provider = LLMProviderConfig(
            brand_id=brand.id,
            name="Telemetry Provider",
            provider_type="openai_compatible",
            base_url="https://llm.example/v1",
            api_key_encrypted=CredentialCipher(settings).encrypt("secret-key"),
            default_model="test-model",
            created_by=brand.id,
        )
        session.add(provider)
        await session.flush()
        session.add(
            AgentLLMBinding(
                brand_id=brand.id,
                purpose="xhs_product_context",
                provider_config_id=provider.id,
                created_by=brand.id,
            )
        )
        brand_id = brand.id
        prompt_id = prompt.id

    async def fake_generate(_gateway, _request, _response_model):
        return LLMResult(
            value=ProductContextOutput(summary="typed response"),
            provider="openai-compatible",
            model="test-model",
            usage=LLMUsage(input_tokens=12, output_tokens=8),
            latency_ms=21,
            provider_request_id="provider-call-1",
        )

    async def fake_close(_gateway):
        return None

    monkeypatch.setattr(OpenAICompatibleGateway, "generate", fake_generate)
    monkeypatch.setattr(OpenAICompatibleGateway, "aclose", fake_close)
    result = await ManagedLLMGateway(session_factory, settings).generate(
        LLMRequest(
            brand_id=brand_id,
            purpose="xhs_product_context",
            prompt_revision_id=prompt_id,
            messages=[ChatMessage(role="user", content="test")],
        ),
        ProductContextOutput,
    )

    assert result.telemetry_logged is True
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(LLMCallLog))
        log = await session.scalar(select(LLMCallLog))
    assert count == 1
    assert log is not None
    assert log.provider_request_id == "provider-call-1"
    assert log.input_tokens == 12


@pytest.mark.asyncio
async def test_gateway_uses_configured_request_timeout() -> None:
    gateway = OpenAICompatibleGateway(
        Settings(
            openai_api_key="test-key",
            openai_model="test-model",
            llm_request_timeout_seconds=240,
        )
    )
    assert gateway.client.timeout.read == 240
    await gateway.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_gateway_returns_typed_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert sent["response_format"]["type"] == "json_schema"
        schema = sent["response_format"]["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["direction"]
        return httpx.Response(
            200,
            json={
                "id": "call-1",
                "model": "test-model",
                "choices": [{"message": {"content": json.dumps({"direction": "科技美学"})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://llm.example/v1"
    )
    gateway = OpenAICompatibleGateway(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            openai_api_key="test-key",
            openai_model="test-model",
        ),
        client=client,
    )
    result = await gateway.generate(
        LLMRequest(
            brand_id=uuid.uuid4(),
            purpose="adapter_example",
            messages=[ChatMessage(role="user", content="生成内容方向")],
        ),
        ExampleOutput,
    )
    assert result.value.direction == "科技美学"
    assert result.usage.input_tokens == 10
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_gateway_exposes_safe_billing_error() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            402,
            json={"base_resp": {"status_code": 1008, "status_msg": "insufficient balance"}},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://llm.example/v1"
    )
    gateway = OpenAICompatibleGateway(
        Settings(openai_api_key="test-key", openai_model="test-model"),
        client=client,
    )
    with pytest.raises(LLMGatewayError, match="余额或 Token Plan 额度不足") as caught:
        await gateway.generate(
            LLMRequest(
                brand_id=uuid.uuid4(),
                purpose="adapter_example",
                messages=[ChatMessage(role="user", content="整理规则")],
            ),
            ExampleOutput,
        )
    assert caught.value.provider_status == 402
    assert caught.value.provider_code == "1008"
    assert calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_gateway_explains_schema_incompatibility() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "unsupported"}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://llm.example/v1",
    )
    gateway = OpenAICompatibleGateway(
        Settings(openai_api_key="test-key", openai_model="test-model"),
        client=client,
    )
    with pytest.raises(LLMGatewayError, match="JSON Schema"):
        await gateway.generate(
            LLMRequest(
                brand_id=uuid.uuid4(),
                purpose="adapter_example",
                messages=[ChatMessage(role="user", content="生成内容")],
            ),
            ExampleOutput,
        )
    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_gateway_falls_back_to_prompt_schema() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        sent = json.loads(request.content)
        if calls == 1:
            assert "response_format" in sent
            return httpx.Response(400, json={"error": {"message": "unsupported"}})
        assert "response_format" not in sent
        assert "JSON Schema" in sent["messages"][-1]["content"]
        return httpx.Response(
            200,
            json={
                "id": "fallback-call",
                "model": "compatible-model",
                "choices": [{"message": {"content": '{"direction":"科技美学"}'}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://llm.example/v1"
    )
    gateway = OpenAICompatibleGateway(
        Settings(openai_api_key="test-key", openai_model="compatible-model"),
        client=client,
    )
    result = await gateway.generate(
        LLMRequest(
            brand_id=uuid.uuid4(),
            purpose="adapter_example",
            messages=[ChatMessage(role="user", content="生成内容")],
        ),
        ExampleOutput,
    )
    assert result.value.direction == "科技美学"
    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_compatible_gateway_strips_reasoning_before_json() -> None:
    content = (
        '<think>分析过程，包含 {"ignore": true}</think>\n'
        '```json\n{"direction":"科技美学"}\n```'
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "id": "reasoning-call",
                    "model": "reasoning-model",
                    "choices": [{"message": {"content": content}}],
                    "usage": {},
                },
            )
        ),
        base_url="https://llm.example/v1",
    )
    gateway = OpenAICompatibleGateway(
        Settings(openai_api_key="test-key", openai_model="reasoning-model"),
        client=client,
    )
    result = await gateway.generate(
        LLMRequest(
            brand_id=uuid.uuid4(),
            purpose="adapter_example",
            messages=[ChatMessage(role="user", content="生成策略")],
        ),
        ExampleOutput,
    )
    assert result.value.direction == "科技美学"
    await client.aclose()


@pytest.mark.asyncio
async def test_minimax_gateway_uses_prompt_schema_instead_of_response_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert "response_format" not in sent
        assert sent["reasoning_split"] is True
        assert sent["temperature"] == 0.1
        contract = sent["messages"][-1]["content"]
        assert "ExampleOutput" in contract
        assert '["direction"]' in contract
        return httpx.Response(
            200,
            json={
                "id": "minimax-call",
                "model": "MiniMax-M2.1",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": (
                                "<think>先检查字段。</think>\n"
                                '```json\n{"direction":"科技美学"}\n```'
                            )
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "completion_tokens_details": {"reasoning_tokens": 3},
                },
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.minimax.io/v1",
    )
    gateway = OpenAICompatibleGateway(
        Settings(
            openai_base_url="https://api.minimax.io/v1",
            openai_api_key="test-key",
            openai_model="MiniMax-M2.1",
        ),
        client=client,
    )
    result = await gateway.generate(
        LLMRequest(
            brand_id=uuid.uuid4(),
            purpose="adapter_example",
            temperature=0.1,
            messages=[ChatMessage(role="user", content="整理产品")],
        ),
        ExampleOutput,
    )
    assert result.value.direction == "科技美学"
    assert result.raw_metadata["structured_output_mode"] == "prompt_json_schema"
    assert result.raw_metadata["reasoning_tokens"] == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_minimax_gateway_repairs_invalid_typed_json_once() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        sent = json.loads(request.content)
        assert "response_format" not in sent
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "model": "MiniMax-M2.1",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": '{"direction":["科技美学"]}'},
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                    "base_resp": {"status_code": 0},
                },
            )
        assert "上一个回答未通过本地结构校验" in sent["messages"][-1]["content"]
        assert "JSON Schema" in sent["messages"][-1]["content"]
        return httpx.Response(
            200,
            json={
                "model": "MiniMax-M2.1",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"direction":"科技美学"}'},
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6},
                "base_resp": {"status_code": 0},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.minimax.io/v1",
    )
    gateway = OpenAICompatibleGateway(
        Settings(
            openai_base_url="https://api.minimax.io/v1",
            openai_api_key="test-key",
            openai_model="MiniMax-M2.1",
        ),
        client=client,
    )
    result = await gateway.generate(
        LLMRequest(
            brand_id=uuid.uuid4(),
            purpose="adapter_example",
            messages=[ChatMessage(role="user", content="整理产品")],
        ),
        ExampleOutput,
    )
    assert result.value.direction == "科技美学"
    assert calls == 2
    assert result.usage.input_tokens == 22
    assert result.usage.output_tokens == 10
    assert result.raw_metadata["provider_attempts"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_strict_schema_keeps_mapping_value_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        field_schema = sent["response_format"]["json_schema"]["schema"]["properties"][
            "field_confidence"
        ]
        assert field_schema["additionalProperties"]["type"] == "number"
        return httpx.Response(
            200,
            json={
                "model": "schema-model",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"field_confidence":{"name":0.9}}'
                        },
                    }
                ],
                "usage": {},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://llm.example/v1",
    )
    gateway = OpenAICompatibleGateway(
        Settings(openai_api_key="test-key", openai_model="schema-model"),
        client=client,
    )
    result = await gateway.generate(
        LLMRequest(
            brand_id=uuid.uuid4(),
            purpose="adapter_mapping",
            messages=[ChatMessage(role="user", content="整理产品")],
        ),
        MappingOutput,
    )
    assert result.value.field_confidence["name"] == 0.9
    await client.aclose()


@pytest.mark.asyncio
async def test_minimax_gateway_raises_business_error_from_success_http_status() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "choices": [],
                    "base_resp": {
                        "status_code": 1039,
                        "status_msg": "token limit exceeded",
                    },
                },
            )
        ),
        base_url="https://api.minimax.io/v1",
    )
    gateway = OpenAICompatibleGateway(
        Settings(
            openai_base_url="https://api.minimax.io/v1",
            openai_api_key="test-key",
            openai_model="MiniMax-M2.1",
        ),
        client=client,
    )
    with pytest.raises(LLMGatewayError, match="Token 上限") as caught:
        await gateway.generate(
            LLMRequest(
                brand_id=uuid.uuid4(),
                purpose="adapter_example",
                messages=[ChatMessage(role="user", content="整理产品")],
            ),
            ExampleOutput,
        )
    assert caught.value.provider_code == "1039"
    await client.aclose()

@pytest.fixture(autouse=True)
def adapter_test_contracts(monkeypatch):
    from smart_growth_agent.llm.contracts import LLM_OUTPUT_CONTRACTS
    monkeypatch.setitem(LLM_OUTPUT_CONTRACTS, "adapter_example", ExampleOutput)
    monkeypatch.setitem(LLM_OUTPUT_CONTRACTS, "adapter_mapping", MappingOutput)
