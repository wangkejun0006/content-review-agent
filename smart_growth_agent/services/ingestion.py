from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import (
    EvidenceDocument,
    IngestionRecord,
    RegistryItem,
    RegistryRevision,
)
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import ConflictError, NotFoundError
from smart_growth_agent.schemas.ingestion import (
    DuplicateMatch,
    IngestionAnalysis,
    IngestionResolve,
)


def normalize_ingestion_text(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.casefold())


def ingestion_checksum(value: str) -> str:
    return hashlib.sha256(value.strip().encode()).hexdigest()


class IngestionDedupService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def preflight(
        self, *, brand_id: uuid.UUID, ingestion_type: str, source_text: str
    ) -> str:
        checksum = ingestion_checksum(source_text)
        async with self.session_factory() as session:
            prior = await session.scalar(
                select(IngestionRecord).where(
                    IngestionRecord.brand_id == brand_id,
                    IngestionRecord.ingestion_type == ingestion_type,
                    IngestionRecord.source_checksum == checksum,
                    IngestionRecord.status != "cancelled",
                )
            )
            if prior is not None:
                raise ConflictError(
                    "相同资料已经做过 AI 整理，本次未调用 LLM；请回到已有草稿处理，"
                    f"导入记录 {prior.id}"
                )
            if ingestion_type == "evidence":
                existing = await session.scalar(
                    select(EvidenceDocument.id).where(
                        EvidenceDocument.brand_id == brand_id,
                        EvidenceDocument.checksum == checksum,
                    )
                )
                if existing is not None:
                    raise ConflictError(
                        "相同证据原文已存在，本次未调用 LLM；"
                        f"Evidence Document {existing}"
                    )
        return checksum

    async def analyze_product(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_text: str,
        source_uri: str | None,
        stable_key: str,
        payload: dict[str, Any],
    ) -> IngestionAnalysis:
        matches: list[DuplicateMatch] = []
        async with self.session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(RegistryRevision, RegistryRevision.item_id == RegistryItem.id)
                        .where(
                            RegistryItem.brand_id == brand_id,
                            RegistryItem.registry_type == RegistryType.PRODUCT,
                        )
                    )
                ).all()
            )
        draft_sku = str(payload.get("sku") or "").strip().casefold()
        draft_name = normalize_ingestion_text(str(payload.get("name") or ""))
        for item, revision in rows:
            existing_sku = str(revision.payload.get("sku") or "").strip().casefold()
            existing_name = normalize_ingestion_text(str(revision.payload.get("name") or ""))
            if draft_sku and existing_sku == draft_sku:
                matches.append(
                    DuplicateMatch(
                        match_type="same_sku",
                        entity_type="product",
                        item_id=item.id,
                        revision_id=revision.id,
                        label=f"{revision.payload.get('name', item.stable_key)} / {draft_sku}",
                        similarity=1,
                        recommended_action="new_revision",
                    )
                )
                continue
            if item.stable_key == stable_key:
                matches.append(
                    DuplicateMatch(
                        match_type="same_stable_key",
                        entity_type="product",
                        item_id=item.id,
                        revision_id=revision.id,
                        label=item.stable_key,
                        similarity=1,
                        recommended_action="new_revision",
                    )
                )
                continue
            similarity = SequenceMatcher(None, draft_name, existing_name).ratio()
            if draft_name and similarity >= 0.86:
                matches.append(
                    DuplicateMatch(
                        match_type="similar_text",
                        entity_type="product",
                        item_id=item.id,
                        revision_id=revision.id,
                        label=str(revision.payload.get("name") or item.stable_key),
                        similarity=round(similarity, 4),
                        recommended_action="review",
                    )
                )
        return await self._persist_analysis(
            brand_id=brand_id,
            actor_id=actor_id,
            ingestion_type="product",
            source_text=source_text,
            source_uri=source_uri,
            matches=matches,
        )

    async def analyze_platform_rule(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_text: str,
        source_uri: str,
        stable_key: str,
        rule_text: str,
    ) -> IngestionAnalysis:
        matches: list[DuplicateMatch] = []
        normalized_rule = normalize_ingestion_text(rule_text)
        async with self.session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(RegistryRevision, RegistryRevision.item_id == RegistryItem.id)
                        .where(
                            RegistryItem.brand_id == brand_id,
                            RegistryItem.registry_type == RegistryType.PLATFORM_RULE,
                        )
                    )
                ).all()
            )
        for item, revision in rows:
            existing_text = normalize_ingestion_text(str(revision.payload.get("rule_text") or ""))
            similarity = SequenceMatcher(None, normalized_rule, existing_text).ratio()
            same_key = item.stable_key == stable_key
            if same_key or (normalized_rule and similarity >= 0.86):
                matches.append(
                    DuplicateMatch(
                        match_type="same_stable_key" if same_key else "similar_text",
                        entity_type="platform_rule",
                        item_id=item.id,
                        revision_id=revision.id,
                        label=item.stable_key,
                        similarity=1 if same_key else round(similarity, 4),
                        recommended_action="new_revision" if same_key else "review",
                    )
                )
        return await self._persist_analysis(
            brand_id=brand_id,
            actor_id=actor_id,
            ingestion_type="platform_rule",
            source_text=source_text,
            source_uri=source_uri,
            matches=matches,
        )

    async def analyze_evidence(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_text: str,
        source_uri: str,
        title: str,
    ) -> IngestionAnalysis:
        matches: list[DuplicateMatch] = []
        normalized_title = normalize_ingestion_text(title)
        async with self.session_factory() as session:
            documents = list(
                await session.scalars(
                    select(EvidenceDocument).where(EvidenceDocument.brand_id == brand_id)
                )
            )
        for document in documents:
            similarity = SequenceMatcher(
                None, normalized_title, normalize_ingestion_text(document.title)
            ).ratio()
            if normalized_title and similarity >= 0.86:
                matches.append(
                    DuplicateMatch(
                        match_type="similar_text",
                        entity_type="evidence",
                        evidence_document_id=document.id,
                        label=document.title,
                        similarity=round(similarity, 4),
                        recommended_action="review",
                    )
                )
        return await self._persist_analysis(
            brand_id=brand_id,
            actor_id=actor_id,
            ingestion_type="evidence",
            source_text=source_text,
            source_uri=source_uri,
            matches=matches,
        )

    async def resolve(
        self,
        *,
        brand_id: uuid.UUID,
        ingestion_id: uuid.UUID,
        data: IngestionResolve,
    ) -> IngestionRecord:
        async with self.session_factory() as session, session.begin():
            record = await session.scalar(
                select(IngestionRecord).where(
                    IngestionRecord.id == ingestion_id,
                    IngestionRecord.brand_id == brand_id,
                )
            )
            if record is None:
                raise NotFoundError("ingestion record not found")
            if record.status != "awaiting_decision":
                raise ConflictError("ingestion record has already been resolved")
            record.decision = data.decision
            record.decision_reason = data.decision_reason.strip() or None
            record.resulting_item_id = data.resulting_item_id
            record.resulting_revision_id = data.resulting_revision_id
            record.resulting_evidence_document_id = data.resulting_evidence_document_id
            record.status = "cancelled" if data.decision == "cancel" else "resolved"
            record.resolved_at = datetime.now(UTC)
            await session.flush()
            await session.refresh(record)
            return record

    async def _persist_analysis(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        ingestion_type: str,
        source_text: str,
        source_uri: str | None,
        matches: list[DuplicateMatch],
    ) -> IngestionAnalysis:
        exact = any(match.similarity == 1 for match in matches)
        duplicate_status = "exact" if exact else "possible" if matches else "none"
        recommended_action = (
            "new_revision"
            if any(match.recommended_action == "new_revision" for match in matches)
            else "review"
            if matches
            else "new_item"
        )
        record = IngestionRecord(
            brand_id=brand_id,
            ingestion_type=ingestion_type,
            source_uri=source_uri,
            source_checksum=ingestion_checksum(source_text),
            normalized_text=normalize_ingestion_text(source_text),
            duplicate_status=duplicate_status,
            matches=[match.model_dump(mode="json") for match in matches],
            recommended_action=recommended_action,
            created_by=actor_id,
        )
        async with self.session_factory() as session, session.begin():
            session.add(record)
            await session.flush()
            record_id = record.id
        message = (
            "未发现重复，可创建新实体"
            if not matches
            else "发现同一 SKU 或 Key，默认创建新 Revision"
            if recommended_action == "new_revision"
            else "发现疑似重复，请人工确认后再保存"
        )
        return IngestionAnalysis(
            ingestion_id=record_id,
            duplicate_status=duplicate_status,
            matches=matches,
            recommended_action=recommended_action,
            message=message,
        )
