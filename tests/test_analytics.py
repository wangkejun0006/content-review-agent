from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import (
    AttributionEvidence,
    Brand,
    CampaignBrief,
    ContentCandidate,
    ContentVersion,
    GrowthRun,
    MetricSnapshot,
)
from smart_growth_agent.domain.enums import (
    AttributionStrength,
    RunStatus,
)
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.schemas.analytics import (
    AttributionEvidenceCreate,
    CommerceSnapshotCreate,
    MetricSnapshotCreate,
    PublicationCreate,
)
from smart_growth_agent.services.analytics import AnalyticsService


async def _seed_selected_content(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    brand_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        session.add(Brand(id=brand_id, name="Test Brand", slug=f"test-{brand_id.hex}"))
        brief = CampaignBrief(
            brand_id=brand_id,
            name="Phase 5 test",
            objective="test analytics",
            product_item_ids=[],
            audience_item_ids=[],
            constraints={},
            created_by=actor_id,
        )
        session.add(brief)
        await session.flush()
        run = GrowthRun(
            brand_id=brand_id,
            brief_id=brief.id,
            thread_id=str(uuid.uuid4()),
            status=RunStatus.READY_FOR_MANUAL_PUBLISH,
            gate_status="approved",
            created_by=actor_id,
        )
        session.add(run)
        await session.flush()
        candidate = ContentCandidate(
            brand_id=brand_id,
            run_id=run.id,
            route_key="selected",
            angle_key="test",
            current_version=1,
        )
        session.add(candidate)
        await session.flush()
        version = ContentVersion(
            brand_id=brand_id,
            candidate_id=candidate.id,
            version=1,
            payload={"title": "test"},
            prompt_revision_id=uuid.uuid4(),
            input_checksum="a" * 64,
            generation_key=uuid.uuid4().hex,
        )
        session.add(version)
        run.selected_candidate_id = candidate.id
        await session.flush()
        return brand_id, actor_id, version.id


@pytest.mark.asyncio
async def test_publication_and_metric_correction_are_governed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    brand_id, actor_id, version_id = await _seed_selected_content(session_factory)
    published_at = datetime.now(UTC) - timedelta(days=2)
    async with session_factory() as session:
        publication = await AnalyticsService(session).create_publication(
            brand_id=brand_id,
            actor_id=actor_id,
            data=PublicationCreate(
                content_version_id=version_id,
                platform_content_id="xhs-note-1",
                url="https://www.xiaohongshu.com/explore/test",
                published_at=published_at,
            ),
        )
        first = await AnalyticsService(session).create_metric_snapshot(
            brand_id=brand_id,
            publication_id=publication.id,
            actor_id=actor_id,
            data=MetricSnapshotCreate(
                captured_at=published_at + timedelta(days=1),
                views=100,
                likes=20,
            ),
        )
        publication_id = publication.id
        first_snapshot_id = first.id

        with pytest.raises(ValidationError, match="cannot decrease"):
            await AnalyticsService(session).create_metric_snapshot(
                brand_id=brand_id,
                publication_id=publication_id,
                actor_id=actor_id,
                data=MetricSnapshotCreate(
                    captured_at=published_at + timedelta(days=1, hours=1),
                    views=90,
                ),
            )

        correction = await AnalyticsService(session).create_metric_snapshot(
            brand_id=brand_id,
            publication_id=publication_id,
            actor_id=actor_id,
            data=MetricSnapshotCreate(
                captured_at=published_at + timedelta(days=1, hours=2),
                views=90,
                is_correction=True,
                correction_reason="平台后台修正",
                corrects_snapshot_id=first_snapshot_id,
            ),
        )
        assert correction.corrects_snapshot_id == first_snapshot_id

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(MetricSnapshot))
        assert count == 2


@pytest.mark.asyncio
async def test_commerce_attribution_enforces_brand_and_strength(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    brand_id, actor_id, version_id = await _seed_selected_content(session_factory)
    published_at = datetime.now(UTC) - timedelta(days=1)
    async with session_factory() as session:
        service = AnalyticsService(session)
        publication = await service.create_publication(
            brand_id=brand_id,
            actor_id=actor_id,
            data=PublicationCreate(
                content_version_id=version_id,
                platform_content_id="xhs-note-2",
                url="https://www.xiaohongshu.com/explore/test-2",
                published_at=published_at,
            ),
        )
        commerce = await service.create_commerce_snapshot(
            brand_id=brand_id,
            actor_id=actor_id,
            data=CommerceSnapshotCreate(
                captured_at=datetime.now(UTC),
                scope_type="campaign",
                scope_key="phase-5",
                product_views=30,
                paid_orders=2,
            ),
        )
        evidence = await service.create_attribution_evidence(
            brand_id=brand_id,
            actor_id=actor_id,
            data=AttributionEvidenceCreate(
                publication_id=publication.id,
                commerce_snapshot_id=commerce.id,
                evidence_type="dedicated_link",
                strength=AttributionStrength.DIRECT,
                details={"link_key": "phase-5"},
            ),
        )
        assert evidence.strength == AttributionStrength.DIRECT

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(AttributionEvidence))
        assert count == 1

    with pytest.raises(PydanticValidationError, match="direct attribution"):
        AttributionEvidenceCreate(
            publication_id=uuid.uuid4(),
            commerce_snapshot_id=uuid.uuid4(),
            evidence_type="manual_link",
            strength=AttributionStrength.DIRECT,
        )


def test_metric_schema_rejects_empty_snapshot() -> None:
    with pytest.raises(PydanticValidationError, match="at least one metric"):
        MetricSnapshotCreate(captured_at=datetime.now(UTC))
