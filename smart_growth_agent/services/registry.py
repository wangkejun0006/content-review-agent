from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import (
    CampaignBrief,
    EvidenceDocument,
    FeedbackRunRegistrySnapshot,
    RegistryItem,
    RegistryLink,
    RegistryRevision,
    RevisionEvidenceLink,
    RunRegistrySnapshot,
)
from smart_growth_agent.domain.enums import RegistryType, RevisionStatus
from smart_growth_agent.domain.errors import ConflictError, NotFoundError, ValidationError
from smart_growth_agent.repositories.registry import RegistryRepository
from smart_growth_agent.schemas.registry import (
    EvidenceDocumentCreate,
    RegistryItemCreate,
    RegistryRevisionCreate,
    RegistryRevisionUpdate,
    validate_registry_payload,
)
from smart_growth_agent.services.audit import record_audit


def payload_checksum(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class RegistryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RegistryRepository(session)

    async def create_item(
        self,
        *,
        brand_id: uuid.UUID,
        registry_type: RegistryType,
        data: RegistryItemCreate,
        actor_id: uuid.UUID,
    ) -> tuple[RegistryItem, RegistryRevision]:
        payload = validate_registry_payload(registry_type, data.payload)
        try:
            async with self.session.begin():
                item = RegistryItem(
                    brand_id=brand_id,
                    registry_type=registry_type,
                    stable_key=data.stable_key,
                )
                self.session.add(item)
                await self.session.flush()
                revision = RegistryRevision(
                    item_id=item.id,
                    version=1,
                    status=RevisionStatus.DRAFT,
                    verification_status=data.verification_status,
                    payload=payload,
                    search_text=data.search_text,
                    source_uri=data.source_uri,
                    checksum=payload_checksum(payload),
                    created_by=actor_id,
                )
                self.session.add(revision)
                await self.session.flush()
                await self._sync_revision_links(item, revision)
                record_audit(
                    self.session,
                    brand_id=brand_id,
                    actor_id=actor_id,
                    action="registry.item_created",
                    resource_type=registry_type.value,
                    resource_id=item.id,
                    details={"revision_id": str(revision.id), "version": 1},
                )
            return item, revision
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            sqlite_unique = (
                "registry_items.brand_id, registry_items.registry_type, registry_items.stable_key"
            ) in str(exc.orig)
            if constraint_name == "uq_registry_items_brand_id" or sqlite_unique:
                raise ConflictError("stable_key already exists for this registry type") from exc
            raise

    async def create_revision(
        self,
        *,
        brand_id: uuid.UUID,
        item_id: uuid.UUID,
        data: RegistryRevisionCreate,
        actor_id: uuid.UUID,
        expected_type: RegistryType | None = None,
    ) -> RegistryRevision:
        async with self.session.begin():
            item = await self.repository.get_item(brand_id, item_id, for_update=True)
            if item is None:
                raise NotFoundError("registry item not found")
            if expected_type is not None and item.registry_type != expected_type:
                raise NotFoundError("registry item not found")
            payload = validate_registry_payload(item.registry_type, data.payload)
            max_version = await self.session.scalar(
                select(func.max(RegistryRevision.version)).where(
                    RegistryRevision.item_id == item.id
                )
            )
            revision = RegistryRevision(
                item_id=item.id,
                version=(max_version or 0) + 1,
                status=RevisionStatus.DRAFT,
                verification_status=data.verification_status,
                payload=payload,
                search_text=data.search_text,
                source_uri=data.source_uri,
                checksum=payload_checksum(payload),
                created_by=actor_id,
            )
            self.session.add(revision)
            await self.session.flush()
            await self._sync_revision_links(item, revision)
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="registry.revision_created",
                resource_type=item.registry_type.value,
                resource_id=item.id,
                details={"revision_id": str(revision.id), "version": revision.version},
            )
        return revision

    async def update_revision(
        self,
        *,
        brand_id: uuid.UUID,
        revision_id: uuid.UUID,
        data: RegistryRevisionUpdate,
        actor_id: uuid.UUID,
        expected_type: RegistryType | None = None,
    ) -> RegistryRevision:
        async with self.session.begin():
            revision = await self.repository.get_revision(brand_id, revision_id, for_update=True)
            if revision is None:
                raise NotFoundError("registry revision not found")
            if revision.status != RevisionStatus.DRAFT:
                raise ConflictError("only draft revisions can be edited")
            item = await self.repository.get_item(brand_id, revision.item_id)
            assert item is not None
            if expected_type is not None and item.registry_type != expected_type:
                raise NotFoundError("registry revision not found")
            if data.payload is not None:
                revision.payload = validate_registry_payload(item.registry_type, data.payload)
                revision.checksum = payload_checksum(revision.payload)
            if data.search_text is not None:
                revision.search_text = data.search_text
            if data.source_uri is not None:
                revision.source_uri = data.source_uri
            if data.verification_status is not None:
                revision.verification_status = data.verification_status
            await self.session.flush()
            await self._sync_revision_links(item, revision)
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="registry.revision_updated",
                resource_type=item.registry_type.value,
                resource_id=item.id,
                details={"revision_id": str(revision.id)},
            )
            await self.session.flush()
            await self.session.refresh(revision)
        return revision

    async def activate_revision(
        self,
        *,
        brand_id: uuid.UUID,
        revision_id: uuid.UUID,
        actor_id: uuid.UUID,
        expected_type: RegistryType | None = None,
    ) -> RegistryRevision:
        async with self.session.begin():
            revision = await self.repository.get_revision(brand_id, revision_id, for_update=True)
            if revision is None:
                raise NotFoundError("registry revision not found")
            if revision.status != RevisionStatus.DRAFT:
                raise ConflictError("only draft revisions can be activated")
            item = await self.repository.get_item(brand_id, revision.item_id, for_update=True)
            assert item is not None
            if expected_type is not None and item.registry_type != expected_type:
                raise NotFoundError("registry revision not found")
            await self._validate_activation(item, revision)
            if item.current_revision_id is not None:
                current = await self.repository.get_revision(
                    brand_id, item.current_revision_id, for_update=True
                )
                if current is not None:
                    current.status = RevisionStatus.RETIRED
                    # The partial unique index is non-deferrable; retire first.
                    await self.session.flush()
            revision.status = RevisionStatus.ACTIVE
            revision.activated_by = actor_id
            revision.activated_at = datetime.now(UTC)
            item.current_revision_id = revision.id
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="registry.revision_activated",
                resource_type=item.registry_type.value,
                resource_id=item.id,
                details={"revision_id": str(revision.id), "version": revision.version},
            )
            await self.session.flush()
            await self.session.refresh(revision)
        return revision

    async def retire_revision(
        self,
        *,
        brand_id: uuid.UUID,
        revision_id: uuid.UUID,
        actor_id: uuid.UUID,
        expected_type: RegistryType | None = None,
    ) -> RegistryRevision:
        async with self.session.begin():
            revision = await self.repository.get_revision(brand_id, revision_id, for_update=True)
            if revision is None:
                raise NotFoundError("registry revision not found")
            if revision.status != RevisionStatus.ACTIVE:
                raise ConflictError("only active revisions can be retired")
            item = await self.repository.get_item(brand_id, revision.item_id, for_update=True)
            assert item is not None
            if expected_type is not None and item.registry_type != expected_type:
                raise NotFoundError("registry revision not found")
            revision.status = RevisionStatus.RETIRED
            item.current_revision_id = None
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="registry.revision_retired",
                resource_type=item.registry_type.value,
                resource_id=item.id,
                details={"revision_id": str(revision.id)},
            )
            await self.session.flush()
            await self.session.refresh(revision)
        return revision

    async def get_item_detail(
        self, brand_id: uuid.UUID, item_id: uuid.UUID
    ) -> tuple[RegistryItem, list[RegistryRevision]]:
        item = await self.repository.get_item(brand_id, item_id)
        if item is None:
            raise NotFoundError("registry item not found")
        return item, await self.repository.list_revisions(brand_id, item_id)

    async def set_item_archived(
        self,
        *,
        brand_id: uuid.UUID,
        item_id: uuid.UUID,
        archived: bool,
        actor_id: uuid.UUID,
        expected_type: RegistryType | None = None,
    ) -> RegistryItem:
        async with self.session.begin():
            item = await self.repository.get_item(brand_id, item_id, for_update=True)
            if item is None or (expected_type is not None and item.registry_type != expected_type):
                raise NotFoundError("registry item not found")
            item.archived_at = datetime.now(UTC) if archived else None
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="registry.item_archived" if archived else "registry.item_restored",
                resource_type=item.registry_type.value,
                resource_id=item.id,
            )
            await self.session.flush()
            await self.session.refresh(item)
        return item

    async def permanently_delete_item(
        self,
        *,
        brand_id: uuid.UUID,
        item_id: uuid.UUID,
        actor_id: uuid.UUID,
        expected_type: RegistryType | None = None,
    ) -> None:
        async with self.session.begin():
            item = await self.repository.get_item(brand_id, item_id, for_update=True)
            if item is None or (expected_type is not None and item.registry_type != expected_type):
                raise NotFoundError("registry item not found")
            if item.archived_at is None:
                raise ConflictError("registry item must be in the recycle bin before deletion")
            referenced = any(
                [
                    await self.session.scalar(
                        select(func.count(RunRegistrySnapshot.id)).where(
                            RunRegistrySnapshot.item_id == item.id
                        )
                    ),
                    await self.session.scalar(
                        select(func.count(FeedbackRunRegistrySnapshot.id)).where(
                            FeedbackRunRegistrySnapshot.item_id == item.id
                        )
                    ),
                    await self.session.scalar(
                        select(func.count(RegistryLink.id)).where(
                            RegistryLink.target_item_id == item.id
                        )
                    ),
                ]
            )
            if not referenced:
                brief_references = list(
                    await self.session.execute(
                        select(
                            CampaignBrief.product_item_ids,
                            CampaignBrief.audience_item_ids,
                        ).where(CampaignBrief.brand_id == brand_id)
                    )
                )
                item_id_text = str(item.id)
                referenced = any(
                    item_id_text in product_ids or item_id_text in audience_ids
                    for product_ids, audience_ids in brief_references
                )
            if referenced:
                raise ConflictError(
                    "registry item is referenced by historical assets "
                    "and cannot be permanently deleted"
                )
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="registry.item_permanently_deleted",
                resource_type=item.registry_type.value,
                resource_id=item.id,
                details={"stable_key": item.stable_key},
            )
            await self.session.delete(item)

    async def create_evidence(
        self, *, brand_id: uuid.UUID, data: EvidenceDocumentCreate, actor_id: uuid.UUID
    ) -> EvidenceDocument:
        checksum = hashlib.sha256(data.content.encode()).hexdigest()
        async with self.session.begin():
            document = EvidenceDocument(
                brand_id=brand_id,
                title=data.title,
                document_type=data.document_type,
                source_uri=data.source_uri,
                content=data.content,
                checksum=checksum,
            )
            self.session.add(document)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="evidence.created",
                resource_type="evidence_document",
                resource_id=document.id,
                details={"verified": False},
            )
        return document

    async def verify_evidence(
        self, *, brand_id: uuid.UUID, document_id: uuid.UUID, actor_id: uuid.UUID
    ) -> EvidenceDocument:
        async with self.session.begin():
            document = await self.session.scalar(
                select(EvidenceDocument)
                .where(
                    EvidenceDocument.id == document_id,
                    EvidenceDocument.brand_id == brand_id,
                    EvidenceDocument.is_active.is_(True),
                )
                .with_for_update()
            )
            if document is None:
                raise NotFoundError("evidence document not found")
            document.verified_by = actor_id
            document.verified_at = datetime.now(UTC)
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="evidence.verified",
                resource_type="evidence_document",
                resource_id=document.id,
            )
            await self.session.flush()
            await self.session.refresh(document)
        return document

    async def _validate_activation(self, item: RegistryItem, revision: RegistryRevision) -> None:
        if item.registry_type != RegistryType.PRODUCT_CLAIM:
            return
        product_ids = [uuid.UUID(value) for value in revision.payload["product_item_ids"]]
        evidence_ids = [uuid.UUID(value) for value in revision.payload["evidence_document_ids"]]
        products = list(
            await self.session.scalars(
                select(RegistryItem).where(
                    RegistryItem.brand_id == item.brand_id,
                    RegistryItem.id.in_(product_ids),
                    RegistryItem.registry_type == RegistryType.PRODUCT,
                    RegistryItem.current_revision_id.is_not(None),
                    RegistryItem.archived_at.is_(None),
                )
            )
        )
        if len(products) != len(set(product_ids)):
            raise ValidationError("all claim products must be active products in the same brand")
        evidence = list(
            await self.session.scalars(
                select(EvidenceDocument).where(
                    EvidenceDocument.brand_id == item.brand_id,
                    EvidenceDocument.id.in_(evidence_ids),
                    EvidenceDocument.is_active.is_(True),
                    EvidenceDocument.verified_at.is_not(None),
                )
            )
        )
        if len(evidence) != len(set(evidence_ids)):
            raise ValidationError("all claim evidence must be active and verified")

    async def _sync_revision_links(self, item: RegistryItem, revision: RegistryRevision) -> None:
        await self.session.execute(
            delete(RegistryLink).where(RegistryLink.source_revision_id == revision.id)
        )
        await self.session.execute(
            delete(RevisionEvidenceLink).where(RevisionEvidenceLink.revision_id == revision.id)
        )
        if item.registry_type != RegistryType.PRODUCT_CLAIM:
            return
        for product_id in revision.payload["product_item_ids"]:
            self.session.add(
                RegistryLink(
                    brand_id=item.brand_id,
                    source_revision_id=revision.id,
                    relation_type="claim_applies_to_product",
                    target_item_id=uuid.UUID(product_id),
                )
            )
        for evidence_id in revision.payload["evidence_document_ids"]:
            self.session.add(
                RevisionEvidenceLink(
                    brand_id=item.brand_id,
                    revision_id=revision.id,
                    evidence_document_id=uuid.UUID(evidence_id),
                )
            )
