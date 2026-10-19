from __future__ import annotations

from pathlib import Path

from smart_growth_agent.cli import build_parser
from smart_growth_agent.runtime import _autostart_unit_contents, _rotate_log


def test_runtime_log_rotation_keeps_recent_history(tmp_path) -> None:
    log = tmp_path / "api.log"
    log.write_text("first", encoding="utf-8")
    _rotate_log(log, keep=2)
    assert not log.exists()
    assert (tmp_path / "api.log.1").read_text(encoding="utf-8") == "first"

    log.write_text("second", encoding="utf-8")
    _rotate_log(log, keep=2)
    assert (tmp_path / "api.log.1").read_text(encoding="utf-8") == "second"
    assert (tmp_path / "api.log.2").read_text(encoding="utf-8") == "first"


def test_autostart_units_restart_crashed_services(tmp_path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    monkeypatch.setattr(
        "smart_growth_agent.runtime._executable",
        lambda name: f"/test/bin/{name}",
    )
    api, worker = _autostart_unit_contents(tmp_path)
    assert "ExecStartPre=\"/test/bin/alembic\" upgrade head" in api
    assert "ExecStart=\"/test/bin/smart-growth-api\"" in api
    assert "ExecStart=\"/test/bin/smart-growth-worker\"" in worker
    assert "Restart=on-failure" in api and "Restart=on-failure" in worker
    assert "StandardError=append:" in api and "StandardError=append:" in worker


def test_runtime_administration_commands_use_project_root() -> None:
    parser = build_parser()
    for command in (
        "runtime-restart",
        "runtime-status",
        "runtime-logs",
        "runtime-stop",
        "autostart-install",
        "autostart-remove",
    ):
        args = parser.parse_args([command])
        assert args.project_root == Path(__file__).resolve().parents[1]
