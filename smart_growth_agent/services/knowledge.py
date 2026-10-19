from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import (
    KnowledgeSource,
    RegistryItem,
    RegistryRevision,
    RegistryVerification,
    RunRegistrySnapshot,
    SourceCapture,
)
from smart_growth_agent.domain.enums import (
    KnowledgeCriticality,
    RegistryType,
    VerificationResult,
)
from smart_growth_agent.domain.errors import ConflictError, NotFoundError, ValidationError
from smart_growth_agent.schemas.knowledge import (
    FreshnessIssue,
    KnowledgeSourceCreate,
    RegistryVerificationCreate,
    SourceCaptureCreate,
)
from smart_growth_agent.services.audit import record_audit

SUCCESSFUL_VERIFICATIONS = {
    VerificationResult.UNCHANGED,
    VerificationResult.MANUALLY_VERIFIED,
}


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_source(
        self, *, brand_id: uuid.UUID, data: KnowledgeSourceCreate, actor_id: uuid.UUID
    ) -> KnowledgeSource:
        async with self.session.begin():
            existing = await self.session.scalar(
                select(KnowledgeSource).where(
                    KnowledgeSource.brand_id == brand_id,
                    KnowledgeSource.canonical_url == str(data.canonical_url),
                )
            )
            if existing is not None:
                raise ConflictError("knowledge source URL already exists")
            source = KnowledgeSource(
                brand_id=brand_id,
                name=data.name,
                source_type=data.source_type,
                platform=data.platform,
                canonical_url=str(data.canonical_url),
                retrieval_method=data.retrieval_method,
                freshness_days=data.freshness_days,
                criticality=data.criticality,
            )
            self.session.add(source)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="knowledge.source_created",
                resource_type="knowledge_source",
                resource_id=source.id,
            )
        return source

    async def create_capture(
        self,
        *,
        brand_id: uuid.UUID,
        source_id: uuid.UUID,
        data: SourceCaptureCreate,
        actor_id: uuid.UUID,
    ) -> SourceCapture:
        checksum = hashlib.sha256(data.content.encode()).hexdigest()
        async with self.session.begin():
            source = await self.session.scalar(
                select(KnowledgeSource).where(
                    KnowledgeSource.id == source_id,
                    KnowledgeSource.brand_id == brand_id,
                    KnowledgeSource.enabled.is_(True),
                )
            )
            if source is None:
                raise NotFoundError("knowledge source not found")
            existing = await self.session.scalar(
                select(SourceCapture).where(
                    SourceCapture.source_id == source_id,
                    SourceCapture.checksum == checksum,
                )
            )
            if existing is not None:
                return existing
            capture = SourceCapture(
                brand_id=brand_id,
                source_id=source_id,
                captured_at=data.captured_at or datetime.now(UTC),
                content=data.content,
                checksum=checksum,
                metadata_json=data.metadata,
            )
            self.session.add(capture)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="knowledge.source_captured",
                resource_type="source_capture",
                resource_id=capture.id,
                details={"source_id": str(source_id)},
            )
        return capture

    async def verify_revision(
        self,
        *,
        brand_id: uuid.UUID,
        revision_id: uuid.UUID,
        data: RegistryVerificationCreate,
        actor_id: uuid.UUID,
    ) -> RegistryVerification:
        async with self.session.begin():
            revision = await self.session.scalar(
                select(RegistryRevision)
                .join(RegistryItem, RegistryItem.id == RegistryRevision.item_id)
                .where(
                    RegistryRevision.id == revision_id,
                    RegistryItem.brand_id == brand_id,
                )
            )
            if revision is None:
                raise NotFoundError("registry revision not found")
            if data.source_id is not None:
                source = await self.session.scalar(
                    select(KnowledgeSource).where(
                        KnowledgeSource.id == data.source_id,
                        KnowledgeSource.brand_id == brand_id,
                    )
                )
                if source is None:
                    raise NotFoundError("knowledge source not found")
            if data.source_capture_id is not None:
                capture = await self.session.scalar(
                    select(SourceCapture).where(
                        SourceCapture.id == data.source_capture_id,
                        SourceCapture.brand_id == brand_id,
                    )
                )
                if capture is None:
                    raise NotFoundError("source capture not found")
                if data.source_id is not None and capture.source_id != data.source_id:
                    raise ValidationError("source capture does not belong to source")
            verification = RegistryVerification(
                brand_id=brand_id,
                revision_id=revision_id,
                source_id=data.source_id,
                source_capture_id=data.source_capture_id,
                checked_at=data.checked_at or datetime.now(UTC),
                result=data.result,
                checked_by=actor_id,
                notes=data.notes,
            )
            self.session.add(verification)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="registry.revision_verified",
                resource_type="registry_revision",
                resource_id=revision_id,
                details={"result": data.result.value},
            )
        return verification

    async def evaluate_run_freshness(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID, now: datetime | None = None
    ) -> list[FreshnessIssue]:
        now = now or datetime.now(UTC)
        rows = list(
            (
                await self.session.execute(
                    select(RegistryItem, RegistryRevision)
                    .join(RegistryRevision, RegistryRevision.item_id == RegistryItem.id)
                    .join(
                        RunRegistrySnapshot,
                        RunRegistrySnapshot.revision_id == RegistryRevision.id,
                    )
                    .where(
                        RunRegistrySnapshot.run_id == run_id,
                        RunRegistrySnapshot.brand_id == brand_id,
                        RegistryItem.registry_type == RegistryType.PLATFORM_RULE,
                    )
                )
            ).all()
        )
        issues: list[FreshnessIssue] = []
        for item, revision in rows:
            source_url = revision.source_uri or revision.payload.get("source_url")
            source = None
            if source_url:
                source = await self.session.scalar(
                    select(KnowledgeSource).where(
                        KnowledgeSource.brand_id == brand_id,
                        KnowledgeSource.canonical_url == str(source_url),
                        KnowledgeSource.enabled.is_(True),
                    )
                )
            freshness_days = source.freshness_days if source is not None else 90
            last_verified_at = await self.session.scalar(
                select(func.max(RegistryVerification.checked_at)).where(
                    RegistryVerification.brand_id == brand_id,
                    RegistryVerification.revision_id == revision.id,
                    RegistryVerification.result.in_(SUCCESSFUL_VERIFICATIONS),
                )
            )
            latest_verification = await self.session.scalar(
                select(RegistryVerification)
                .where(
                    RegistryVerification.brand_id == brand_id,
                    RegistryVerification.revision_id == revision.id,
                )
                .order_by(RegistryVerification.checked_at.desc())
                .limit(1)
            )
            if last_verified_at is None and revision.payload.get("verified_at"):
                last_verified_at = datetime.fromisoformat(revision.payload["verified_at"])
            if last_verified_at is not None and last_verified_at.tzinfo is None:
                last_verified_at = last_verified_at.replace(tzinfo=UTC)
            change_detected = (
                latest_verification is not None
                and latest_verification.result == VerificationResult.CHANGED
            )
            stale = (
                change_detected
                or last_verified_at is None
                or now - last_verified_at > timedelta(days=freshness_days)
            )
            critical = revision.payload.get("severity") == "blocker" or (
                source is not None and source.criticality == KnowledgeCriticality.CRITICAL
            )
            if stale:
                issues.append(
                    FreshnessIssue(
                        revision_id=revision.id,
                        stable_key=item.stable_key,
                        source_id=source.id if source is not None else None,
                        critical=critical,
                        stale=True,
                        change_detected=change_detected,
                        last_verified_at=last_verified_at,
                        freshness_days=freshness_days,
                        message=(
                            "platform rule source changed and requires review"
                            if change_detected
                            else "platform rule verification is stale or missing"
                        ),
                    )
                )
        return issues
