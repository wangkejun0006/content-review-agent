"""Fresh browser task -> rework -> approval -> fictional registration -> feedback."""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from local_runtime import ROOT, configure
from playwright.sync_api import expect, sync_playwright

FEEDBACK = "请补充虚构演示标识，并说明资料不足时需补充证据。"


def run(args, report):
    configure(args.instance, args.port, args.db_port)
    base = "http://127.0.0.1:" + str(args.port)
    marker = "fictional-browser-" + uuid.uuid4().hex[:10]
    errors, http_errors, blocked = [], [], []

    def worker(label):
        result = subprocess.run(
            [
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
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
        )
        text = result.stdout + result.stderr
        for key in ["SMART_GROWTH_DATABASE_URL", "SMART_GROWTH_JWT_SECRET"]:
            if os.environ.get(key):
                text = text.replace(os.environ[key], "[REDACTED]")
        (args.output / (label + "-worker.log")).write_text(text)
        if result.returncode:
            raise RuntimeError("worker_failed:" + label)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        def page_for(role):
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()

            def network(route):
                if urlsplit(route.request.url).hostname not in {"localhost", "127.0.0.1"}:
                    blocked.append(urlsplit(route.request.url).hostname)
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", network)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "response",
                lambda response: (
                    http_errors.append(
                        {"status": response.status, "path": urlsplit(response.url).path}
                    )
                    if response.status >= 400
                    else None
                ),
            )
            page.goto(base + "/login")
            page.get_by_role("button", name="以" + role + "进入演示", exact=True).click()
            page.wait_for_url(base + "/")
            return page

        editor = page_for("编辑")
        editor.goto(base + "/briefs")
        editor.get_by_role("button", name="新建 Brief", exact=True).click()
        for label, value in [
            ("任务名称", marker),
            ("内容目标", "介绍虚构文具的纸笔记录场景，不承诺效率和效果。"),
            ("希望用户记住的一句话", "点阵布局用于纸笔记录。"),
            ("核心使用场景", "书桌记录待办"),
            ("绝对不要提", "未提供的产品参数和效果承诺"),
        ]:
            editor.get_by_label(label, exact=True).fill(value)
        editor.get_by_label(re.compile("支持方案策略")).select_option("organic_only")
        editor.get_by_role("button", name="保存 Brief", exact=True).click()
        with editor.expect_response(
            lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/v1/growth-runs"
        ) as response:
            editor.get_by_role("button", name="立即启动任务", exact=True).click()
        assert response.value.status == 202
        run_id = response.value.json()["id"]
        report["run_id"] = run_id
        editor.wait_for_url(base + "/runs/" + run_id)
        worker("generation")
        editor.reload()
        expect(editor.get_by_text("等待 Reviewer 操作", exact=True)).to_be_visible(timeout=20000)
        expect(editor.get_by_role("button", name="批准选中稿", exact=True)).to_have_count(0)
        reviewer = page_for("审核员")
        reviewer.goto(base + "/runs/" + run_id)
        expect(reviewer.get_by_role("button", name="要求修改", exact=True)).to_be_visible(
            timeout=20000
        )
        reviewer.screenshot(path=str(args.output / "before-rework.png"), full_page=True)
        reviewer.get_by_role("button", name="要求修改", exact=True).click()
        reviewer.get_by_label("定向修改要求", exact=True).fill(FEEDBACK)
        with reviewer.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/reviews")
        ) as response:
            reviewer.get_by_role("button", name="提交修改要求", exact=True).click()
        assert response.value.status == 202
        worker("revision")
        reviewer.reload()
        expect(reviewer.get_by_text(re.compile("资料不足时暂停无依据结论"))).to_be_visible(
            timeout=20000
        )
        reviewer.screenshot(path=str(args.output / "after-rework.png"), full_page=True)
        with reviewer.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/reviews")
        ) as response:
            reviewer.get_by_role("button", name="批准选中稿", exact=True).click()
        assert response.value.status == 202
        worker("approval")
        reviewer.reload()
        expect(reviewer.get_by_text("内容已完成审核", exact=True)).to_be_visible(timeout=20000)
        editor.goto(base + "/publications")
        editor.get_by_role("button", name="登记 Publication", exact=True).click()
        editor.get_by_label("小红书笔记 ID", exact=True).fill(marker)
        editor.get_by_label("笔记 URL", exact=True).fill(
            "https://example.com/fictional-publication"
        )
        with editor.expect_response(
            lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/v1/publications"
        ) as response:
            editor.get_by_role("button", name="确认登记", exact=True).click()
        assert response.value.status == 201
        card = editor.locator(".glass-panel").filter(
            has=editor.get_by_text("笔记 " + marker, exact=True)
        )
        card.get_by_role("button", name="录入指标", exact=True).click()
        for label, value in [("阅读", "60"), ("点赞", "4"), ("收藏", "3"), ("评论", "1")]:
            editor.get_by_label(label, exact=True).fill(value)
        with editor.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/metric-snapshots")
        ) as response:
            editor.get_by_role("button", name="保存指标快照", exact=True).click()
        assert response.value.status == 201
        editor.goto(base + "/feedback")
        editor.get_by_role("button", name="Feedback 分析", exact=True).click()
        editor.locator("label").filter(has_text=marker).get_by_role("checkbox").check()
        with editor.expect_response(
            lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/v1/feedback-runs"
        ) as response:
            editor.get_by_role("button", name="开始分析", exact=True).click()
        assert response.value.status == 202
        feedback_id = response.value.json()["id"]
        worker("feedback")
        editor.reload()
        heading = editor.get_by_text("Feedback " + feedback_id[:8], exact=True)
        expect(heading).to_be_visible(timeout=20000)
        feedback_card = editor.locator(".glass-panel").filter(has=heading)
        expect(
            feedback_card.get_by_text(
                "策略建议先以草稿保存，Reviewer 激活后才影响后续内容策略。", exact=True
            )
        ).to_be_visible(timeout=20000)
        editor.screenshot(path=str(args.output / "feedback.png"), full_page=True)
        editor.set_viewport_size({"width": 390, "height": 844})
        editor.goto(base + "/products")
        editor.wait_for_load_state("networkidle")
        overflow = editor.evaluate("document.documentElement.scrollWidth > innerWidth")
        editor.screenshot(path=str(args.output / "mobile-products.png"), full_page=True)
        report.update(
            {
                "page_errors": errors,
                "http_errors": http_errors,
                "blocked_external_requests": blocked,
                "mobile_overflow": overflow,
                "feedback_id": feedback_id,
                "checks": [
                    "UI-created brief and run",
                    "editor has no review action",
                    "substantive fixture rework",
                    "reviewer approval and fresh worker resume",
                    "UI fictional registration and metrics",
                    "UI feedback",
                ],
                "pass": not errors and not http_errors and not blocked and not overflow,
            }
        )
        browser.close()
        assert report["pass"], report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", default="demo")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--db-port", type=int, default=55433)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output directory required")
    args.output.mkdir(parents=True)
    report = {
        "evidence_type": "automated_browser_offline_fixtures",
        "real_model_calls": 0,
        "external_publication": False,
        "pass": False,
    }
    try:
        run(args, report)
    except Exception as exc:
        report["failure_type"] = type(exc).__name__
        raise
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
