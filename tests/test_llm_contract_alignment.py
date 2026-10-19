from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from smart_growth_agent.config import Settings
from smart_growth_agent.llm.contracts import LLM_OUTPUT_CONTRACTS, contract_mismatch
from smart_growth_agent.llm.openai_compatible import OpenAICompatibleGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.llm_config import MANAGED_LLM_PURPOSES

PROMPT_FILE = (
    Path(__file__).resolve().parents[1]
    / "smart_growth_agent"
    / "prompts"
    / "phase2_templates.json"
)
UUID_1 = "11111111-1111-4111-8111-111111111111"


def _simple_payloads() -> dict[str, dict]:
    routes = [
        {
            "route_key": f"route-{index}",
            "angle_key": "daily-style",
            "angle_name": "日常造型",
            "premise": f"表达路径 {index}",
            "target_emotion": "好奇",
            "hook_mechanism": "细节提问",
            "scene": "通勤",
            "variation_axes": ["hook"],
            "allowed_claim_revision_ids": [],
            "visual_direction": "产品近景",
            "cta_direction": "邀请讨论",
        }
        for index in range(1, 4)
    ]
    dimensions = [
        {"name": name, "score": 80, "rationale": "结构完整。"}
        for name in [
            "Hook",
            "Emotion",
            "Authenticity",
            "Visual",
            "SaveValue",
            "Conversion",
        ]
    ]
    return {
        "product_registry_import": {
            "stable_key": "test-product",
            "payload": {
                "name": "测试产品",
                "sku": "T-01",
                "product_type": "stationery",
                "description": "用于结构验证的产品草稿。",
                "features": ["测试功能（待确认）"],
                "materials": [],
                "non_medical_disclaimer": "消费级电子产品，不属于医疗设备。",
            },
            "search_text": "测试产品 T-01",
            "field_confidence": {"name": 0.8},
            "missing_fields": [],
            "warnings": [],
            "source_summaries": [
                {"source_name": "test.xlsx", "summary": "已读取测试资料。"}
            ],
        },
        "evidence_registry_import": {
            "title": "测试规格资料",
            "document_type": "product_specification",
            "source_summary": "测试摘要。",
            "relevant_excerpts": ["测试摘录。"],
            "confidence": 0.8,
            "warnings": [],
        },
        "platform_rule_import": {
            "stable_key": "xhs-test-rule",
            "category": "content_compliance",
            "rule_text": "测试规则。",
            "severity": "warning",
            "confidence": 0.8,
            "source_excerpt": "测试规则原文。",
            "warnings": [],
        },
        "xhs_product_context": {
            "summary": "测试产品上下文。",
            "relevant_facts": [{"revision_id": UUID_1, "statement": "测试事实。"}],
            "allowed_claims": [],
            "provisional_facts": [],
            "forbidden_claims": [],
            "missing_information": [],
        },
        "xhs_strategy": {
            "objective": "测试内容方向",
            "target_audience": "测试受众",
            "key_message": "测试核心信息",
            "brand_voice": ["克制"],
            "guardrails": ["不虚构体验"],
            "creative_routes": routes,
        },
        "xhs_writer": {
            "route_key": "route-1",
            "angle_key": "daily-style",
            "title_options": ["标题一", "标题二", "标题三"],
            "recommended_title": "标题一",
            "body": "用于结构测试的正文。",
            "visual_brief": {
                "cover_concept": "产品近景",
                "cover_text": "测试封面",
                "scene": "通勤",
                "shot_list": ["产品特写"],
                "props_and_background": [],
                "avoid_elements": [],
            },
            "media_plan": {
                "preferred_format": "image_set",
                "rationale": "适合展示产品细节",
                "preferred_generation_prompt": "生成克制的产品静物图",
                "alternate_format": "video",
                "alternate_generation_prompt": "生成产品细节短视频",
                "aspect_ratio": "3:4",
                "duration_seconds": None,
                "image_sequence": ["封面", "细节"],
                "shot_list": [],
                "voiceover": "",
                "on_screen_text": [],
                "negative_prompts": [],
                "shooting_notes": [],
                "product_media_ids": [],
                "claim_revision_ids": [],
            },
            "tags": ["智能文具"],
            "cta": "你更喜欢哪种设计？",
            "cited_claim_revision_ids": [],
            "source_revision_ids": [UUID_1],
        },
        "xhs_compliance_semantic": {
            "summary": "未发现额外问题。",
            "findings": [],
            "requires_revision": False,
        },
        "xhs_scoring": {
            "summary": "测试评分。",
            "dimensions": dimensions,
            "revision_suggestions": [],
        },
        "xhs_feedback": {
            "summary": "测试反馈。",
            "observations": [
                {
                    "statement": "阅读数已记录。",
                    "evidence_ids": [UUID_1],
                    "attribution_scope": "correlative",
                    "confidence": 0.8,
                }
            ],
            "hypotheses": [],
            "actions": [
                {
                    "action": "继续测试标题。",
                    "rationale": "减少变量。",
                    "priority": "medium",
                    "expected_signal": "收藏率变化",
                }
            ],
            "confidence": 0.7,
            "attribution_scope": "correlative",
            "limitations": [],
        },
    }


def test_every_managed_purpose_has_one_matching_prompt_contract() -> None:
    entries = json.loads(PROMPT_FILE.read_text(encoding="utf-8"))
    prompts = {entry["payload"]["purpose"]: entry for entry in entries}

    assert set(MANAGED_LLM_PURPOSES) == set(LLM_OUTPUT_CONTRACTS) == set(prompts)
    for purpose, response_model in LLM_OUTPUT_CONTRACTS.items():
        assert prompts[purpose]["payload"]["output_schema_name"] == response_model.__name__


def test_contract_gate_rejects_code_or_prompt_mismatch() -> None:
    expected = LLM_OUTPUT_CONTRACTS["xhs_scoring"]
    assert (
        contract_mismatch(
            purpose="xhs_scoring",
            response_model=expected,
            prompt_schema_name=expected.__name__,
        )
        is None
    )
    assert "代码输出契约" in str(
        contract_mismatch(
            purpose="xhs_scoring",
            response_model=LLM_OUTPUT_CONTRACTS["xhs_writer"],
            prompt_schema_name=expected.__name__,
        )
    )
    assert "Prompt 输出契约" in str(
        contract_mismatch(
            purpose="xhs_scoring",
            response_model=expected,
            prompt_schema_name="WrongOutput",
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose", MANAGED_LLM_PURPOSES)
async def test_minimax_parses_simple_json_for_every_agent_contract(purpose: str) -> None:
    response_model: type[BaseModel] = LLM_OUTPUT_CONTRACTS[purpose]
    expected = response_model.model_validate(_simple_payloads()[purpose])

    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert "response_format" not in sent
        assert sent["reasoning_split"] is True
        assert response_model.__name__ in sent["messages"][-1]["content"]
        return httpx.Response(
            200,
            json={
                "id": f"mock-{purpose}",
                "model": "MiniMax-M2.7",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": expected.model_dump_json()},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
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
            openai_model="MiniMax-M2.7",
        ),
        client=client,
    )
    result = await gateway.generate(
        LLMRequest(
            brand_id=uuid.uuid4(),
            purpose=purpose,
            messages=[ChatMessage(role="user", content="{}")],
        ),
        response_model,
    )
    assert result.value == expected
    await client.aclose()
