from __future__ import annotations

import json
import uuid

from pydantic import BaseModel

from smart_growth_agent.llm.types import LLMRequest, LLMResult, LLMUsage
from smart_growth_agent.schemas.phase2 import TrendResearchOutput


class FakePhase2LLM:
    def __init__(
        self,
        *,
        unsafe_draft_routes: set[str] | None = None,
        always_unsafe_routes: set[str] | None = None,
        score_by_route: dict[str, int] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.unsafe_draft_routes = unsafe_draft_routes or set()
        self.always_unsafe_routes = always_unsafe_routes or set()
        self.score_by_route = score_by_route or {}

    async def generate(self, request: LLMRequest, response_model: type[BaseModel]) -> LLMResult:
        self.calls.append(request.purpose)
        user_payload = json.loads(request.messages[-1].content)
        if request.purpose == "xhs_product_context":
            product = next(
                item for item in user_payload["registry"] if item["registry_type"] == "product"
            )
            payload = {
                "summary": "用于测试的点阵笔记本创意文具资料。",
                "relevant_facts": [],
                "allowed_claims": [],
                "provisional_facts": [
                    {
                        "revision_id": product["revision_id"],
                        "statement": product["payload"]["description"],
                    }
                ],
                "forbidden_claims": ["不得生成健康效果或医疗结论"],
                "missing_information": ["正式材料和功能声明尚待确认"],
            }
        elif request.purpose == "xhs_strategy":
            payload = {
                "objective": "建立创意文具认知",
                "target_audience": "关注书桌布置与消费电子的城市女性",
                "key_message": "用克制的科技细节丰富日常造型",
                "brand_voice": ["克制", "生活化", "科技美学"],
                "guardrails": ["不虚构体验", "不生成健康效果"],
                "marketing_support": {
                    "policy": user_payload["brief"]["constraints"].get(
                        "marketing_support_policy", "evaluate"
                    ),
                    "recommended": False,
                    "program_revision_ids": [],
                    "program_names": [],
                    "rationale": ["先验证自然内容"],
                    "prerequisites": [],
                    "application_checklist": [],
                    "budget_assumptions": [],
                    "measurement_plan": ["登记发布指标"],
                    "human_decision_required": True,
                },
                "creative_routes": [
                    {
                        "route_key": "aesthetic-detail",
                        "angle_key": "technology-aesthetic",
                        "angle_name": "科技美学细节",
                        "premise": "从造型细节切入",
                        "target_emotion": "审美认同",
                        "hook_mechanism": "细节发现",
                        "scene": "通勤书桌布置",
                        "variation_axes": ["hook"],
                        "allowed_claim_revision_ids": [],
                        "visual_direction": "近景展示文具轮廓",
                        "cta_direction": "邀请讨论",
                    },
                    {
                        "route_key": "aesthetic-question",
                        "angle_key": "technology-aesthetic",
                        "angle_name": "科技美学讨论",
                        "premise": "用问题引出科技与文具的关系",
                        "target_emotion": "好奇",
                        "hook_mechanism": "提问",
                        "scene": "日常配饰选择",
                        "variation_axes": ["narrative", "tone"],
                        "allowed_claim_revision_ids": [],
                        "visual_direction": "留白构图",
                        "cta_direction": "邀请表达偏好",
                    },
                    {
                        "route_key": "daily-object",
                        "angle_key": "daily-object",
                        "angle_name": "日常科技物件",
                        "premise": "从随身物件切入",
                        "target_emotion": "亲近感",
                        "hook_mechanism": "场景代入",
                        "scene": "出门前整理配饰",
                        "variation_axes": ["scene"],
                        "allowed_claim_revision_ids": [],
                        "visual_direction": "桌面静物",
                        "cta_direction": "建议收藏",
                    },
                ],
            }
        elif request.purpose == "xhs_writer":
            route = user_payload["creative_route"]
            source_ids = [
                item["revision_id"]
                for item in user_payload["product_context"].get("provisional_facts", [])
            ]
            base = route["route_key"]
            is_rewrite = user_payload.get("task") == "targeted_compliance_rewrite"
            unsafe = base in self.always_unsafe_routes or (
                base in self.unsafe_draft_routes and not is_rewrite
            )
            payload = {
                "route_key": base,
                "angle_key": route["angle_key"],
                "title_options": [f"{base} 标题一", f"{base} 标题二", f"{base} 标题三"],
                "recommended_title": f"{base} 标题一",
                "body": (
                    "这是一篇品牌官方测试草稿：我戴了7天，治疗效果明显，不可发布。"
                    if unsafe
                    else "这是一篇品牌官方测试草稿，仅讨论创意文具的视觉表达。"
                ),
                "visual_brief": {
                    "cover_concept": "克制的产品近景",
                    "cover_text": "科技也可以是一种日常细节",
                    "scene": route["scene"],
                    "shot_list": ["产品近景", "搭配场景"],
                    "props_and_background": ["纯色背景"],
                    "avoid_elements": ["医疗场景"],
                },
                "media_plan": {
                    "preferred_format": "image_set",
                    "rationale": "适合展示产品细节",
                    "preferred_generation_prompt": (
                        "小红书3:4竖图，真实点阵笔记本近景与通勤搭配，不改变产品结构"
                    ),
                    "alternate_format": "video",
                    "alternate_generation_prompt": "15秒竖屏产品细节短视频",
                    "aspect_ratio": "3:4",
                    "duration_seconds": None,
                    "image_sequence": ["封面近景", "书写场景"],
                    "shot_list": [],
                    "voiceover": "",
                    "on_screen_text": ["创意文具日常细节"],
                    "negative_prompts": ["医疗场景", "虚构功能"],
                    "shooting_notes": ["使用真实产品作为参考"],
                    "product_media_ids": [],
                    "claim_revision_ids": [],
                },
                "tags": ["创意文具", "日常书桌布置"],
                "cta": "你会如何搭配这样的创意文具？",
                "cited_claim_revision_ids": [],
                "source_revision_ids": source_ids,
            }
        elif request.purpose == "xhs_compliance_semantic":
            payload = {
                "summary": "Fake 语义审查未发现额外阻断项。",
                "findings": [],
                "requires_revision": False,
            }
        elif request.purpose == "xhs_scoring":
            route_key = user_payload["content"]["route_key"]
            score = self.score_by_route.get(route_key, 80)
            payload = {
                "summary": "Fake 内部质量评分。",
                "dimensions": [
                    {"name": name, "score": score, "rationale": "Fake 固定评分理由。"}
                    for name in [
                        "Hook",
                        "Emotion",
                        "Authenticity",
                        "Visual",
                        "SaveValue",
                        "Conversion",
                    ]
                ],
                "revision_suggestions": (
                    ["增强开头与收藏价值。"] if score < 70 else []
                ),
            }
        else:
            raise AssertionError(f"unexpected LLM purpose: {request.purpose}")
        value = response_model.model_validate(payload)
        return LLMResult(
            value=value,
            provider="fake",
            model="fake-phase2",
            usage=LLMUsage(input_tokens=10, output_tokens=20),
            latency_ms=1,
            provider_request_id=str(uuid.uuid4()),
        )


class FakeResearchGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def research(self, request) -> TrendResearchOutput:
        self.calls += 1
        return TrendResearchOutput(
            limitations=[f"fake research for {request.product_keywords}"]
        )
