from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.schemas.phase2 import MediaPlan
from smart_growth_agent.schemas.registry import validate_registry_payload
from smart_growth_agent.schemas.runs import BriefConstraints


def test_marketing_program_registry_payload_is_governed() -> None:
    payload = validate_registry_payload(
        RegistryType.PLATFORM_MARKETING_PROGRAM,
        {
            "platform": "xhs",
            "name": "蒲公英产品众测",
            "program_type": "product_trial",
            "objectives": ["content_validation", "creator_seeding"],
            "description": "用于产品体验内容验证，最终资格以官方平台为准。",
            "eligibility_requirements": ["满足平台准入要求"],
            "required_assets": ["产品资料与合规声明"],
            "application_steps": ["运营人员登录官方平台提交"],
            "budget_guidance": "向平台确认",
            "measurement_signals": ["合规内容产出数"],
            "source_url": "https://pgy.xiaohongshu.com/",
            "verified_at": datetime.now(UTC),
        },
    )
    assert payload["program_type"] == "product_trial"


def test_brief_rejects_inverted_marketing_budget() -> None:
    with pytest.raises(ValidationError, match="marketing_budget_max"):
        BriefConstraints(marketing_budget_min=20_000, marketing_budget_max=5_000)


def test_video_media_plan_requires_duration_and_distinct_alternate() -> None:
    with pytest.raises(ValidationError, match="duration_seconds"):
        MediaPlan(preferred_format="video", alternate_format="image_set")
    with pytest.raises(ValidationError, match="alternate_format"):
        MediaPlan(preferred_format="image_set", alternate_format="image_set")
