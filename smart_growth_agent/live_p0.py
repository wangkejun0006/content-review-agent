"""Bounded integration harness: real HTTP model, fictional inputs, explicit stage control."""

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select

from smart_growth_agent.config import get_settings
from smart_growth_agent.db.models import (
    ContentCandidate,
    ContentVersion,
    GrowthRun,
    Job,
    RegistryItem,
    RunRegistrySnapshot,
)
from smart_growth_agent.db.session import SessionFactory, engine
from smart_growth_agent.domain.enums import JobStatus, RegistryType
from smart_growth_agent.graph.growth_graph import build_growth_graph
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.research.gateway import NullResearchGateway
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.registry import RegistryItemCreate, RegistryRevisionCreate
from smart_growth_agent.security import create_access_token
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.worker import Worker

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / ".runtime/live-p0-20261016"
REPORT = ROOT / "reports/live-p0-20261016.json"
MATERIALS = ROOT / "demo/materials"


def read(path):
    return json.loads(path.read_text())


def ledger():
    current = read(ROOT / ".runtime/live-budget.json")
    original = read(CAMPAIGN / "budget-before.json")
    auth = read(CAMPAIGN / "authorization.json")
    assert current["calls"][:37] == original["calls"], "Budget history changed"
    assert auth["cumulative_cap"] == 61 and len(current["calls"]) <= 61, "Budget violation"
    return current


def report():
    return (
        read(REPORT)
        if REPORT.exists()
        else {
            "campaign": "p0-live-20261016",
            "started_at": datetime.now(UTC).isoformat(),
            "evidence_type": "real_model_fictional_data_and_labeled_fault_injection",
            "initial_requests": 37,
            "max_new_requests": 24,
            "cumulative_cap": 61,
            "model": "deepseek-flash",
            "cost_reserve_cny": 2,
            "stages": {},
            "checks": {},
            "external_publication": False,
            "original_repository_modified": False,
        }
    )


def save(value):
    calls = ledger()["calls"][37:]
    value.update(
        {
            "new_requests": len(calls),
            "cumulative_requests": 37 + len(calls),
            "reported_input_tokens": sum(c.get("prompt_tokens", 0) for c in calls),
            "reported_output_tokens": sum(c.get("completion_tokens", 0) for c in calls),
            "unknown_or_pending": sum(c.get("status") != "response_received" for c in calls),
            "usage_is_not_invoice": True,
        }
    )
    value["reported_peak_price_cny"] = round(
        value["reported_input_tokens"] * 2e-6 + value["reported_output_tokens"] * 8e-6, 6
    )
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    for name in [
        "SMART_GROWTH_OPENAI_API_KEY",
        "SMART_GROWTH_JWT_SECRET",
        "SMART_GROWTH_DATABASE_URL",
    ]:
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    REPORT.write_text(text)


def require_budget(minimum):
    remaining = 61 - len(ledger()["calls"])
    assert remaining >= minimum, f"Only {remaining} requests remain; phase needs at least {minimum}"


class API:
    async def __aenter__(self):
        from smart_growth_agent.app.main import app

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=180
        )
        self.state = read(CAMPAIGN / "state.json")
        self.brand = uuid.UUID(self.state["brand_id"])
        self.admin = uuid.UUID(self.state["users"]["admin"])
        self.tokens = {}
        for role, ident in self.state["users"].items():
            principal = Principal(
                user_id=uuid.UUID(ident),
                brand_id=self.brand,
                role=role,
                email=f"{role}@paper-orbit.example",
            )
            self.tokens[role] = create_access_token(principal, get_settings())[0]
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def call(
        self,
        method,
        path,
        *,
        role="editor",
        body=None,
        data=None,
        files=None,
        key=None,
        expect=None,
    ):
        headers = {"Authorization": "Bearer " + self.tokens[role]}
        if key:
            headers["Idempotency-Key"] = key
        response = await self.client.request(
            method, path, json=body, data=data, files=files, headers=headers
        )
        if expect is not None:
            assert response.status_code == expect, (
                f"Expected {expect}, received {response.status_code}"
            )
        elif response.status_code >= 400:
            raise RuntimeError(f"API {response.status_code}: {response.text[:1000]}")
        return response.json() if response.content else None

    async def resolve(self, draft, **kwargs):
        from smart_growth_agent.schemas.ingestion import IngestionResolve
        from smart_growth_agent.services.ingestion import IngestionDedupService

        await IngestionDedupService(SessionFactory).resolve(
            brand_id=self.brand,
            ingestion_id=uuid.UUID(draft["dedup"]["ingestion_id"]),
            data=IngestionResolve(**kwargs),
        )


async def imports(value):
    async with API() as api:
        outputs = value.setdefault("imports", {})
        tasks = [
            (
                "conflict",
                "/v1/registry/product/ai-drafts",
                {},
                [
                    (
                        "files",
                        ("spec-v1.md", (MATERIALS / "spec-v1.md").read_bytes(), "text/markdown"),
                    ),
                    (
                        "files",
                        (
                            "conflicting-supplier-note.md",
                            (MATERIALS / "conflicting-supplier-note.md").read_bytes(),
                            "text/markdown",
                        ),
                    ),
                ],
            ),
            (
                "confirmed",
                "/v1/registry/product/ai-drafts",
                {},
                [
                    (
                        "files",
                        (
                            "spec-v2-confirmed.md",
                            (MATERIALS / "spec-v2-confirmed.md").read_bytes(),
                            "text/markdown",
                        ),
                    ),
                ],
            ),
            (
                "evidence",
                "/v1/evidence/ai-drafts",
                {"source_uri": "synthetic://paper-orbit/live-p0/evidence"},
                [
                    (
                        "file",
                        (
                            "evidence-page-count.md",
                            (MATERIALS / "evidence-page-count.md").read_bytes(),
                            "text/markdown",
                        ),
                    ),
                ],
            ),
            (
                "rule",
                "/v1/registry/platform_rule/ai-drafts",
                {
                    "source_url": "https://example.com/paper-orbit/live-p0-rule",
                    "verified_at": datetime.now(UTC).isoformat(),
                },
                [
                    (
                        "file",
                        (
                            "rule-current.md",
                            (MATERIALS / "rule-current.md").read_bytes(),
                            "text/markdown",
                        ),
                    )
                ],
            ),
        ]
        for name, path, data, files in tasks:
            if name in outputs:
                continue
            require_budget(1)
            outputs[name] = await api.call("POST", path, data=data, files=files)
            save(value)
            print(
                f"Import {name}: received; new requests={len(ledger()['calls']) - 37}", flush=True
            )
        count = len(ledger()["calls"])
        await api.call("POST", tasks[0][1], data=tasks[0][2], files=tasks[0][3], expect=409)
        value["checks"]["duplicate_skips_paid_call"] = len(ledger()["calls"]) == count
        save(value)


async def gates(value):
    drafts = value["imports"]
    assert set(drafts) == {"conflict", "confirmed", "evidence", "rule"}
    conflict = drafts["conflict"]
    warnings = " ".join([*conflict.get("warnings", []), *conflict.get("missing_fields", [])])
    assert any(word in warnings for word in ["冲突", "不一致", "矛盾"]), "Conflict not surfaced"
    confirmed = drafts["confirmed"]["payload"]
    facts = json.dumps(confirmed, ensure_ascii=False)
    assert "120" in facts and "A5" in facts and "160" not in facts and "A6" not in facts
    assert not any(
        term in statement
        for statement in confirmed["features"]
        for term in ["提高效率", "完全防水", "80%"]
    )
    evidence = drafts["evidence"]
    assert evidence["relevant_excerpts"]
    assert all(x in evidence["content"] for x in evidence["relevant_excerpts"])
    value["checks"].update(
        {
            "conflict_surfaced": True,
            "confirmed_v2_facts_correct": True,
            "no_unsupported_effect_as_feature": True,
            "evidence_excerpts_grounded": True,
            "rule_excerpt_grounded": drafts["rule"]["source_excerpt"]
            in (MATERIALS / "rule-current.md").read_text(),
        }
    )
    async with API() as api:
        product = uuid.UUID(api.state["product_id"])
        old = await api.call(
            "POST",
            "/v1/growth-runs",
            body={"brief_id": api.state["brief_id"]},
            key="live-p0-old-snapshot-20261016",
        )
        value["historical_snapshot_run"] = old["id"]
        value["historical_snapshot_execution"] = (
            "snapshot-only queued job; targeted harness never claims it"
        )
        async with SessionFactory() as session:
            item = await session.get(RegistryItem, product)
            prior = item.current_revision_id
        async with SessionFactory() as session:
            _, pending = await RegistryService(session).create_item(
                brand_id=api.brand,
                registry_type=RegistryType.PRODUCT,
                actor_id=api.admin,
                data=RegistryItemCreate(
                    stable_key="live-p0-conflict",
                    payload=conflict["payload"],
                    source_uri="synthetic://paper-orbit/live-p0/conflict",
                ),
            )
        async with SessionFactory() as session:
            correct = await RegistryService(session).create_revision(
                brand_id=api.brand,
                item_id=product,
                actor_id=api.admin,
                data=RegistryRevisionCreate(
                    payload=confirmed, source_uri="synthetic://paper-orbit/live-p0/v2"
                ),
            )
        await api.call(
            "POST",
            f"/v1/registry/product/{product}/revisions/{correct.id}/activate",
            role="reviewer",
        )
        await api.resolve(
            drafts["confirmed"],
            decision="new_revision",
            decision_reason="Scripted reviewer selected confirmed fictional V2",
            resulting_item_id=product,
            resulting_revision_id=correct.id,
        )
        await api.resolve(
            conflict,
            decision="new_item",
            resulting_item_id=pending.item_id,
            resulting_revision_id=pending.id,
        )
        created = await api.call(
            "POST",
            "/v1/evidence",
            body={
                "title": evidence["title"],
                "document_type": evidence["document_type"],
                "content": evidence["content"],
                "source_uri": evidence["source_uri"],
            },
        )
        claim = await api.call(
            "POST",
            "/v1/registry/product_claim",
            body={
                "stable_key": "live-p0-pages",
                "payload": {
                    "statement": "内页 120 页",
                    "allowed_expressions": ["内页 120 页"],
                    "forbidden_expressions": ["保证提高效率80%", "完全防水"],
                    "risk_level": "low",
                    "product_item_ids": [str(product)],
                    "evidence_document_ids": [created["id"]],
                },
            },
        )
        claim_revision = claim["revisions"][0]["id"]
        path = f"/v1/registry/product_claim/{claim['id']}/revisions/{claim_revision}/activate"
        await api.call("POST", path, role="reviewer", expect=422)
        value["checks"]["unverified_evidence_blocks_claim"] = True
        await api.call("POST", f"/v1/evidence/{created['id']}/verify", role="reviewer")
        await api.call("POST", path, role="reviewer")
        value["checks"]["verified_limited_evidence_allows_claim"] = True
        await api.resolve(
            evidence, decision="new_item", resulting_evidence_document_id=created["id"]
        )
        unverified = await api.call(
            "POST",
            "/v1/evidence",
            body={
                "title": "无依据宣传（虚构，未验证）",
                "document_type": "unverified_marketing",
                "source_uri": "synthetic://paper-orbit/live-p0/unsupported",
                "content": (MATERIALS / "unsupported-claim.md").read_text(),
            },
        )
        blocked = await api.call(
            "POST",
            "/v1/registry/product_claim",
            body={
                "stable_key": "live-p0-unsupported",
                "payload": {
                    "statement": "保证提高效率80%，完全防水",
                    "allowed_expressions": ["保证提高效率80%，完全防水"],
                    "risk_level": "high",
                    "product_item_ids": [str(product)],
                    "evidence_document_ids": [unverified["id"]],
                },
            },
        )
        blocked_revision = blocked["revisions"][0]["id"]
        await api.call(
            "POST",
            f"/v1/registry/product_claim/{blocked['id']}/revisions/{blocked_revision}/activate",
            role="reviewer",
            expect=422,
        )
        value["checks"]["unsupported_claim_stays_draft"] = True
        rule = await api.call(
            "POST",
            "/v1/registry/platform_rule",
            body={
                "stable_key": "live-p0-imported-rule",
                "payload": drafts["rule"]["payload"],
                "source_uri": "https://example.com/paper-orbit/live-p0-rule",
            },
        )
        await api.call(
            "POST",
            f"/v1/registry/platform_rule/{rule['id']}/revisions/{rule['revisions'][0]['id']}/activate",
            role="reviewer",
        )
        await api.resolve(
            drafts["rule"],
            decision="new_item",
            resulting_item_id=rule["id"],
            resulting_revision_id=rule["revisions"][0]["id"],
        )
        new = await api.call(
            "POST",
            "/v1/growth-runs",
            body={"brief_id": api.state["brief_id"]},
            key="live-p0-main-20261016",
        )
        value["run_id"] = new["id"]
        async with SessionFactory() as session:
            old_ids = set(
                await session.scalars(
                    select(RunRegistrySnapshot.revision_id).where(
                        RunRegistrySnapshot.run_id == uuid.UUID(old["id"])
                    )
                )
            )
            new_ids = set(
                await session.scalars(
                    select(RunRegistrySnapshot.revision_id).where(
                        RunRegistrySnapshot.run_id == uuid.UUID(new["id"])
                    )
                )
            )
        value["checks"].update(
            {
                "historical_snapshot_frozen": prior in old_ids and correct.id not in old_ids,
                "new_snapshot_uses_v2": correct.id in new_ids and prior not in new_ids,
                "unsupported_claim_not_snapshotted": uuid.UUID(blocked_revision) not in new_ids,
                "conflict_draft_not_snapshotted": pending.id not in new_ids,
            }
        )
        assert all(value["checks"].values())
        save(value)


async def worker(value):
    ident = "live-p0-" + str(os.getpid())
    run_id = uuid.UUID(value["run_id"])
    async with SessionFactory() as session, session.begin():
        job = await session.scalar(
            select(Job)
            .where(
                Job.payload["run_id"].as_string() == str(run_id),
                Job.status == JobStatus.QUEUED,
                Job.attempts < Job.max_attempts,
            )
            .with_for_update(skip_locked=True)
        )
        assert job is not None, "Targeted job is not claimable"
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.worker_id = ident
        job.lease_until = datetime.now(UTC) + timedelta(seconds=300)
        await session.flush()
        session.expunge(job)
    gateway = build_llm_gateway(get_settings(), SessionFactory)
    context = GrowthRuntimeContext(SessionFactory, gateway, NullResearchGateway())
    try:
        async with AsyncPostgresSaver.from_conn_string(
            get_settings().checkpoint_database_url
        ) as saver:
            await saver.setup()
            graph = build_growth_graph(saver)
            await Worker(
                graph, ident, session_factory=SessionFactory, runtime_context=context
            ).execute(job)
    finally:
        await gateway.aclose()
    async with SessionFactory() as session:
        run = await session.get(GrowthRun, run_id)
        return {"status": run.status.value, "error": run.error, "pid": os.getpid()}


async def spawn_worker(value, label, minimum):
    require_budget(minimum)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/live_p0.py",
        "worker-" + label,
        "--allow-model-calls",
        cwd=ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    value.setdefault("worker_pids", {})[label] = proc.pid
    output, _ = await proc.communicate()
    text = output.decode(errors="replace")
    for name in [
        "SMART_GROWTH_OPENAI_API_KEY",
        "SMART_GROWTH_JWT_SECRET",
        "SMART_GROWTH_DATABASE_URL",
    ]:
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    (CAMPAIGN / f"worker-{label}.log").write_text(text)
    assert proc.returncode == 0, "Targeted worker failed; sanitized log retained"
    async with SessionFactory() as session:
        run = await session.get(GrowthRun, uuid.UUID(value["run_id"]))
        if run.error:
            value.setdefault("worker_errors", []).append(run.error)
        return run.status.value


async def generate(value):
    status = await spawn_worker(value, "generate", 11)
    value["generation_status"] = status
    assert status == "waiting_human", f"Generation stopped at {status}"
    async with SessionFactory() as session:
        candidates = list(
            await session.scalars(
                select(ContentCandidate).where(
                    ContentCandidate.run_id == uuid.UUID(value["run_id"])
                )
            )
        )
        versions = []
        for candidate in candidates:
            version = await session.scalar(
                select(ContentVersion).where(
                    ContentVersion.candidate_id == candidate.id,
                    ContentVersion.version == candidate.current_version,
                )
            )
            versions.append(
                {
                    "candidate_id": str(candidate.id),
                    "version_id": str(version.id),
                    "version": version.version,
                    "payload": version.payload,
                }
            )
    value["original_model_candidates"] = versions
    value["checks"]["three_real_model_candidates"] = len(versions) == 3
    save(value)


async def inject(value):
    require_budget(7)
    from smart_growth_agent.agents.compliance_agent import CANDIDATE_REVIEW_GRAPH
    from smart_growth_agent.schemas.phase2 import WriterOutput
    from smart_growth_agent.services.audit import record_audit
    from smart_growth_agent.services.compliance import ComplianceService

    run_id = uuid.UUID(value["run_id"])
    async with API() as api:
        eligible = [x for x in value["original_model_candidates"] if x["version"] == 1]
        assert eligible, "No original version-1 candidate has automatic rewrite headroom"
        chosen = eligible[0]
        candidate_id = uuid.UUID(chosen["candidate_id"])
        original = WriterOutput.model_validate(chosen["payload"])
        injected = original.model_copy(
            update={
                "body": (
                        "我用了7天，保证提高效率80%，完全防水。"
                        "这是受控故障注入测试稿，不是模型自然输出。"
                    )
            }
        )
        event = uuid.uuid4()
        gateway = build_llm_gateway(get_settings(), SessionFactory)
        service = ComplianceService(SessionFactory, gateway)
        try:
            version_id = await service.save_human_edit(
                brand_id=api.brand,
                candidate_id=candidate_id,
                edited_content=injected,
                review_id=event,
            )
            async with SessionFactory() as session, session.begin():
                record_audit(
                    session,
                    brand_id=api.brand,
                    actor_id=uuid.UUID(api.state["users"]["reviewer"]),
                    action="validation.controlled_fault_injection",
                    resource_type="content_version",
                    resource_id=version_id,
                    details={
                        "origin": "explicit_test_fixture_not_natural_model_output",
                        "original_version_id": chosen["version_id"],
                        "test_event": str(event),
                    },
                )
            value["fault_injection"] = {
                "candidate_id": str(candidate_id),
                "original_version_id": chosen["version_id"],
                "injected_version_id": str(version_id),
                "event_id": str(event),
                "origin": "explicit_test_fixture_not_natural_model_output",
                "body": injected.body,
            }
            save(value)
            audit_id = await service.review_content_version(
                brand_id=api.brand, content_version_id=version_id
            )
            audit = await service.get_report(brand_id=api.brand, report_id=audit_id)
            value["fault_injection"]["initial_compliance"] = audit.model_dump(mode="json")
            value["checks"]["controlled_unsafe_draft_blocked"] = audit.has_blockers
            assert audit.has_blockers, "Controlled unsafe draft was not blocked"
            await api.call(
                "POST",
                f"/v1/growth-runs/{run_id}/reviews",
                role="reviewer",
                body={"decision": "approved", "selected_candidate_id": str(candidate_id)},
                key="live-p0-denied-blocker-20261016",
                expect=422,
            )
            value["checks"]["blocker_cannot_be_approved"] = True
            await api.call(
                "POST",
                f"/v1/growth-runs/{run_id}/reviews",
                role="editor",
                body={"decision": "approved", "selected_candidate_id": str(candidate_id)},
                key="live-p0-denied-editor-20261016",
                expect=403,
            )
            value["checks"]["editor_cannot_review"] = True
            save(value)
            require_budget(3)
            result = await CANDIDATE_REVIEW_GRAPH.ainvoke(
                {"brand_id": api.brand, "run_id": run_id, "candidate_id": candidate_id},
                context=GrowthRuntimeContext(SessionFactory, gateway, NullResearchGateway()),
            )
            final = await service.get_report(
                brand_id=api.brand, report_id=result["compliance_report_id"]
            )
            async with SessionFactory() as session:
                candidate = await session.get(ContentCandidate, candidate_id)
                version = await session.scalar(
                    select(ContentVersion).where(
                        ContentVersion.candidate_id == candidate_id,
                        ContentVersion.version == candidate.current_version,
                    )
                )
            value["fault_injection"]["rewritten_version"] = {
                "id": str(version.id),
                "version": version.version,
                "payload": version.payload,
                "compliance": final.model_dump(mode="json"),
            }
            value["checks"]["automatic_real_rewrite_created_version"] = version.version == 3
            value["checks"]["automatic_rewrite_passed_compliance"] = (
                not final.has_blockers and final.semantic_pass
            )
            assert value["checks"]["automatic_real_rewrite_created_version"]
            assert value["checks"]["automatic_rewrite_passed_compliance"]
            save(value)
        finally:
            await gateway.aclose()


async def human(value):
    require_budget(3)
    if "generate" not in value.setdefault("worker_pids", {}):
        for line in (CAMPAIGN / "worker-generate.log").read_text().splitlines():
            try:
                result = json.loads(line)
            except ValueError:
                continue
            if isinstance(result, dict) and result.get("pid"):
                value["worker_pids"]["generate"] = result["pid"]
        assert "generate" in value["worker_pids"], "Generation worker PID evidence missing"
    candidate = value["fault_injection"]["candidate_id"]
    async with API() as api:
        await api.call(
            "POST",
            f"/v1/growth-runs/{value['run_id']}/reviews",
            role="reviewer",
            body={
                "decision": "request_changes",
                "selected_candidate_id": candidate,
                "change_request": (
                    "请在开头补充“虚构规格演示”，准确引用冻结规格。"
                    "不要加入个人使用体验、效率或防水承诺，正文保持简短。"
                ),
            },
            key="live-p0-request-changes-20261016",
        )
    status = await spawn_worker(value, "changes", 3)
    value["human_change_status"] = status
    assert status == "waiting_human", "Requested change did not return to review"
    from smart_growth_agent.db.models import ComplianceReport, ScoreReport

    async with SessionFactory() as session:
        row = await session.get(ContentCandidate, uuid.UUID(candidate))
        version = await session.scalar(
            select(ContentVersion).where(
                ContentVersion.candidate_id == row.id, ContentVersion.version == row.current_version
            )
        )
        compliance = await session.scalar(
            select(ComplianceReport).where(ComplianceReport.content_version_id == version.id)
        )
        score = await session.scalar(
            select(ScoreReport).where(ScoreReport.content_version_id == version.id)
        )
    value["human_revision"] = {
        "version_id": str(version.id),
        "version": version.version,
        "payload": version.payload,
        "score": float(score.total_score) if score else None,
    }
    value["checks"]["human_change_rechecked_and_rescored"] = (
        version.version == 4
        and compliance is not None
        and score is not None
        and not compliance.has_blockers
        and compliance.semantic_pass
    )
    assert value["checks"]["human_change_rechecked_and_rescored"]
    async with API() as api:
        await api.call(
            "POST",
            f"/v1/growth-runs/{value['run_id']}/reviews",
            role="reviewer",
            body={"decision": "approved", "selected_candidate_id": candidate},
            key="live-p0-final-approval-20261016",
        )
    status = await spawn_worker(value, "approve", 0)
    value["final_status"] = status
    value["checks"]["approval_resumed_in_fresh_worker"] = (
        status == "ready_for_manual_publish" and len(set(value["worker_pids"].values())) == 3
    )
    assert value["checks"]["approval_resumed_in_fresh_worker"]
    value["reviewer_actions"] = "scripted reviewer-role API operations, not human assessment"
    value["pass"] = all(value["checks"].values())
    save(value)


async def execute_stage(stage):
    if read(CAMPAIGN / "authorization.json").get("closed"):
        raise SystemExit("Campaign is closed; no further model calls are allowed.")
    value = report()
    before = len(ledger()["calls"])
    try:
        if stage.startswith("worker-"):
            result = await worker(value)
            print(json.dumps(result, ensure_ascii=False))
            if result["error"]:
                raise RuntimeError("Worker recorded a failure")
            return
        assert value["stages"].get(stage, {}).get("status") != "passed", (
            "Stage already passed; no replay"
        )
        function = {
            "imports": imports,
            "gates": gates,
            "generate": generate,
            "inject": inject,
            "human": human,
        }.get(stage)
        if function is None:
            raise RuntimeError("Stage implementation not yet installed")
        await function(value)
        value["stages"][stage] = {"status": "passed", "requests": len(ledger()["calls"]) - before}
    except Exception as exc:
        if not stage.startswith("worker-"):
            value["stages"][stage] = {
                "status": "failed",
                "requests": len(ledger()["calls"]) - before,
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            save(value)
            target = CAMPAIGN / f"failure-{stage}-{datetime.now(UTC).strftime('%H%M%S')}.json"
            target.write_bytes(REPORT.read_bytes())
        print(
            f"Stage {stage} stopped: {type(exc).__name__}; sanitized report retained.", flush=True
        )
        raise SystemExit(1) from None
    finally:
        if not stage.startswith("worker-"):
            save(value)
        await engine.dispose()
    print(
        json.dumps(
            {
                "stage": stage,
                "status": "passed",
                "new_requests": value["new_requests"],
                "remaining": 61 - len(ledger()["calls"]),
            }
        ),
        flush=True,
    )
