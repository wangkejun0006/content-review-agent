"""Release boundaries and offline fixture semantics, no Docker/model network."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_instance_identity_is_bound_to_checkout(tmp_path, monkeypatch):
    module = load("local_runtime")
    first = module.identity("demo")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert module.identity("demo") != first
    with pytest.raises(ValueError):
        module.identity("../old")


def test_config_rejects_port_drift_and_orphan_volume(tmp_path, monkeypatch):
    module = load("local_runtime")
    monkeypatch.setenv("PAPER_ORBIT_PRIVATE_HOME", str(tmp_path))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    module.load_private("new", 8766, 55433)
    with pytest.raises(RuntimeError, match="configuration_mismatch"):
        module.load_private("new", 8767, 55433)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError, match="volume_exists_without"):
        module.load_private("orphan", 8766, 55433)


def test_new_private_config_has_private_permissions(tmp_path, monkeypatch):
    module = load("local_runtime")
    monkeypatch.setenv("PAPER_ORBIT_PRIVATE_HOME", str(tmp_path))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    directory, _ = module.load_private("new", 8766, 55433)
    assert (directory / "session.json").stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700


def test_export_excludes_runtime_and_rejects_symlinks(tmp_path):
    module = load("export_release")
    (tmp_path / "release").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src/.runtime").mkdir()
    (tmp_path / "src/.runtime/db.sqlite").write_text("private")
    (tmp_path / "src/good.py").write_text("pass")
    config = {
        "files": [],
        "directories": ["src"],
        "excluded_parts": [".runtime"],
        "excluded_suffixes": [],
        "excluded_names": [],
    }
    (tmp_path / "release/manifest.json").write_text(json.dumps(config))
    assert [p.name for p in module.selected_files(tmp_path)] == ["good.py"]
    (tmp_path / "src/link.py").symlink_to(tmp_path / "src/good.py")
    with pytest.raises(ValueError, match="symlink"):
        module.selected_files(tmp_path)


def test_offline_guard_stops_sync_and_async_before_http():
    code = """
import asyncio, httpx
from smart_growth_agent.offline_boundary import install
install()
try:
    httpx.get('https://example.com')
except RuntimeError as e:
    assert str(e)=='offline_external_http_forbidden'
else: raise AssertionError('sync escaped')
async def check():
    async with httpx.AsyncClient() as c:
        try: await c.get('https://example.com')
        except RuntimeError as e: assert str(e)=='offline_external_http_forbidden'
        else: raise AssertionError('async escaped')
asyncio.run(check())
from smart_growth_agent.llm.openai_compatible import OpenAICompatibleGateway
async def reject_loopback_model():
    gateway = OpenAICompatibleGateway.__new__(OpenAICompatibleGateway)
    try: await gateway._request_and_parse()
    except RuntimeError as e: assert str(e)=='offline_model_transport_forbidden'
    else: raise AssertionError('provider transport escaped')
asyncio.run(reject_loopback_model())
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_fixed_rework_does_not_invent_general_instruction_support():
    from smart_growth_agent.llm.fake import DevelopmentFakeLLMGateway

    inputs = {
        "creative_route": {
            "route_key": "test",
            "angle_key": "a",
            "angle_name": "角度",
            "visual_direction": "近景",
            "scene": "书桌",
        },
        "product_context": {},
    }
    original = DevelopmentFakeLLMGateway._writer_payload(inputs)
    inputs["revision_instructions"] = "请补充虚构演示标识，并说明资料不足时需补充证据。"
    revised = DevelopmentFakeLLMGateway._writer_payload(inputs)
    assert revised["body"] != original["body"]
    assert revised["source_revision_ids"] == original["source_revision_ids"]
    inputs["revision_instructions"] = "不要补充虚构演示标识，资料不足时也无需补充证据。"
    assert DevelopmentFakeLLMGateway._writer_payload(inputs) == original


def test_offline_instance_discards_ambient_provider_and_old_budget(tmp_path, monkeypatch):
    import os

    from smart_growth_agent import offline_boundary

    module = load("local_runtime")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr(offline_boundary, "install", lambda: None)
    monkeypatch.setattr(
        module,
        "load_private",
        lambda *args: (tmp_path, {"db_password": "new-demo-only", "jwt": "new-demo-only"}),
    )
    os.environ["SMART_GROWTH_OPENAI_API_KEY"] = "ambient-must-not-be-used"
    os.environ["SMART_GROWTH_LLM_BUDGET_PATH"] = "/old/campaign/must-not-open.json"
    module.configure("new", 8766, 55433)
    assert "SMART_GROWTH_OPENAI_API_KEY" not in os.environ
    assert os.environ["SMART_GROWTH_LLM_MODE"] == "fake"
    assert os.environ["SMART_GROWTH_LLM_BUDGET_PATH"] == str(
        tmp_path / ".runtime/instances/new/not-authorized-budget.json"
    )
    assert not Path(os.environ["SMART_GROWTH_LLM_BUDGET_PATH"]).exists()


def test_offline_launcher_rejects_real_before_configuration():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/local_runtime.py",
            "serve",
            "--mode",
            "real",
            "--allow-model-calls",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_rehearsal_refuses_existing_record(tmp_path):
    report = tmp_path / "report.json"
    report.write_text("old-failed-record")
    result = subprocess.run(
        [sys.executable, "scripts/offline_demo.py", "--output", str(report)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert report.read_text() == "old-failed-record"


def test_database_readiness_waits_for_authenticated_mapped_tcp(monkeypatch):
    import psycopg

    module = load("local_runtime")
    calls = []

    def connect(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise psycopg.OperationalError("initializing")
        return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    module.wait_for_database({"db_port": 55433, "db_password": "fake-test-only"})
    assert len(calls) == 3
    assert all(c["host"] == "127.0.0.1" and c["port"] == 55433 for c in calls)
