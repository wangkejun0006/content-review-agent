"""Bounded live test through the original HTTP API and fresh worker processes."""

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def worker_once(label):
    command = [
        sys.executable,
        "scripts/local_runtime.py",
        "worker",
        "--mode",
        "real",
        "--allow-model-calls",
        "--max-calls",
        os.environ.get("SMART_GROWTH_LLM_MAX_CALLS", "24"),
        "--once",
    ]
    process = await asyncio.create_subprocess_exec(
        *command, cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await process.communicate()
    text = output.decode(errors="replace")
    # Redact before any output reaches a log file.
    values = [
        os.environ.get("SMART_GROWTH_OPENAI_API_KEY", ""),
        os.environ.get("SMART_GROWTH_JWT_SECRET", ""),
        os.environ.get("SMART_GROWTH_DATABASE_URL", ""),
    ]
    for value in values:
        if value:
            text = text.replace(value, "[REDACTED]")
    (ROOT / ".runtime" / f"e2e-worker-{label}.log").write_text(text)
    if process.returncode:
        raise RuntimeError("worker_process_failed_" + label)


async def run_e2e():
    if os.environ.get("SMART_GROWTH_LLM_MODE") != "openai_compatible":
        raise RuntimeError("live_e2e_requires_explicit_real_mode")
    state = json.loads((ROOT / ".runtime/demo-state.json").read_text())
    report = {
        "evidence_type": "live_model_with_fictional_business_data",
        "model": "deepseek-flash",
        "started_at": datetime.now(UTC).isoformat(),
        "request_cap": int(os.environ.get("SMART_GROWTH_LLM_MAX_CALLS", "24")),
        "external_publication": False,
    }
    started = time.monotonic()
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8765", timeout=30, trust_env=False
    ) as client:

        async def request(method, path, body=None, key=None, token=None):
            headers = {}
            if key:
                headers["Idempotency-Key"] = key
            if token:
                headers["Authorization"] = "Bearer " + token
            response = await client.request(method, path, json=body, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError(f"local_api_{response.status_code}_{path.split('/')[2]}")
            return response.json() if response.content else None

        async def login(role):
            return (await request("POST", "/v1/auth/demo-session", {"role": role}))["access_token"]

        editor, reviewer = await login("editor"), await login("reviewer")
        run = await request(
            "POST",
            "/v1/growth-runs",
            {"brief_id": state["brief_id"]},
            key="paper-orbit-live-e2e-004",
            token=editor,
        )
        run_id = run["id"]
        report["run_id"] = run_id
        print(
            "Live validation: processing the original generation/compliance/scoring graph.",
            flush=True,
        )
        if run["status"] == "queued":
            await worker_once("generate-" + run_id[:8])
        run = await request("GET", f"/v1/growth-runs/{run_id}", token=editor)
        report["generation_status"] = run["status"]
        if run["status"] != "waiting_human":
            report["failure_stage"] = "generation"
            report["run_error"] = run.get("error")
        else:
            candidates = await request("GET", f"/v1/growth-runs/{run_id}/candidates", token=editor)
            compliance = await request(
                "GET", f"/v1/growth-runs/{run_id}/compliance-reports", token=editor
            )
            scores = await request("GET", f"/v1/growth-runs/{run_id}/score-reports", token=editor)
            report["candidate_count"] = len(candidates)
            report["compliance_report_count"] = len(compliance)
            report["score_report_count"] = len(scores)
            clean = {r["content_version_id"] for r in compliance if not r["has_blockers"]}
            safe = [c for c in candidates if c["content_version_id"] in clean]
            if not safe:
                raise RuntimeError("no_candidate_passed_compliance")
            selected = next(
                (c for c in safe if c["id"] == run["recommended_candidate_id"]), safe[0]
            )
            # Exercise role enforcement without allowing an editor to review.
            denied = await client.post(
                f"/v1/growth-runs/{run_id}/reviews",
                headers={
                    "Authorization": "Bearer " + editor,
                    "Idempotency-Key": "denied-editor-review",
                },
                json={"decision": "approved", "selected_candidate_id": selected["id"]},
            )
            report["editor_review_denied"] = denied.status_code == 403
            await request(
                "POST",
                f"/v1/growth-runs/{run_id}/reviews",
                {"decision": "approved", "selected_candidate_id": selected["id"]},
                key="paper-orbit-live-review-004",
                token=reviewer,
            )
            # A fresh OS process reopens PostgreSQL checkpoints, rather than in-memory state.
            await worker_once("resume-" + run_id[:8])
            approved = await request("GET", f"/v1/growth-runs/{run_id}", token=editor)
            report["review_resume_status"] = approved["status"]
            report["separate_worker_process_for_resume"] = True
            if approved["status"] == "ready_for_manual_publish":
                publication = await request(
                    "POST",
                    "/v1/publications",
                    {
                        "content_version_id": selected["content_version_id"],
                        "platform": "xhs",
                        "platform_content_id": "fictional-live-e2e-004",
                        "url": "https://example.com/fictional-publication",
                        "published_at": "2026-10-15T10:00:00Z",
                    },
                    token=editor,
                )
                await request(
                    "POST",
                    f"/v1/publications/{publication['id']}/metric-snapshots",
                    {
                        "captured_at": "2026-10-15T11:00:00Z",
                        "impressions": 120,
                        "views": 60,
                        "likes": 4,
                        "collections": 3,
                        "comments": 1,
                    },
                    token=editor,
                )
                feedback = await request(
                    "POST",
                    "/v1/feedback-runs",
                    {"publication_ids": [publication["id"]]},
                    key="paper-orbit-live-feedback-004",
                    token=editor,
                )
                await worker_once("feedback-" + run_id[:8])
                feedback = await request("GET", f"/v1/feedback-runs/{feedback['id']}", token=editor)
                report["feedback_status"] = feedback["status"]
                report["publication_record"] = "fictional_local_record_only"
            report["candidate_titles"] = [c["payload"]["recommended_title"] for c in candidates]
    budget_path = ROOT / ".runtime/live-budget.json"
    budget = json.loads(budget_path.read_text()) if budget_path.exists() else {"calls": []}
    report["http_requests"] = len(budget["calls"])
    report["input_tokens"] = sum(c.get("prompt_tokens", 0) for c in budget["calls"])
    report["output_tokens"] = sum(c.get("completion_tokens", 0) for c in budget["calls"])
    report["returned_models"] = sorted(
        {c["returned_model"] for c in budget["calls"] if c.get("returned_model")}
    )
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["pass"] = (
        report.get("candidate_count") == 3
        and report.get("editor_review_denied")
        and report.get("review_resume_status") == "ready_for_manual_publish"
        and report.get("feedback_status") == "succeeded"
    )
    report["limitations"] = [
        "Single fictional brief; not an evaluation of general content quality.",
        "Publication and metrics are fabricated local records.",
        "No real users, business documents or external publication were used.",
        "Token counts are provider-reported; not a verified invoice.",
    ]
    output = ROOT / "reports/live-e2e.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report
