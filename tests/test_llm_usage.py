from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import Brand, LLMCallLog
from smart_growth_agent.services.llm_config import LLMConfigService


@pytest.mark.asyncio
async def test_usage_report_counts_tokens_failures_period_and_brand_isolation(
    session_factory,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        brand = Brand(name="Usage Brand", slug="usage-brand")
        other_brand = Brand(name="Other Brand", slug="other-brand")
        session.add_all([brand, other_brand])
        await session.flush()
        session.add_all(
            [
                LLMCallLog(
                    brand_id=brand.id,
                    provider="Primary",
                    model="model-a",
                    purpose="xhs_writer",
                    input_tokens=10,
                    output_tokens=4,
                    latency_ms=100,
                    created_at=now - timedelta(days=1),
                ),
                LLMCallLog(
                    brand_id=brand.id,
                    provider="Primary",
                    model="model-a",
                    purpose="xhs_writer",
                    input_tokens=None,
                    output_tokens=None,
                    latency_ms=300,
                    error={"message": "timeout"},
                    created_at=now - timedelta(days=2),
                ),
                LLMCallLog(
                    brand_id=brand.id,
                    provider="Archive",
                    model="model-old",
                    purpose="product_registry_import",
                    input_tokens=30,
                    output_tokens=20,
                    latency_ms=500,
                    created_at=now - timedelta(days=40),
                ),
                LLMCallLog(
                    brand_id=other_brand.id,
                    provider="Other",
                    model="other-model",
                    purpose="xhs_writer",
                    input_tokens=999,
                    output_tokens=999,
                    latency_ms=10,
                    created_at=now,
                ),
            ]
        )
        brand_id = brand.id

    async with session_factory() as session:
        service = LLMConfigService(session, Settings())
        recent = await service.get_usage_report(brand_id=brand_id, days=30)
        assert recent.totals.calls == 2
        assert recent.totals.successful_calls == 1
        assert recent.totals.failed_calls == 1
        assert recent.totals.input_tokens == 10
        assert recent.totals.output_tokens == 4
        assert recent.totals.total_tokens == 14
        assert recent.totals.unreported_token_calls == 1
        assert recent.totals.average_latency_ms == 200
        assert len(recent.by_provider) == 1
        assert recent.by_purpose[0].purpose == "xhs_writer"

        all_time = await service.get_usage_report(brand_id=brand_id, days=None)
        assert all_time.totals.calls == 3
        assert all_time.totals.total_tokens == 64
        assert {row.provider for row in all_time.by_provider} == {"Primary", "Archive"}
