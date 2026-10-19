from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import (
    AttributionEvidence,
    CommerceSnapshot,
    ContentCandidate,
    ContentVersion,
    GrowthRun,
    MetricSnapshot,
    Publication,
)
from smart_growth_agent.domain.enums import RunStatus
from smart_growth_agent.domain.errors import ConflictError, NotFoundError, ValidationError
from smart_growth_agent.schemas.analytics import (
    AttributionEvidenceCreate,
    CommerceSnapshotCreate,
    MetricSnapshotCreate,
    PublicationCreate,
)
from smart_growth_agent.services.audit import record_audit

METRIC_NAMES = (
    "impressions",
    "views",
    "likes",
    "collections",
    "comments",
    "shares",
    "follows",
    "profile_visits",
    "outbound_clicks",
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_publication(
        self,
        *,
        brand_id: uuid.UUID,
        data: PublicationCreate,
        actor_id: uuid.UUID,
    ) -> Publication:
        try:
            async with self.session.begin():
                row = (
                    await self.session.execute(
                        select(ContentVersion, ContentCandidate, GrowthRun)
                        .join(ContentCandidate, ContentCandidate.id == ContentVersion.candidate_id)
                        .join(GrowthRun, GrowthRun.id == ContentCandidate.run_id)
                        .where(
                            ContentVersion.id == data.content_version_id,
                            ContentVersion.brand_id == brand_id,
                            ContentCandidate.brand_id == brand_id,
                            GrowthRun.brand_id == brand_id,
                        )
                    )
                ).one_or_none()
                if row is None:
                    raise NotFoundError("content version not found")
                version, candidate, run = row
                if run.status != RunStatus.READY_FOR_MANUAL_PUBLISH:
                    raise ValidationError("growth run is not ready for manual publishing")
                if run.selected_candidate_id != candidate.id:
                    raise ValidationError("publication must use the human-selected candidate")
                if candidate.current_version != version.version:
                    raise ValidationError(
                        "publication must use the selected candidate current version"
                    )

                publication = Publication(
                    brand_id=brand_id,
                    content_version_id=version.id,
                    platform=data.platform,
                    platform_content_id=data.platform_content_id,
                    url=str(data.url),
                    published_at=data.published_at,
                )
                self.session.add(publication)
                await self.session.flush()
                record_audit(
                    self.session,
                    brand_id=brand_id,
                    actor_id=actor_id,
                    action="publication.created",
                    resource_type="publication",
                    resource_id=publication.id,
                    details={"content_version_id": str(version.id)},
                )
                return publication
        except IntegrityError as exc:
            raise ConflictError("publication already exists") from exc

    async def create_metric_snapshot(
        self,
        *,
        brand_id: uuid.UUID,
        publication_id: uuid.UUID,
        data: MetricSnapshotCreate,
        actor_id: uuid.UUID,
    ) -> MetricSnapshot:
        try:
            async with self.session.begin():
                publication = await self.session.scalar(
                    select(Publication).where(
                        Publication.id == publication_id,
                        Publication.brand_id == brand_id,
                    )
                )
                if publication is None:
                    raise NotFoundError("publication not found")
                if _as_utc(data.captured_at) < _as_utc(publication.published_at):
                    raise ValidationError("metric capture cannot predate publication")

                if data.is_correction:
                    corrected = await self.session.scalar(
                        select(MetricSnapshot).where(
                            MetricSnapshot.id == data.corrects_snapshot_id,
                            MetricSnapshot.publication_id == publication_id,
                            MetricSnapshot.brand_id == brand_id,
                        )
                    )
                    if corrected is None:
                        raise ValidationError("corrected snapshot does not belong to publication")
                else:
                    await self._validate_cumulative_metrics(
                        brand_id=brand_id,
                        publication_id=publication_id,
                        data=data,
                    )

                snapshot = MetricSnapshot(
                    brand_id=brand_id,
                    publication_id=publication_id,
                    **data.model_dump(),
                )
                self.session.add(snapshot)
                await self.session.flush()
                record_audit(
                    self.session,
                    brand_id=brand_id,
                    actor_id=actor_id,
                    action=(
                        "metric_snapshot.corrected"
                        if data.is_correction
                        else "metric_snapshot.created"
                    ),
                    resource_type="metric_snapshot",
                    resource_id=snapshot.id,
                    details={
                        "publication_id": str(publication_id),
                        "corrects_snapshot_id": (
                            str(data.corrects_snapshot_id)
                            if data.corrects_snapshot_id is not None
                            else None
                        ),
                    },
                )
                return snapshot
        except IntegrityError as exc:
            raise ConflictError("a snapshot already exists at this capture time") from exc

    async def _validate_cumulative_metrics(
        self,
        *,
        brand_id: uuid.UUID,
        publication_id: uuid.UUID,
        data: MetricSnapshotCreate,
    ) -> None:
        previous = await self.session.scalar(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.brand_id == brand_id,
                MetricSnapshot.publication_id == publication_id,
                MetricSnapshot.captured_at < data.captured_at,
            )
            .order_by(MetricSnapshot.captured_at.desc())
            .limit(1)
        )
        following = await self.session.scalar(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.brand_id == brand_id,
                MetricSnapshot.publication_id == publication_id,
                MetricSnapshot.captured_at > data.captured_at,
            )
            .order_by(MetricSnapshot.captured_at)
            .limit(1)
        )
        for name in METRIC_NAMES:
            value = getattr(data, name)
            if value is None:
                continue
            previous_value = getattr(previous, name, None)
            following_value = getattr(following, name, None)
            if previous_value is not None and value < previous_value:
                raise ValidationError(
                    f"cumulative metric {name} cannot decrease; submit a correction instead"
                )
            if following_value is not None and value > following_value:
                raise ValidationError(
                    f"cumulative metric {name} cannot exceed a later snapshot"
                )

    async def create_commerce_snapshot(
        self,
        *,
        brand_id: uuid.UUID,
        data: CommerceSnapshotCreate,
        actor_id: uuid.UUID,
    ) -> CommerceSnapshot:
        try:
            async with self.session.begin():
                snapshot = CommerceSnapshot(brand_id=brand_id, **data.model_dump())
                self.session.add(snapshot)
                await self.session.flush()
                record_audit(
                    self.session,
                    brand_id=brand_id,
                    actor_id=actor_id,
                    action="commerce_snapshot.created",
                    resource_type="commerce_snapshot",
                    resource_id=snapshot.id,
                    details={"scope_type": data.scope_type, "scope_key": data.scope_key},
                )
                return snapshot
        except IntegrityError as exc:
            raise ConflictError("commerce snapshot already exists") from exc

    async def create_attribution_evidence(
        self,
        *,
        brand_id: uuid.UUID,
        data: AttributionEvidenceCreate,
        actor_id: uuid.UUID,
    ) -> AttributionEvidence:
        try:
            async with self.session.begin():
                publication = await self.session.scalar(
                    select(Publication.id).where(
                        Publication.id == data.publication_id,
                        Publication.brand_id == brand_id,
                    )
                )
                commerce = await self.session.scalar(
                    select(CommerceSnapshot.id).where(
                        CommerceSnapshot.id == data.commerce_snapshot_id,
                        CommerceSnapshot.brand_id == brand_id,
                    )
                )
                if publication is None or commerce is None:
                    raise ValidationError(
                        "publication and commerce snapshot must belong to the current brand"
                    )
                evidence = AttributionEvidence(brand_id=brand_id, **data.model_dump())
                self.session.add(evidence)
                await self.session.flush()
                record_audit(
                    self.session,
                    brand_id=brand_id,
                    actor_id=actor_id,
                    action="attribution_evidence.created",
                    resource_type="attribution_evidence",
                    resource_id=evidence.id,
                    details={"strength": data.strength.value},
                )
                return evidence
        except IntegrityError as exc:
            raise ConflictError("attribution evidence already exists") from exc
