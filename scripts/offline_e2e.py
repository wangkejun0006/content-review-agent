"""Fresh local HTTP workflow and new Worker processes, always fake and no provider."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from local_runtime import ROOT, configure

FEEDBACK = "请补充虚构演示标识，并说明资料不足时需补充证据。"


async def run(args, report):
    _, _, _, state_dir = configure(args.instance, args.port, args.db_port)
    state = json.loads((state_dir / "demo-state.json").read_text())
    prefix = "offline-" + uuid.uuid4().hex
    base = "http://127.0.0.1:" + str(args.port)

    async def worker(label):
        command = [
            sys.executable,
            "scripts/local_runtime.py",
            "worker",
            "--instance",
            args.instance,
            "--port",
            str(args.port),
            "--db-port",
            str(args.db_port),
            "--once",
        ]
        process = await asyncio.create_subprocess_exec(
            *command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        output, _ = await process.communicate()
        text = output.decode(errors="replace")
        for name in ["SMART_GROWTH_DATABASE_URL", "SMART_GROWTH_JWT_SECRET"]:
            if os.environ.get(name):
                text = text.replace(os.environ[name], "[REDACTED]")
        (args.output.parent / (label + "-worker.log")).write_text(text)
        if process.returncode:
            raise RuntimeError("worker_process_failed:" + label)

    async with httpx.AsyncClient(base_url=base, timeout=30, trust_env=False) as client:

        async def request(method, path, body=None, token=None, key=None, expected=200):
            headers = {"Authorization": "Bearer " + token} if token else {}
            if key:
                headers["Idempotency-Key"] = prefix + "-" + key
            response = await client.request(method, path, json=body, headers=headers)
            if response.status_code != expected:
                raise RuntimeError(f"api_status_{response.status_code}:{path}")
            return response.json() if response.content else None

        editor = (await request("POST", "/v1/auth/demo-session", {"role": "editor"}))[
            "access_token"
        ]
        reviewer = (await request("POST", "/v1/auth/demo-session", {"role": "reviewer"}))[
            "access_token"
        ]
        context = await request("GET", "/v1/auth/demo-context")
        assert context["mode"] == "fake" and context["used_calls"] == 0
        run = await request(
            "POST", "/v1/growth-runs", {"brief_id": state["brief_id"]}, editor, "create", 202
        )
        run_id = run["id"]
        report["run_id"] = run_id
        await worker("generation")
        run = await request("GET", f"/v1/growth-runs/{run_id}", token=editor)
        assert run["status"] == "waiting_human", run.get("error")
        candidates = await request("GET", f"/v1/growth-runs/{run_id}/candidates", token=editor)
        checks = await request("GET", f"/v1/growth-runs/{run_id}/compliance-reports", token=editor)
        clean = {
            x["content_version_id"] for x in checks if not x["has_blockers"] and x["semantic_pass"]
        }
        selected = next(c for c in candidates if c["content_version_id"] in clean)
        report["candidate_count"] = len(candidates)
        report["before"] = selected
        review_path = f"/v1/growth-runs/{run_id}/reviews"
        await request(
            "POST",
            review_path,
            {"decision": "approved", "selected_candidate_id": selected["id"]},
            editor,
            "denied",
            403,
        )
        report["editor_review_denied"] = True
        await request(
            "POST",
            review_path,
            {
                "decision": "request_changes",
                "selected_candidate_id": selected["id"],
                "change_request": FEEDBACK,
            },
            reviewer,
            "changes",
            202,
        )
        await worker("revision")
        run = await request("GET", f"/v1/growth-runs/{run_id}", token=editor)
        assert run["status"] == "waiting_human", run.get("error")
        revised = await request("GET", f"/v1/growth-runs/{run_id}/candidates", token=editor)
        selected = next(c for c in revised if c["id"] == selected["id"])
        report["after"] = selected
        assert selected["current_version"] > report["before"]["current_version"]
        assert selected["payload"]["body"] != report["before"]["payload"]["body"]
        assert "资料不足时暂停无依据结论" in selected["payload"]["body"]
        await request(
            "POST",
            review_path,
            {"decision": "approved", "selected_candidate_id": selected["id"]},
            reviewer,
            "approve",
            202,
        )
        await worker("approval")
        run = await request("GET", f"/v1/growth-runs/{run_id}", token=editor)
        assert run["status"] == "ready_for_manual_publish", run.get("error")
        publication = await request(
            "POST",
            "/v1/publications",
            {
                "content_version_id": selected["content_version_id"],
                "platform": "xhs",
                "platform_content_id": prefix,
                "url": "https://example.com/fictional-publication",
                "published_at": datetime.now(UTC).isoformat(),
            },
            editor,
            expected=201,
        )
        await request(
            "POST",
            f"/v1/publications/{publication['id']}/metric-snapshots",
            {
                "captured_at": datetime.now(UTC).isoformat(),
                "impressions": 120,
                "views": 60,
                "likes": 4,
                "collections": 3,
                "comments": 1,
            },
            editor,
            expected=201,
        )
        feedback = await request(
            "POST",
            "/v1/feedback-runs",
            {"publication_ids": [publication["id"]]},
            editor,
            "feedback",
            202,
        )
        await worker("feedback")
        feedback = await request("GET", f"/v1/feedback-runs/{feedback['id']}", token=editor)
        assert feedback["status"] == "succeeded", feedback.get("error")
        report.update(
            {
                "final_status": run["status"],
                "feedback_status": feedback["status"],
                "separate_worker_processes": 4,
                "substantive_fixture_rework": True,
                "pass": True,
            }
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", default="demo")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--db-port", type=int, default=55433)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.parent.exists():
        parser.error("use a new output directory and report path")
    args.output.parent.mkdir(parents=True)
    report = {
        "evidence_type": "offline_fixture_scripted_roles",
        "real_model_calls": 0,
        "external_publication": False,
        "pass": False,
    }
    try:
        asyncio.run(run(args, report))
    except Exception as exc:
        # No exception values: transport errors may contain credentials.
        report["failure_type"] = type(exc).__name__
        raise
    finally:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
