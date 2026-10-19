"""Exercise original services and workflow with fictional inputs and fake outputs only."""

import asyncio
import io
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from PIL import Image, ImageDraw
from sqlalchemy import select

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import (
    ComplianceReport,
    ContentCandidate,
    GrowthRun,
    RegistryItem,
    RegistryRevision,
)
from smart_growth_agent.domain.enums import RegistryType, ReviewDecision, RevisionStatus
from smart_growth_agent.domain.errors import ConflictError, ValidationError
from smart_growth_agent.graph.growth_graph import build_growth_graph
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.llm.fake import DevelopmentFakeLLMGateway
from smart_growth_agent.llm.policy import GovernedLLMGateway
from smart_growth_agent.research.gateway import NullResearchGateway
from smart_growth_agent.schemas.ingestion import IngestionResolve
from smart_growth_agent.schemas.knowledge import KnowledgeSourceCreate
from smart_growth_agent.schemas.registry import (
    EvidenceDocumentCreate,
    RegistryItemCreate,
    RegistryRevisionCreate,
    RegistryRevisionUpdate,
)
from smart_growth_agent.schemas.reviews import HumanReviewCreate
from smart_growth_agent.schemas.runs import CampaignBriefCreate
from smart_growth_agent.services.evidence_import import EvidenceImportService
from smart_growth_agent.services.ingestion import IngestionDedupService
from smart_growth_agent.services.knowledge import KnowledgeService
from smart_growth_agent.services.media import ProductMediaService
from smart_growth_agent.services.platform_rule_import import PlatformRuleImportService
from smart_growth_agent.services.product_import import ProductImportService
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.services.reviews import ReviewService
from smart_growth_agent.services.runs import RunService
from smart_growth_agent.worker import Worker

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ROOT / "demo/materials"


class CountingFake(DevelopmentFakeLLMGateway):
    def __init__(self):
        self.calls = []

    def _payload(self, request):
        value = super()._payload(request)
        if request.purpose == "xhs_writer":
            inputs = json.loads(request.messages[-1].content)
            route = inputs["creative_route"]["route_key"]
            rewrite = inputs.get("task") == "targeted_compliance_rewrite"
            if route == "aesthetic-question" or (route == "aesthetic-detail" and not rewrite):
                value["body"] = "我用了7天，保证提高效率80%。这是故意注入的虚构违规测试稿。"
        return value

    async def generate(self, request, response_model):
        self.calls.append(request.purpose)
        return await super().generate(request, response_model)


def product_diagram():
    image = Image.new("RGB", (640, 480), "#f3f0e9")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (190, 65, 450, 415), radius=12, fill="#9eb6ce", outline="#3e5368", width=4
    )
    draw.line((220, 65, 220, 415), fill="#3e5368", width=3)
    draw.text((245, 185), "PAPER ORBIT", fill="#18334f")
    draw.text((245, 215), "NOTE01 / FICTIONAL", fill="#18334f")
    draw.text((160, 445), "SYNTHETIC DIAGRAM - NOT A REAL PRODUCT", fill="#18334f")
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


async def exercise_scenarios(session_factory, state, *, media_path, checkpointer=None):
    brand = uuid.UUID(state["brand_id"])
    admin = uuid.UUID(state["users"]["admin"])
    reviewer = uuid.UUID(state["users"]["reviewer"])
    product = uuid.UUID(state["product_id"])
    fake = CountingFake()
    gateway = GovernedLLMGateway(fake, session_factory)
    checks = {}
    ids = {}

    async def create(kind, key, payload, *, source="synthetic://paper-orbit/p0"):
        async with session_factory() as session:
            return await RegistryService(session).create_item(
                brand_id=brand,
                registry_type=kind,
                actor_id=admin,
                data=RegistryItemCreate(stable_key=key, payload=payload, source_uri=source),
            )

    async def activate(revision):
        async with session_factory() as session:
            return await RegistryService(session).activate_revision(
                brand_id=brand,
                revision_id=revision.id,
                actor_id=reviewer,
            )

    async def revision(payload, source):
        async with session_factory() as session:
            return await RegistryService(session).create_revision(
                brand_id=brand,
                item_id=product,
                actor_id=admin,
                data=RegistryRevisionCreate(payload=payload, source_uri=source),
            )

    async def make_run(label):
        async with session_factory() as session:
            svc = RunService(session)
            brief = await svc.create_brief(
                brand_id=brand,
                actor_id=admin,
                data=CampaignBriefCreate(
                    name=f"P0 离线演示 · {label}",
                    objective="演示虚构文具事实与证据治理",
                    product_item_ids=[product],
                    constraints={"body_length": 150},
                ),
            )
            return await svc.create_growth_run(
                brand_id=brand,
                brief_id=brief.id,
                actor_id=admin,
                idempotency_key="p0-" + str(uuid.uuid4()),
                max_attempts=1,
            )

    importer = ProductImportService(session_factory, gateway)
    initial = await importer.create_draft(
        brand_id=brand,
        actor_id=admin,
        pasted_text="",
        files=[("spec-v1.md", "text/markdown", (MATERIALS / "spec-v1.md").read_bytes())],
    )
    initial_revision = await revision(
        initial.payload.model_dump(mode="json"), "synthetic://paper-orbit/confirmed-v1"
    )
    await activate(initial_revision)
    await IngestionDedupService(session_factory).resolve(
        brand_id=brand,
        ingestion_id=initial.dedup.ingestion_id,
        data=IngestionResolve(
            decision="new_revision",
            decision_reason="脚本扮演人工：建立确认 V1，96 页",
            resulting_item_id=product,
            resulting_revision_id=initial_revision.id,
        ),
    )
    files = [
        (name, "text/markdown", (MATERIALS / name).read_bytes())
        for name in ["spec-v1.md", "conflicting-supplier-note.md"]
    ]
    draft = await importer.create_draft(brand_id=brand, actor_id=admin, pasted_text="", files=files)
    checks["same_sku_requires_revision"] = draft.dedup.recommended_action == "new_revision"
    checks["conflict_warning_preserved"] = any("冲突" in w for w in draft.warnings)
    conflicting = await revision(
        draft.payload.model_dump(mode="json"), "synthetic://paper-orbit/conflict"
    )
    ids["conflicting_draft_revision"] = str(conflicting.id)
    await IngestionDedupService(session_factory).resolve(
        brand_id=brand,
        ingestion_id=draft.dedup.ingestion_id,
        data=IngestionResolve(
            decision="new_revision",
            decision_reason="脚本扮演人工：冲突待核验，不激活",
            resulting_item_id=product,
            resulting_revision_id=conflicting.id,
        ),
    )
    before = len(fake.calls)
    try:
        await importer.create_draft(brand_id=brand, actor_id=admin, pasted_text="", files=files)
    except ConflictError:
        checks["exact_duplicate_skips_model"] = len(fake.calls) == before

    old_run, old_job, old_snapshots = await make_run("旧版本快照")
    async with session_factory() as session:
        old_product = await session.get(RegistryItem, product)
        old_revision_id = old_product.current_revision_id
        old_payload = (await session.get(RegistryRevision, old_revision_id)).payload.copy()

    confirmed = await importer.create_draft(
        brand_id=brand,
        actor_id=admin,
        pasted_text="",
        files=[
            (
                "spec-v2-confirmed.md",
                "text/markdown",
                (MATERIALS / "spec-v2-confirmed.md").read_bytes(),
            )
        ],
    )
    correct = await revision(
        confirmed.payload.model_dump(mode="json"), "synthetic://paper-orbit/confirmed-v2"
    )
    await IngestionDedupService(session_factory).resolve(
        brand_id=brand,
        ingestion_id=confirmed.dedup.ingestion_id,
        data=IngestionResolve(
            decision="new_revision",
            decision_reason="脚本扮演人工：采用已确认 V2",
            resulting_item_id=product,
            resulting_revision_id=correct.id,
        ),
    )
    await activate(correct)
    ids["active_product_revision"] = str(correct.id)
    try:
        async with session_factory() as session:
            await RegistryService(session).update_revision(
                brand_id=brand,
                revision_id=correct.id,
                actor_id=admin,
                data=RegistryRevisionUpdate(
                    payload={**confirmed.payload.model_dump(mode="json"), "name": "非法覆盖"}
                ),
            )
    except ConflictError:
        checks["active_revision_is_immutable"] = True

    evidence_draft = await EvidenceImportService(session_factory, gateway).create_draft(
        brand_id=brand,
        actor_id=admin,
        source_uri="synthetic://paper-orbit/page-count",
        source_name="evidence-page-count.md",
        source_text=(MATERIALS / "evidence-page-count.md").read_text(),
    )
    async with session_factory() as session:
        evidence = await RegistryService(session).create_evidence(
            brand_id=brand,
            actor_id=admin,
            data=EvidenceDocumentCreate(
                title=evidence_draft.title,
                document_type=evidence_draft.document_type,
                source_uri=evidence_draft.source_uri,
                content=evidence_draft.content,
            ),
        )
    claim, claim_revision = await create(
        RegistryType.PRODUCT_CLAIM,
        "p0-page-count",
        {
            "statement": "内页 120 页",
            "allowed_expressions": ["内页 120 页"],
            "forbidden_expressions": ["保证提高效率 80%", "完全防水"],
            "risk_level": "low",
            "product_item_ids": [str(product)],
            "evidence_document_ids": [str(evidence.id)],
        },
    )
    try:
        await activate(claim_revision)
    except ValidationError:
        checks["unverified_evidence_blocks_claim"] = True
    async with session_factory() as session:
        await RegistryService(session).verify_evidence(
            brand_id=brand, document_id=evidence.id, actor_id=reviewer
        )
    await activate(claim_revision)
    checks["verified_evidence_allows_claim"] = True
    await IngestionDedupService(session_factory).resolve(
        brand_id=brand,
        ingestion_id=evidence_draft.dedup.ingestion_id,
        data=IngestionResolve(decision="new_item", resulting_evidence_document_id=evidence.id),
    )

    async with session_factory() as session:
        unsupported = await RegistryService(session).create_evidence(
            brand_id=brand,
            actor_id=admin,
            data=EvidenceDocumentCreate(
                title="无证据宣传草稿（虚构，未验证）",
                document_type="unverified_marketing",
                source_uri="synthetic://paper-orbit/unsupported",
                content=(MATERIALS / "unsupported-claim.md").read_text(),
            ),
        )
    _, blocked_claim = await create(
        RegistryType.PRODUCT_CLAIM,
        "p0-unsupported-effect",
        {
            "statement": "保证提高效率 80%，完全防水",
            "allowed_expressions": ["保证提高效率 80%，完全防水"],
            "risk_level": "high",
            "product_item_ids": [str(product)],
            "evidence_document_ids": [str(unsupported.id)],
        },
    )
    try:
        await activate(blocked_claim)
    except ValidationError:
        checks["unsupported_effect_stays_draft"] = True
    ids["blocked_claim_revision"] = str(blocked_claim.id)

    clip = await importer.create_draft(
        brand_id=brand,
        actor_id=admin,
        pasted_text="",
        files=[("desk-clip.md", "text/markdown", (MATERIALS / "desk-clip.md").read_bytes())],
    )
    clip_item, clip_revision = await create(
        RegistryType.PRODUCT, clip.stable_key, clip.payload.model_dump(mode="json")
    )
    await activate(clip_revision)
    await IngestionDedupService(session_factory).resolve(
        brand_id=brand,
        ingestion_id=clip.dedup.ingestion_id,
        data=IngestionResolve(
            decision="new_item",
            resulting_item_id=clip_item.id,
            resulting_revision_id=clip_revision.id,
        ),
    )
    media_settings = Settings(media_storage_path=media_path)
    async with session_factory() as session:
        media = await ProductMediaService(session, media_settings).create(
            brand_id=brand,
            product_item_id=product,
            file_name="paper-orbit-fictional.png",
            content=product_diagram(),
            alt_text="虚构产品几何示意图，不是真实商品摄影",
            is_primary=True,
            actor_id=admin,
        )
    checks["fictional_media_attached"] = media.width == 640
    ids["product_media"] = str(media.id)

    rule = await PlatformRuleImportService(session_factory, gateway).create_draft(
        brand_id=brand,
        actor_id=admin,
        source_text=(MATERIALS / "rule-current.md").read_text(),
        source_url="https://example.com/paper-orbit/fictional-rules",
        verified_at=datetime.now(UTC),
    )
    _, rule_revision = await create(RegistryType.PLATFORM_RULE, "p0-current-rule", rule.payload)
    await activate(rule_revision)
    checks["imported_rule_preserves_source"] = (
        rule.payload["rule_text"] in (MATERIALS / "rule-current.md").read_text()
    )
    await IngestionDedupService(session_factory).resolve(
        brand_id=brand,
        ingestion_id=rule.dedup.ingestion_id,
        data=IngestionResolve(decision="new_item", resulting_revision_id=rule_revision.id),
    )
    old_url = "https://example.com/paper-orbit/fictional-rules-old"
    async with session_factory() as session:
        await KnowledgeService(session).create_source(
            brand_id=brand,
            actor_id=admin,
            data=KnowledgeSourceCreate(
                name="虚构历史规则",
                source_type="platform_rule",
                platform="xhs",
                canonical_url=old_url,
                freshness_days=90,
            ),
        )
    _, stale = await create(
        RegistryType.PLATFORM_RULE,
        "p0-stale-rule",
        {
            "platform": "xhs",
            "category": "content_compliance",
            "rule_text": (MATERIALS / "rule-expired.md").read_text(),
            "severity": "warning",
            "source_url": old_url,
            "verified_at": "2020-01-01T00:00:00Z",
        },
        source=old_url,
    )
    await activate(stale)
    new_run, new_job, new_snapshots = await make_run("新版本与审核")
    checks["historical_run_frozen"] = (
        old_revision_id in old_snapshots and correct.id not in old_snapshots
    )
    checks["next_run_uses_new_revision"] = (
        correct.id in new_snapshots and old_revision_id not in new_snapshots
    )
    checks["blocked_claim_excluded_from_run"] = blocked_claim.id not in new_snapshots
    async with session_factory() as session:
        original = await session.get(RegistryRevision, old_revision_id)
        pending = await session.get(RegistryRevision, conflicting.id)
        checks["old_payload_preserved"] = (
            original.payload == old_payload and original.status == RevisionStatus.RETIRED
        )
        checks["conflict_remains_draft"] = pending.status == RevisionStatus.DRAFT
        issues = await KnowledgeService(session).evaluate_run_freshness(
            brand_id=brand, run_id=new_run.id
        )
        checks["stale_rule_warns"] = any(
            issue.revision_id == stale.id and issue.stale for issue in issues
        )

    context = GrowthRuntimeContext(session_factory, gateway, NullResearchGateway())
    graph = build_growth_graph(checkpointer if checkpointer is not None else InMemorySaver())
    worker = Worker(
        graph, "p0-offline-script", session_factory=session_factory, runtime_context=context
    )
    await worker.execute(old_job)
    await worker.execute(new_job)
    async with session_factory() as session:
        run = await session.get(GrowthRun, new_run.id)
        candidates = list(
            await session.scalars(
                select(ContentCandidate).where(ContentCandidate.run_id == new_run.id)
            )
        )
        checks["graph_waits_for_human"] = (
            run.status.value == "waiting_human" and len(candidates) == 3
        )
        selected = run.recommended_candidate_id
    if checks["graph_waits_for_human"]:
        checks["automatic_rewrite_creates_version"] = any(
            c.current_version == 2 for c in candidates
        )
        checks["automatic_rewrite_is_bounded"] = max(c.current_version for c in candidates) == 3
        async with session_factory() as session:
            blocked_report = await session.scalar(
                select(ComplianceReport).where(ComplianceReport.has_blockers.is_(True))
            )
        blocked_candidate = next(c for c in candidates if c.route_key == "aesthetic-question")
        try:
            async with session_factory() as session:
                await ReviewService(session).submit(
                    brand_id=brand,
                    run_id=new_run.id,
                    reviewer_id=reviewer,
                    data=HumanReviewCreate(
                        decision=ReviewDecision.APPROVED, selected_candidate_id=blocked_candidate.id
                    ),
                    idempotency_key="p0-blocked-" + str(new_run.id),
                )
        except ValidationError:
            checks["blocker_cannot_be_approved"] = blocked_report is not None
        async with session_factory() as session:
            await ReviewService(session).submit(
                brand_id=brand,
                run_id=new_run.id,
                reviewer_id=reviewer,
                data=HumanReviewCreate(
                    decision=ReviewDecision.REQUEST_CHANGES,
                    selected_candidate_id=selected,
                    change_request="脚本扮演审核员：保留虚构披露，不添加效率或防水承诺",
                ),
                idempotency_key="p0-changes-" + str(new_run.id),
            )
        from smart_growth_agent.db.models import Job

        async with session_factory() as session:
            changed_job = await session.get(Job, new_job.id)
        await worker.execute(changed_job)
        async with session_factory() as session:
            changed_run = await session.get(GrowthRun, new_run.id)
            changed_candidate = await session.get(ContentCandidate, selected)
            checks["request_changes_rechecks_and_waits"] = (
                changed_run.status.value == "waiting_human"
                and changed_candidate.current_version >= 2
            )
        async with session_factory() as session:
            await ReviewService(session).submit(
                brand_id=brand,
                run_id=new_run.id,
                reviewer_id=reviewer,
                data=HumanReviewCreate(
                    decision=ReviewDecision.APPROVED, selected_candidate_id=selected
                ),
                idempotency_key="p0-review-" + str(new_run.id),
            )
        from smart_growth_agent.db.models import Job

        async with session_factory() as session:
            refreshed_job = await session.get(Job, new_job.id)
        await worker.execute(refreshed_job)
        async with session_factory() as session:
            run = await session.get(GrowthRun, new_run.id)
            checks["scripted_reviewer_resumes_graph"] = (
                run.status.value == "ready_for_manual_publish"
            )
    ids.update({"historical_run": str(old_run.id), "reviewed_run": str(new_run.id)})
    await gateway.aclose()
    return {
        "evidence_type": "offline_deterministic_fixtures",
        "fictional": True,
        "real_model_calls": 0,
        "fake_calls": len(fake.calls),
        "checks": checks,
        "ids": ids,
        "pass": len(checks) == 21 and all(checks.values()),
        "limitations": [
            "Scripted reviewer decisions, not real human review.",
            "Fake warnings are deterministic fixtures, not model-quality evidence.",
            (
                "InMemorySaver demonstrates same-process resume only."
                if checkpointer is None
                else "PostgreSQL checkpoint used; this rehearsal is not a crash-recovery benchmark."
            ),
            "Source conflicts are surfaced for review, not automatically proven or resolved.",
        ],
    }


async def install_local_scenarios():
    from smart_growth_agent.config import get_settings
    from smart_growth_agent.db.session import SessionFactory

    if get_settings().llm_mode != "fake" or not get_settings().local_demo:
        raise RuntimeError("fictional scenarios require local fake runtime")
    destination = Path(
        os.environ.get("SMART_GROWTH_DEMO_SCENARIO_PATH", ROOT / ".runtime/p0-installed.json")
    )
    if await asyncio.to_thread(destination.exists):
        return json.loads(await asyncio.to_thread(destination.read_text))
    state_path = Path(
        os.environ.get("SMART_GROWTH_DEMO_STATE_PATH", ROOT / ".runtime/demo-state.json")
    )
    state = json.loads(await asyncio.to_thread(state_path.read_text))
    async with SessionFactory() as session:
        partial = await session.scalar(
            select(RegistryItem.id).where(
                RegistryItem.brand_id == uuid.UUID(state["brand_id"]),
                RegistryItem.stable_key == "p0-page-count",
            )
        )
    if partial is not None:
        raise RuntimeError(
            "partial scenario records exist; inspect recovery checkpoint before retrying"
        )
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
        await saver.setup()
        report = await exercise_scenarios(
            SessionFactory, state, media_path=get_settings().media_storage_path, checkpointer=saver
        )
        report["historical_run_postgres_checkpoint"] = True
    if not report["pass"]:
        raise RuntimeError(
            "offline scenario installation failed; inspect preserved database records"
        )
    await asyncio.to_thread(
        destination.write_text, json.dumps(report, ensure_ascii=False, indent=2)
    )
    return report
