from __future__ import annotations

import argparse
from types import SimpleNamespace

from smart_growth_agent.cli import build_parser, configure_managed_llm
from smart_growth_agent.runtime import _child_environment


def test_configure_managed_llm_creates_and_preserves_env(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CUSTOM_VALUE=keep\nSMART_GROWTH_LLM_MODE=fake\n", encoding="utf-8")
    configure_managed_llm(argparse.Namespace(env_file=env_file, restart=False))
    first = env_file.read_text(encoding="utf-8")
    assert "CUSTOM_VALUE=keep" in first
    assert "SMART_GROWTH_LLM_MODE=managed" in first
    assert "SMART_GROWTH_JWT_SECRET=" in first
    assert "SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY=" in first

    configure_managed_llm(argparse.Namespace(env_file=env_file, restart=False))
    assert env_file.read_text(encoding="utf-8") == first
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"


def test_configure_managed_llm_replaces_example_placeholders(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SMART_GROWTH_JWT_SECRET=replace-with-at-least-32-random-characters\n"
        "SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY="
        "replace-with-a-different-32-character-random-secret\n",
        encoding="utf-8",
    )
    configure_managed_llm(argparse.Namespace(env_file=env_file, restart=False))
    configured = env_file.read_text(encoding="utf-8")
    assert "replace-with-" not in configured
    assert "SMART_GROWTH_LLM_MODE=managed" in configured


def test_configure_managed_llm_restarts_runtime_by_default(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    captured: list[object] = []

    def fake_restart(project_root):
        captured.append(project_root)
        return SimpleNamespace(
            api_pid=101,
            worker_pid=102,
            runtime_directory=project_root / ".runtime",
        )

    monkeypatch.setattr("smart_growth_agent.cli.restart_runtime", fake_restart)
    args = build_parser().parse_args(["configure-managed-llm", "--env-file", str(env_file)])
    assert args.restart is True
    configure_managed_llm(args)
    assert captured == [tmp_path]


def test_runtime_children_do_not_inherit_managed_settings(monkeypatch) -> None:
    monkeypatch.setenv("SMART_GROWTH_LLM_MODE", "fake")
    monkeypatch.setenv("SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY", "old-key")
    monkeypatch.setenv("SMART_GROWTH_DATABASE_URL", "keep-this-value")
    environment = _child_environment()
    assert "SMART_GROWTH_LLM_MODE" not in environment
    assert "SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY" not in environment
    assert environment["SMART_GROWTH_DATABASE_URL"] == "keep-this-value"
