from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import ImportBatch
from smart_growth_agent.domain.errors import (
    ConflictError,
    DomainError,
)
from smart_growth_agent.domain.errors import (
    ValidationError as DomainValidationError,
)
from smart_growth_agent.schemas.analytics import CommerceSnapshotCreate, MetricSnapshotCreate
from smart_growth_agent.schemas.imports import ImportBatchResult, ImportRowResult
from smart_growth_agent.services.analytics import AnalyticsService

XHS_INTEGER_FIELDS = (
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
JD_INTEGER_FIELDS = (
    "impressions",
    "product_views",
    "add_to_cart",
    "orders",
    "paid_orders",
)


class ImportService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def import_xhs(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        idempotency_key: str,
        content: str,
    ) -> ImportBatchResult:
        existing = await self._existing(
            brand_id=brand_id,
            idempotency_key=idempotency_key,
            import_type="xhs_metrics",
            content=content,
        )
        if existing is not None:
            return existing
        results: list[ImportRowResult] = []
        for row_number, row in enumerate(self._rows(content), start=2):
            try:
                publication_id = uuid.UUID(self._required(row, "publication_id"))
                payload = {
                    "captured_at": datetime.fromisoformat(
                        self._required(row, "captured_at")
                    ),
                    **self._integers(row, XHS_INTEGER_FIELDS),
                    "is_correction": self._boolean(row.get("is_correction")),
                    "correction_reason": self._optional(row.get("correction_reason")),
                    "corrects_snapshot_id": self._optional_uuid(
                        row.get("corrects_snapshot_id")
                    ),
                }
                async with self.session_factory() as session:
                    snapshot = await AnalyticsService(session).create_metric_snapshot(
                        brand_id=brand_id,
                        publication_id=publication_id,
                        data=MetricSnapshotCreate.model_validate(payload),
                        actor_id=actor_id,
                    )
                results.append(
                    ImportRowResult(
                        row_number=row_number,
                        status="succeeded",
                        resource_id=snapshot.id,
                    )
                )
            except (ValueError, DomainError, PydanticValidationError) as exc:
                results.append(
                    ImportRowResult(
                        row_number=row_number,
                        status="failed",
                        error=str(exc),
                    )
                )
        result = self._result("xhs_metrics", results)
        await self._save(
            brand_id=brand_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            content=content,
            result=result,
        )
        return result

    async def import_jd(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        idempotency_key: str,
        content: str,
    ) -> ImportBatchResult:
        existing = await self._existing(
            brand_id=brand_id,
            idempotency_key=idempotency_key,
            import_type="jd_commerce",
            content=content,
        )
        if existing is not None:
            return existing
        results: list[ImportRowResult] = []
        for row_number, row in enumerate(self._rows(content), start=2):
            try:
                gmv = self._optional(row.get("gmv"))
                payload = CommerceSnapshotCreate(
                    captured_at=datetime.fromisoformat(
                        self._required(row, "captured_at")
                    ),
                    scope_type=self._required(row, "scope_type"),
                    scope_key=self._required(row, "scope_key"),
                    **self._integers(row, JD_INTEGER_FIELDS),
                    gmv=Decimal(gmv) if gmv is not None else None,
                )
                async with self.session_factory() as session:
                    snapshot = await AnalyticsService(session).create_commerce_snapshot(
                        brand_id=brand_id,
                        data=payload,
                        actor_id=actor_id,
                    )
                results.append(
                    ImportRowResult(
                        row_number=row_number,
                        status="succeeded",
                        resource_id=snapshot.id,
                    )
                )
            except (ValueError, DomainError, PydanticValidationError) as exc:
                results.append(
                    ImportRowResult(
                        row_number=row_number,
                        status="failed",
                        error=str(exc),
                    )
                )
        result = self._result("jd_commerce", results)
        await self._save(
            brand_id=brand_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            content=content,
            result=result,
        )
        return result

    async def _existing(
        self,
        *,
        brand_id: uuid.UUID,
        idempotency_key: str,
        import_type: str,
        content: str,
    ) -> ImportBatchResult | None:
        checksum = hashlib.sha256(content.encode()).hexdigest()
        async with self.session_factory() as session:
            batch = await session.scalar(
                select(ImportBatch).where(
                    ImportBatch.brand_id == brand_id,
                    ImportBatch.idempotency_key == idempotency_key,
                )
            )
        if batch is None:
            return None
        if batch.import_type != import_type or batch.checksum != checksum:
            raise ConflictError("idempotency key is attached to different import content")
        return ImportBatchResult.model_validate(batch.result)

    async def _save(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        idempotency_key: str,
        content: str,
        result: ImportBatchResult,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            session.add(
                ImportBatch(
                    brand_id=brand_id,
                    import_type=result.import_type,
                    idempotency_key=idempotency_key,
                    checksum=hashlib.sha256(content.encode()).hexdigest(),
                    result=result.model_dump(mode="json"),
                    created_by=actor_id,
                )
            )

    @staticmethod
    def _rows(content: str) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
        if not reader.fieldnames:
            raise DomainValidationError("CSV header is required")
        return list(reader)

    @staticmethod
    def _required(row: dict[str, str], name: str) -> str:
        value = (row.get(name) or "").strip()
        if not value:
            raise ValueError(f"{name} is required")
        return value

    @staticmethod
    def _optional(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @classmethod
    def _optional_uuid(cls, value: str | None) -> uuid.UUID | None:
        normalized = cls._optional(value)
        return uuid.UUID(normalized) if normalized is not None else None

    @classmethod
    def _integers(
        cls, row: dict[str, str], names: tuple[str, ...]
    ) -> dict[str, int | None]:
        return {
            name: int(value) if (value := cls._optional(row.get(name))) is not None else None
            for name in names
        }

    @staticmethod
    def _boolean(value: str | None) -> bool:
        normalized = (value or "").strip().lower()
        if normalized in {"", "0", "false", "no"}:
            return False
        if normalized in {"1", "true", "yes"}:
            return True
        raise ValueError("is_correction must be true or false")

    @staticmethod
    def _result(import_type: str, rows: list[ImportRowResult]) -> ImportBatchResult:
        succeeded = sum(row.status == "succeeded" for row in rows)
        return ImportBatchResult(
            import_type=import_type,
            total_rows=len(rows),
            succeeded_rows=succeeded,
            failed_rows=len(rows) - succeeded,
            rows=rows,
        )
