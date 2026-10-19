from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from smart_growth_agent.db.models import (
    Brand,
    CampaignBrief,
    EvidenceDocument,
    GrowthRun,
    RegistryItem,
    RegistryRevision,
    RunRegistrySnapshot,
    User,
)
from smart_growth_agent.domain.enums import RegistryType, RevisionStatus, RunStatus
from smart_growth_agent.services.claim_coverage import ClaimCoverageService


async def _active_registry_item(
    session,
    *,
    brand_id,
    actor_id,
    registry_type,
    stable_key,
    payload,
):
    item = RegistryItem(
        brand_id=brand_id,
        registry_type=registry_type,
        stable_key=stable_key,
    )
    session.add(item)
    await session.flush()
    revision = RegistryRevision(
        item_id=item.id,
        version=1,
        status=RevisionStatus.ACTIVE,
        payload=payload,
        search_text=stable_key,
        checksum=stable_key.ljust(64, "0")[:64],
        created_by=actor_id,
        activated_by=actor_id,
        activated_at=datetime.now(UTC),
    )
    session.add(revision)
    await session.flush()
    item.current_revision_id = revision.id
    return item, revision


@pytest.mark.asyncio
async def test_claim_coverage_distinguishes_current_registry_and_run_snapshot(
    session_factory,
) -> None:
    async with session_factory() as session, session.begin():
        brand = Brand(name="Coverage Brand", slug="coverage-brand")
        user = User(
            email="coverage@example.com",
            password_hash="unused",
            display_name="Coverage",
        )
        session.add_all([brand, user])
        await session.flush()
        evidence = EvidenceDocument(
            brand_id=brand.id,
            title="NFC 规格确认",
            document_type="product_specification",
            source_uri="test://nfc",
            content="支持 NFC 信息交互",
            checksum="e" * 64,
            verified_by=user.id,
            verified_at=datetime.now(UTC),
            is_active=True,
        )
        session.add(evidence)
        await session.flush()
        product, product_revision = await _active_registry_item(
            session,
            brand_id=brand.id,
            actor_id=user.id,
            registry_type=RegistryType.PRODUCT,
            stable_key="bracelet-one",
            payload={
                "name": "手链一号",
                "product_type": "stationery",
                "description": "创意文具",
                "features": ["NFC"],
                "materials": [],
            },
        )
        second_product, _second_revision = await _active_registry_item(
            session,
            brand_id=brand.id,
            actor_id=user.id,
            registry_type=RegistryType.PRODUCT,
            stable_key="bracelet-two",
            payload={
                "name": "手链二号",
                "product_type": "stationery",
                "description": "创意文具",
                "features": ["模块化"],
                "materials": [],
            },
        )
        claim, claim_revision = await _active_registry_item(
            session,
            brand_id=brand.id,
            actor_id=user.id,
            registry_type=RegistryType.PRODUCT_CLAIM,
            stable_key="bracelet-one-nfc",
            payload={
                "statement": "支持 NFC 信息交互",
                "allowed_expressions": ["支持 NFC 数字体验"],
                "forbidden_expressions": [],
                "risk_level": "low",
                "product_item_ids": [str(product.id)],
                "evidence_document_ids": [str(evidence.id)],
            },
        )
        brief = CampaignBrief(
            brand_id=brand.id,
            name="覆盖率 Run",
            objective="验证快照",
            product_item_ids=[str(product.id)],
            audience_item_ids=[],
            constraints={},
            created_by=user.id,
        )
        session.add(brief)
        await session.flush()
        run = GrowthRun(
            brand_id=brand.id,
            brief_id=brief.id,
            thread_id=str(uuid.uuid4()),
            status=RunStatus.QUEUED,
            gate_status="pending",
            created_by=user.id,
        )
        session.add(run)
        await session.flush()
        session.add_all(
            [
                RunRegistrySnapshot(
                    brand_id=brand.id,
                    run_id=run.id,
                    item_id=product.id,
                    revision_id=product_revision.id,
                    purpose="selected_product",
                ),
                RunRegistrySnapshot(
                    brand_id=brand.id,
                    run_id=run.id,
                    item_id=claim.id,
                    revision_id=claim_revision.id,
                    purpose="product_claim",
                ),
            ]
        )
        brand_id, run_id, evidence_id = brand.id, run.id, evidence.id
        claim_revision_id, second_product_id = claim_revision.id, second_product.id

    async with session_factory() as session:
        current = await ClaimCoverageService(session).current(brand_id=brand_id)
        frozen = await ClaimCoverageService(session).for_run(
            brand_id=brand_id,
            run_id=run_id,
        )

    assert current.products_total == 2
    assert current.product_claim_coverage_percent == 50
    assert current.claim_evidence_coverage_percent == 100
    assert {row.status for row in current.products} == {"covered", "no_claims"}
    assert frozen.products_total == 1
    assert frozen.product_claim_coverage_percent == 100

    async with session_factory() as session, session.begin():
        shared_claim = await session.get(RegistryRevision, claim_revision_id)
        assert shared_claim is not None
        shared_claim.payload = {
            **shared_claim.payload,
            "product_item_ids": [str(product.id), str(second_product_id)],
        }
    async with session_factory() as session:
        shared = await ClaimCoverageService(session).current(brand_id=brand_id)
    assert shared.claims_total == shared.fully_supported_claims == 1
    assert shared.claim_evidence_coverage_percent == 100

    async with session_factory() as session, session.begin():
        evidence = await session.get(EvidenceDocument, evidence_id)
        assert evidence is not None
        evidence.is_active = False
    async with session_factory() as session:
        changed = await ClaimCoverageService(session).current(brand_id=brand_id)
    assert changed.claim_evidence_coverage_percent == 0
    assert changed.products[0].status == "evidence_gap"
    assert "未核验、已停用或不存在" in changed.products[0].warnings[0]
