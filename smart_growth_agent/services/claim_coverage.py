from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import (
    EvidenceDocument,
    GrowthRun,
    RegistryItem,
    RegistryRevision,
    RunRegistrySnapshot,
)
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import NotFoundError
from smart_growth_agent.schemas.knowledge import (
    ClaimCoverageRead,
    ProductClaimCoverageRead,
)


def _ids(values: object) -> set[uuid.UUID]:
    if not isinstance(values, list):
        return set()
    parsed: set[uuid.UUID] = set()
    for value in values:
        try:
            parsed.add(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return parsed


class ClaimCoverageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def current(self, *, brand_id: uuid.UUID) -> ClaimCoverageRead:
        rows = list(
            (
                await self.session.execute(
                    select(RegistryItem, RegistryRevision)
                    .join(
                        RegistryRevision,
                        RegistryRevision.id == RegistryItem.current_revision_id,
                    )
                    .where(
                        RegistryItem.brand_id == brand_id,
                        RegistryItem.archived_at.is_(None),
                        RegistryItem.registry_type.in_(
                            [RegistryType.PRODUCT, RegistryType.PRODUCT_CLAIM]
                        ),
                    )
                )
            ).all()
        )
        return await self._build(
            brand_id=brand_id,
            scope="current_active_registry",
            run_id=None,
            rows=rows,
        )

    async def for_run(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> ClaimCoverageRead:
        exists = await self.session.scalar(
            select(GrowthRun.id).where(
                GrowthRun.id == run_id,
                GrowthRun.brand_id == brand_id,
            )
        )
        if exists is None:
            raise NotFoundError("growth run not found")
        rows = list(
            (
                await self.session.execute(
                    select(RegistryItem, RegistryRevision)
                    .join(
                        RunRegistrySnapshot,
                        RunRegistrySnapshot.item_id == RegistryItem.id,
                    )
                    .join(
                        RegistryRevision,
                        RegistryRevision.id == RunRegistrySnapshot.revision_id,
                    )
                    .where(
                        RunRegistrySnapshot.run_id == run_id,
                        RunRegistrySnapshot.brand_id == brand_id,
                        RegistryItem.registry_type.in_(
                            [RegistryType.PRODUCT, RegistryType.PRODUCT_CLAIM]
                        ),
                    )
                )
            ).all()
        )
        return await self._build(
            brand_id=brand_id,
            scope="run_registry_snapshot",
            run_id=run_id,
            rows=rows,
        )

    async def _build(
        self,
        *,
        brand_id: uuid.UUID,
        scope: str,
        run_id: uuid.UUID | None,
        rows: list[tuple[RegistryItem, RegistryRevision]],
    ) -> ClaimCoverageRead:
        products = [row for row in rows if row[0].registry_type == RegistryType.PRODUCT]
        claims = [row for row in rows if row[0].registry_type == RegistryType.PRODUCT_CLAIM]
        evidence_ids = set().union(
            *(_ids(revision.payload.get("evidence_document_ids")) for _, revision in claims),
            set(),
        )
        verified_ids: set[uuid.UUID] = set()
        if evidence_ids:
            verified_ids = set(
                await self.session.scalars(
                    select(EvidenceDocument.id).where(
                        EvidenceDocument.brand_id == brand_id,
                        EvidenceDocument.id.in_(evidence_ids),
                        EvidenceDocument.is_active.is_(True),
                        EvidenceDocument.verified_at.is_not(None),
                    )
                )
            )
        claims_by_product: dict[
            uuid.UUID, list[tuple[RegistryItem, RegistryRevision]]
        ] = defaultdict(list)
        for claim in claims:
            for product_id in _ids(claim[1].payload.get("product_item_ids")):
                claims_by_product[product_id].append(claim)

        product_rows: list[ProductClaimCoverageRead] = []
        fully_supported_claim_ids: set[uuid.UUID] = set()
        evidence_used: set[uuid.UUID] = set()
        for product, revision in products:
            product_claims = claims_by_product.get(product.id, [])
            fully_supported = 0
            product_evidence: set[uuid.UUID] = set()
            warnings: list[str] = []
            for claim, claim_revision in product_claims:
                cited = _ids(claim_revision.payload.get("evidence_document_ids"))
                valid = cited & verified_ids
                product_evidence |= valid
                evidence_used |= valid
                if cited and cited <= verified_ids:
                    fully_supported += 1
                    fully_supported_claim_ids.add(claim.id)
                else:
                    missing = len(cited - verified_ids)
                    warnings.append(
                        f"Claim {claim.stable_key} 有 {missing or 1} 份证据未核验、已停用或不存在"
                    )
            if not product_claims:
                status = "no_claims"
                warnings.append("当前产品没有可用 Product Claim；生成时只能使用基础产品事实")
            elif fully_supported < len(product_claims):
                status = "evidence_gap"
            else:
                status = "covered"
            product_rows.append(
                ProductClaimCoverageRead(
                    product_item_id=product.id,
                    product_revision_id=revision.id,
                    product_name=str(revision.payload.get("name") or product.stable_key),
                    active_claims=len(product_claims),
                    fully_supported_claims=fully_supported,
                    verified_evidence_documents=len(product_evidence),
                    status=status,
                    warnings=warnings,
                )
            )

        products_with_claims = sum(row.active_claims > 0 for row in product_rows)
        return ClaimCoverageRead(
            scope=scope,
            run_id=run_id,
            products_total=len(product_rows),
            products_with_claims=products_with_claims,
            product_claim_coverage_percent=round(
                products_with_claims / len(product_rows) * 100, 1
            )
            if product_rows
            else 0,
            claims_total=len(claims),
            fully_supported_claims=len(fully_supported_claim_ids),
            claim_evidence_coverage_percent=round(
                len(fully_supported_claim_ids) / len(claims) * 100, 1
            )
            if claims
            else 0,
            verified_evidence_documents=len(evidence_used),
            products=sorted(product_rows, key=lambda row: row.product_name),
        )
