import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from pydantic import SecretStr

from smart_growth_agent.config import Settings
from smart_growth_agent.llm.budget import reserve
from smart_growth_agent.llm.openai_compatible import LLMGatewayError, OpenAICompatibleGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.phase2 import ProductContextOutput


def test_cross_process_style_budget_is_atomic_under_concurrency(tmp_path):
    path = tmp_path / "budget.json"

    def call(_):
        try:
            return reserve(path, 3, "fictional-model")
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, range(12)))
    assert len([r for r in results if r is not None]) == 3
    assert len(json.loads(path.read_text())["calls"]) == 3


@pytest.mark.asyncio
async def test_deepseek_json_mode_and_bounded_output(tmp_path):
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "usage": {"prompt_tokens": 30, "completion_tokens": 15},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                ProductContextOutput(summary="虚构演示").model_dump(mode="json")
                            )
                        },
                    }
                ],
            },
        )

    settings = Settings(
        _env_file=None,
        openai_base_url="https://api.deepseek.com",
        openai_model="deepseek-flash",
        openai_api_key=SecretStr("fixture-not-a-key"),
        llm_max_output_tokens=2200,
        llm_budget_path=tmp_path / "budget.json",
        llm_max_calls=1,
    )
    client = httpx.AsyncClient(
        base_url="https://api.deepseek.com", transport=httpx.MockTransport(handle)
    )
    async with client:
        gateway = OpenAICompatibleGateway(settings, client)
        result = await gateway.generate(
            LLMRequest(
                brand_id=uuid.UUID(int=1),
                purpose="xhs_product_context",
                messages=[ChatMessage(role="user", content="虚构产品 JSON")],
            ),
            ProductContextOutput,
        )
    assert result.value.summary == "虚构演示"
    assert result.raw_metadata["structured_output_mode"] == "json_object_local_validation"
    assert captured[0]["response_format"] == {"type": "json_object"}
    assert captured[0]["thinking"] == {"type": "disabled"}
    assert captured[0]["max_tokens"] == 2200
    assert json.loads((tmp_path / "budget.json").read_text())["calls"][0]["prompt_tokens"] == 30


@pytest.mark.asyncio
async def test_unknown_network_outcome_is_not_retried(tmp_path):
    calls = []

    def handle(request):
        calls.append(1)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    settings = Settings(
        _env_file=None,
        openai_base_url="https://api.deepseek.com",
        openai_model="deepseek-flash",
        openai_api_key=SecretStr("fixture-not-a-key"),
        llm_no_network_retry=True,
        llm_budget_path=tmp_path / "budget.json",
    )
    async with httpx.AsyncClient(
        base_url="https://api.deepseek.com", transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(LLMGatewayError, match="停止自动重试"):
            await OpenAICompatibleGateway(settings, client).generate(
                LLMRequest(
                    brand_id=uuid.UUID(int=1),
                    purpose="xhs_product_context",
                    messages=[ChatMessage(role="user", content="虚构产品 JSON")],
                ),
                ProductContextOutput,
            )
    assert len(calls) == 1
    assert (
        json.loads((tmp_path / "budget.json").read_text())["calls"][0]["status"]
        == "outcome_unknown"
    )
