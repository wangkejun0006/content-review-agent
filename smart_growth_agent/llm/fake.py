from __future__ import annotations

import json
import uuid
from typing import TypeVar

from pydantic import BaseModel

from smart_growth_agent.llm.types import LLMRequest, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


class DevelopmentFakeLLMGateway:
    """Deterministic, zero-cost responses for local workflow tests."""

    is_fake = True

    async def generate(self, request: LLMRequest, response_model: type[T]) -> LLMResult[T]:
        payload = self._payload(request)
        return LLMResult[T](
            value=response_model.model_validate(payload),
            provider="development-fake",
            model="deterministic-fixture-v1",
            usage=LLMUsage(input_tokens=0, output_tokens=0),
            latency_ms=0,
            provider_request_id=f"fake-{uuid.uuid4()}",
            raw_metadata={"paid_call": False},
        )

    def _payload(self, request: LLMRequest) -> dict:
        inputs = json.loads(request.messages[-1].content)
        if request.purpose == "xhs_product_context":
            product = next(
                item for item in inputs["registry"] if item["registry_type"] == "product"
            )
            return {
                "summary": f"{product['payload']['name']} 的产品上下文。",
                "relevant_facts": [],
                "allowed_claims": [],
                "provisional_facts": [
                    {
                        "revision_id": product["revision_id"],
                        "statement": product["payload"]["description"],
                    }
                ],
                "forbidden_claims": ["不得补充未经验证的产品功能或健康效果"],
                "missing_information": ["部分产品事实和 Claim 尚缺少可验证证据"],
            }
        if request.purpose == "xhs_strategy":
            return self._strategy_payload(inputs)
        if request.purpose == "xhs_writer":
            return self._writer_payload(inputs)
        if request.purpose == "xhs_compliance_semantic":
            return {
                "summary": "Fake 语义审查未发现额外阻断项。",
                "findings": [],
                "requires_revision": False,
            }
        if request.purpose == "xhs_scoring":
            route_key = inputs["content"]["route_key"]
            score = {
                "aesthetic-detail": 84,
                "aesthetic-question": 80,
                "daily-object": 76,
            }.get(route_key, 78)
            return {
                "summary": "Fake Scoring 按固定规则返回内部质量分，不预测流量。",
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
                "revision_suggestions": [],
            }
        if request.purpose == "xhs_feedback":
            publication = inputs["publications"][0]
            latest = publication["metric_snapshots"][-1]
            scope = (
                max(
                    (item["strength"] for item in inputs["attribution_evidence"]),
                    key={"correlative": 0, "assisted": 1, "direct": 2}.get,
                )
                if inputs["attribution_evidence"]
                else "correlative"
            )
            return {
                "summary": "Fake Feedback 基于冻结指标生成测试建议，不预测实际流量。",
                "observations": [
                    {
                        "statement": f"当前冻结快照的阅读数为 {latest.get('views')}。",
                        "evidence_ids": [latest["id"]],
                        "attribution_scope": "correlative",
                        "confidence": 0.8,
                    }
                ],
                "hypotheses": [
                    {
                        "statement": "视觉细节角度可继续进行受控测试。",
                        "rationale": "当前仅有内容自身累计数据，尚不能建立因果关系。",
                        "attribution_scope": scope,
                        "confidence": 0.55,
                    }
                ],
                "actions": [
                    {
                        "action": "保留同一内容角度，测试新的封面和标题表达。",
                        "rationale": "用单变量测试减少解释歧义。",
                        "priority": "high",
                        "expected_signal": "收藏率或互动率相对同类历史内容改善",
                    }
                ],
                "confidence": 0.65,
                "attribution_scope": scope,
                "limitations": ["Fake LLM 结果只用于开发测试。"],
            }
        if request.purpose == "product_registry_import":
            source_names = [source["name"] for source in inputs["sources"]]
            combined = "\n".join(source["text"] for source in inputs["sources"])
            is_note01 = "NOTE01" in combined.upper()
            if "演示资料版本:" in combined:
                from smart_growth_agent.demo_fixtures import product_import_fixture

                return product_import_fixture(combined, source_names)

            return {
                "stable_key": "paper-orbit-note01-ai-draft" if is_note01 else "product-ai-draft",
                "payload": {
                    "name": "Paper Orbit NOTE01 点阵笔记本" if is_note01 else "待确认产品",
                    "sku": "NOTE01" if is_note01 else None,
                    "product_type": "stationery",
                    "description": "由 Fake LLM 根据上传资料整理的测试草稿，所有事实需人工确认。",
                    "features": ["内页为点阵布局（待确认）", "封面可选雾蓝色（待确认）"],
                    "materials": [],
                    "non_medical_disclaimer": "虚构文具示例，不涉及健康或医疗用途。",
                },
                "search_text": "Paper Orbit NOTE01 点阵笔记本 AI 导入草稿",
                "field_confidence": {
                    "name": 0.8,
                    "sku": 0.8,
                    "features": 0.45,
                    "materials": 0.1,
                },
                "missing_fields": ["天然材料的权威规格", "最终量产功能确认"],
                "warnings": [
                    "Fake LLM 不会验证产品事实。",
                    "原始资料中的健康、疗愈和监测表述不得直接作为 Product Claim。",
                ],
                "source_summaries": [
                    {"source_name": name, "summary": "已提取文字，等待运营人员核对。"}
                    for name in source_names
                ],
            }
        if request.purpose == "platform_rule_import":
            if "RULE_CURRENT" in inputs["source_text"]:
                return {
                    "stable_key": "p0-current-rule",
                    "category": "content_compliance",
                    "rule_text": "不得把没有证据的效率提升百分比或防水承诺写成产品效果。",
                    "severity": "blocker",
                    "confidence": 0.8,
                    "source_excerpt": "不得把没有证据的效率提升百分比或防水承诺写成产品效果。",
                    "warnings": ["虚构平台规则，确定性离线 fixture，不是真实政策。"],
                }
            return {
                "stable_key": "xhs-health-claims-ai-draft",
                "category": "health_claim",
                "rule_text": "消费级非医疗设备不得明示或暗示具有疾病诊断或治疗功效。",
                "severity": "blocker",
                "confidence": 0.65,
                "source_excerpt": inputs["source_text"][:120],
                "warnings": ["Fake LLM 仅整理结构，必须由运营人员对照官方原文核验。"],
            }
        if request.purpose == "evidence_registry_import":
            source_text = inputs["source_text"]
            return {
                "title": f"{inputs['source_name']}（AI 整理草稿）",
                "document_type": "product_specification",
                "source_summary": "已保留原始文字，并整理出可能与产品声明相关的摘录。",
                "relevant_excerpts": [source_text[:160]],
                "confidence": 0.6,
                "warnings": ["AI 未核验证据真实性，保存后仍需 Reviewer 对照原文件确认。"],
            }
        raise RuntimeError(f"development fake has no fixture for purpose: {request.purpose}")

    @staticmethod
    def _strategy_payload(inputs: dict) -> dict:
        allowed_claims = [
            item["claim_revision_id"]
            for item in inputs["product_context"].get("allowed_claims", [])
        ]
        common = {"allowed_claim_revision_ids": allowed_claims}
        constraints = inputs["brief"]["constraints"]
        return {
            "objective": inputs["brief"]["objective"],
            "target_audience": "喜欢纸笔记录与桌面整理的虚构人群",
            "key_message": inputs["brief"]["constraints"].get("key_message")
            or "清晰展示纸笔记录与桌面整理场景",
            "brand_voice": inputs["brief"]["constraints"].get("tone")
            or ["克制", "生活化", "科技美学"],
            "guardrails": ["不虚构体验", "不生成未经验证的功能或健康效果"],
            "marketing_support": {
                "policy": constraints.get("marketing_support_policy", "evaluate"),
                "recommended": False,
                "program_revision_ids": [],
                "program_names": [],
                "rationale": ["默认先验证自然内容表现"],
                "prerequisites": [],
                "application_checklist": [],
                "budget_assumptions": ["未提供可确认的投放预算"],
                "measurement_plan": ["发布后登记曝光、收藏和评论累计指标"],
                "human_decision_required": True,
            },
            "creative_routes": [
                {
                    **common,
                    "route_key": "aesthetic-detail",
                    "angle_key": "technology-aesthetic",
                    "angle_name": "科技美学细节",
                    "premise": "从造型细节切入",
                    "target_emotion": "审美认同",
                    "hook_mechanism": "细节发现",
                    "scene": "通勤书桌布置",
                    "variation_axes": ["hook"],
                    "visual_direction": "产品轮廓与书桌布置近景",
                    "cta_direction": "邀请讨论",
                },
                {
                    **common,
                    "route_key": "aesthetic-question",
                    "angle_key": "technology-aesthetic",
                    "angle_name": "科技美学讨论",
                    "premise": "用问题讨论科技与文具的关系",
                    "target_emotion": "好奇",
                    "hook_mechanism": "提问",
                    "scene": "日常配饰选择",
                    "variation_axes": ["narrative", "tone"],
                    "visual_direction": "留白静物构图",
                    "cta_direction": "邀请表达偏好",
                },
                {
                    **common,
                    "route_key": "daily-object",
                    "angle_key": "daily-object",
                    "angle_name": "日常科技物件",
                    "premise": "从随身物件切入",
                    "target_emotion": "亲近感",
                    "hook_mechanism": "场景代入",
                    "scene": "出门前整理配饰",
                    "variation_axes": ["scene"],
                    "visual_direction": "桌面与书写场景",
                    "cta_direction": "建议收藏",
                },
            ],
        }

    @staticmethod
    def _writer_payload(inputs: dict) -> dict:
        route = inputs["creative_route"]
        source_ids = [
            item["revision_id"] for item in inputs["product_context"].get("provisional_facts", [])
        ]
        route_key = route["route_key"]
        body = (
            "这是一篇由开发环境 Fake LLM 生成的品牌官方流程草稿。"
            "它只用于验证系统流程，不代表已经确认的产品功能，也不可直接发布。"
        )
        # One explicit fixture, not general natural-language instruction following.
        if (
            inputs.get("revision_instructions")
            == "请补充虚构演示标识，并说明资料不足时需补充证据。"
        ):
            body += (
                "\n【虚构演示】资料不足时暂停无依据结论，向负责人请求补充证据，重新核对后再审核。"
            )
        return {
            "route_key": route_key,
            "angle_key": route["angle_key"],
            "title_options": [
                f"{route['angle_name']}｜一种新的日常细节",
                f"当科技感进入配饰，会是什么样？{route_key}",
                f"今天的书桌布置细节，来自一件创意文具 {route_key}",
            ],
            "recommended_title": f"{route['angle_name']}｜一种新的日常细节",
            "body": body,
            "visual_brief": {
                "cover_concept": route["visual_direction"],
                "cover_text": "科技也可以是一种日常细节",
                "scene": route["scene"],
                "shot_list": ["产品近景", "使用或搭配场景", "材质细节占位镜头"],
                "props_and_background": ["纯色背景", "日常配饰"],
                "avoid_elements": ["医疗场景", "未经确认的功能图示"],
            },
            "media_plan": {
                "preferred_format": "image_set",
                "rationale": "静物与使用细节更适合当前科技美学路线",
                "preferred_generation_prompt": (
                    "小红书3:4竖图，点阵笔记本产品近景，蓝色品牌调性，自然光，"
                    "真实材质，留白构图，包含通勤搭配与细节图，不改变产品结构"
                ),
                "alternate_format": "video",
                "alternate_generation_prompt": "将产品近景与通勤书写场景剪成15秒竖屏短视频",
                "aspect_ratio": "3:4",
                "duration_seconds": None,
                "image_sequence": ["封面产品近景", "通勤书写场景", "材质细节"],
                "shot_list": [],
                "voiceover": "",
                "on_screen_text": ["科技也可以是一种日常细节"],
                "negative_prompts": ["医疗场景", "虚构功能界面", "改变产品结构"],
                "shooting_notes": ["优先使用登记的产品示意图（虚构演示）作为参考"],
                "product_media_ids": [],
                "claim_revision_ids": [],
            },
            "tags": ["创意文具", "日常书桌布置", "纸笔记录"],
            "cta": "你更在意创意文具的外观，还是它融入日常的方式？",
            "cited_claim_revision_ids": [],
            "source_revision_ids": source_ids,
        }
