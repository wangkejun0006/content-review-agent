from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.schemas.registry import (
    DEFAULT_SCORING_RUBRIC,
    validate_registry_payload,
)


def test_default_rubric_is_complete_and_totals_100() -> None:
    assert len(DEFAULT_SCORING_RUBRIC.dimensions) == 6
    assert sum(item.weight for item in DEFAULT_SCORING_RUBRIC.dimensions) == 100
    assert DEFAULT_SCORING_RUBRIC.pass_threshold == 70


def test_claim_requires_products_and_evidence() -> None:
    with pytest.raises(ValidationError):
        validate_registry_payload(
            RegistryType.PRODUCT_CLAIM,
            {
                "statement": "监测睡眠",
                "allowed_expressions": ["了解睡眠趋势"],
                "risk_level": "high",
                "product_item_ids": [str(uuid.uuid4())],
                "evidence_document_ids": [],
            },
        )


def test_platform_rule_requires_verified_source() -> None:
    payload = validate_registry_payload(
        RegistryType.PLATFORM_RULE,
        {
            "platform": "xhs",
            "category": "health_claim",
            "rule_text": "不得将消费级设备宣传为医疗器械",
            "severity": "blocker",
            "source_url": "https://example.com/rule",
            "verified_at": datetime.now(UTC).isoformat(),
        },
    )
    assert payload["platform"] == "xhs"


def test_platform_rule_reserves_douyin_namespace() -> None:
    payload = validate_registry_payload(
        RegistryType.PLATFORM_RULE,
        {
            "platform": "douyin",
            "category": "content_compliance",
            "rule_text": "抖音规则入口预留。",
            "severity": "information",
            "source_url": "https://example.com/douyin-rule",
            "verified_at": datetime.now(UTC).isoformat(),
        },
    )
    assert payload["platform"] == "douyin"
