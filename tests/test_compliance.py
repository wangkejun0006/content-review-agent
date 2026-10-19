from __future__ import annotations

import uuid

from smart_growth_agent.schemas.phase2 import ProductContextOutput, WriterOutput
from smart_growth_agent.services.compliance import ComplianceService


def test_deterministic_compliance_blocks_medical_and_false_experience() -> None:
    writer = WriterOutput.model_validate(
        {
            "route_key": "unsafe-route",
            "angle_key": "unsafe-angle",
            "title_options": ["亲测有效", "戴了之后", "医疗级体验"],
            "recommended_title": "亲测有效",
            "body": "测试稿：我戴了7天，治疗效果非常明显，不可直接发布。",
            "visual_brief": {
                "cover_concept": "测试",
                "cover_text": "测试",
                "scene": "测试",
                "shot_list": ["测试"],
                "props_and_background": [],
                "avoid_elements": [],
            },
            "tags": [],
            "cta": "测试",
            "cited_claim_revision_ids": [],
            "source_revision_ids": [str(uuid.uuid4())],
        }
    )
    findings = ComplianceService._deterministic_findings(
        writer=writer,
        product_context=ProductContextOutput(
            summary="测试",
        ),
        snapshot_rows=[],
    )
    categories = {item["category"] for item in findings if item["severity"] == "blocker"}
    assert "medical_claim" in categories
    assert "false_experience" in categories


def test_deterministic_compliance_allows_explicit_non_medical_disclaimer() -> None:
    writer = WriterOutput.model_validate(
        {
            "route_key": "safe-route",
            "angle_key": "safe-angle",
            "title_options": ["日常趋势参考", "一枚消费级戒指", "克制的科技配饰"],
            "recommended_title": "日常趋势参考",
            "body": (
                "这是一款虚构文具示例，不涉及健康或医疗用途。数据仅供个人趋势参考，"
                "不用于诊断、治疗，也不能替代医生。"
            ),
            "visual_brief": {
                "cover_concept": "产品静物",
                "cover_text": "日常趋势参考",
                "scene": "通勤",
                "shot_list": ["产品近景"],
            },
            "cta": "你更关心哪类日常趋势？",
        }
    )

    findings = ComplianceService._deterministic_findings(
        writer=writer,
        product_context=ProductContextOutput(summary="测试"),
        snapshot_rows=[],
    )

    assert not any(item["category"] == "medical_claim" for item in findings)


def test_deterministic_compliance_still_blocks_claim_after_adversative_boundary() -> None:
    writer = WriterOutput.model_validate(
        {
            "route_key": "unsafe-route",
            "angle_key": "unsafe-angle",
            "title_options": ["标题一", "标题二", "标题三"],
            "recommended_title": "标题一",
            "body": "产品不能诊断，但是可以治疗睡眠问题。",
            "visual_brief": {
                "cover_concept": "产品静物",
                "cover_text": "产品介绍",
                "scene": "卧室",
                "shot_list": ["产品近景"],
            },
            "cta": "了解更多",
        }
    )

    findings = ComplianceService._deterministic_findings(
        writer=writer,
        product_context=ProductContextOutput(summary="测试"),
        snapshot_rows=[],
    )

    assert any(
        item["category"] == "medical_claim" and item["evidence_excerpt"] == "治疗"
        for item in findings
    )
