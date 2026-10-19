from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from smart_growth_agent.db.models import CommerceSnapshot, ImportBatch, MetricSnapshot
from smart_growth_agent.schemas.analytics import PublicationCreate
from smart_growth_agent.services.analytics import AnalyticsService
from smart_growth_agent.services.imports import ImportService
from tests.test_analytics import _seed_selected_content


@pytest.mark.asyncio
async def test_csv_import_is_partial_and_idempotent(session_factory) -> None:
    brand_id, actor_id, version_id = await _seed_selected_content(session_factory)
    published_at = datetime.now(UTC) - timedelta(days=2)
    async with session_factory() as session:
        publication = await AnalyticsService(session).create_publication(
            brand_id=brand_id,
            actor_id=actor_id,
            data=PublicationCreate(
                content_version_id=version_id,
                platform_content_id="csv-note",
                url="https://www.xiaohongshu.com/explore/csv-note",
                published_at=published_at,
            ),
        )
        publication_id = publication.id

    capture_one = (published_at + timedelta(days=1)).isoformat()
    capture_two = (published_at + timedelta(days=1, hours=1)).isoformat()
    content = (
        "publication_id,captured_at,views,likes,is_correction,"
        "correction_reason,corrects_snapshot_id\n"
        f"{publication_id},{capture_one},100,10,false,,\n"
        f"{publication_id},{capture_two},90,11,false,,\n"
    )
    service = ImportService(session_factory)
    first = await service.import_xhs(
        brand_id=brand_id,
        actor_id=actor_id,
        idempotency_key="xhs-import-test",
        content=content,
    )
    replay = await service.import_xhs(
        brand_id=brand_id,
        actor_id=actor_id,
        idempotency_key="xhs-import-test",
        content=content,
    )
    assert (first.succeeded_rows, first.failed_rows) == (1, 1)
    assert replay == first

    jd_content = (
        "captured_at,scope_type,scope_key,product_views,paid_orders,gmv\n"
        f"{datetime.now(UTC).isoformat()},campaign,summer,30,2,699.00\n"
        f"{datetime.now(UTC).isoformat()},sku,broken,-1,1,99.00\n"
    )
    jd = await service.import_jd(
        brand_id=brand_id,
        actor_id=actor_id,
        idempotency_key="jd-import-test",
        content=jd_content,
    )
    assert (jd.succeeded_rows, jd.failed_rows) == (1, 1)

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(MetricSnapshot)) == 1
        assert await session.scalar(select(func.count()).select_from(CommerceSnapshot)) == 1
        assert await session.scalar(select(func.count()).select_from(ImportBatch)) == 2
