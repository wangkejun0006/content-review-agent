from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from smart_growth_agent.cli import DEFAULT_PROJECT_ROOT, build_parser, share_start
from smart_growth_agent.sharing import (
    TailscaleError,
    TailscaleServeStatus,
    TailscaleStatus,
    inspect_tailscale,
    inspect_tailscale_serve,
    start_tailscale_serve,
)


def test_inspect_tailscale_reports_missing_binary(monkeypatch) -> None:
    monkeypatch.setattr("smart_growth_agent.sharing.shutil.which", lambda _name: None)
    assert inspect_tailscale() == TailscaleStatus(installed=False)


def test_inspect_tailscale_returns_private_magicdns_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "smart_growth_agent.sharing.shutil.which", lambda _name: "/usr/bin/tailscale"
    )
    monkeypatch.setattr(
        "smart_growth_agent.sharing.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "BackendState": "Running",
                    "Self": {"DNSName": "growth-host.example.ts.net."},
                }
            ),
            stderr="",
        ),
    )
    status = inspect_tailscale()
    assert status.ready is True
    assert status.url == "https://growth-host.example.ts.net"


def test_inspect_tailscale_timeout_is_reported_as_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "smart_growth_agent.sharing.shutil.which", lambda _name: "/usr/bin/tailscale"
    )

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("tailscale", 5)

    monkeypatch.setattr("smart_growth_agent.sharing.subprocess.run", timeout)
    status = inspect_tailscale()
    assert status.installed is True
    assert status.backend_state == "Unavailable"


def test_inspect_tailscale_serve_reports_proxy_target(monkeypatch) -> None:
    monkeypatch.setattr(
        "smart_growth_agent.sharing.shutil.which", lambda _name: "/usr/bin/tailscale"
    )
    monkeypatch.setattr(
        "smart_growth_agent.sharing.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "Web": {
                        "host.example.ts.net:443": {
                            "Handlers": {"/": {"Proxy": "http://127.0.0.1:8000"}}
                        }
                    }
                }
            ),
            stderr="",
        ),
    )
    assert inspect_tailscale_serve() == TailscaleServeStatus(
        enabled=True,
        target="http://127.0.0.1:8000",
    )


def test_start_requires_authenticated_tailscale(monkeypatch) -> None:
    monkeypatch.setattr(
        "smart_growth_agent.sharing.inspect_tailscale",
        lambda: TailscaleStatus(installed=True, backend_state="NeedsLogin"),
    )
    with pytest.raises(TailscaleError, match="tailscale up"):
        start_tailscale_serve()


def test_share_start_defaults_to_build_and_restart() -> None:
    args = build_parser().parse_args(["share-start"])
    assert args.build is True
    assert args.restart is True
    assert args.project_root == DEFAULT_PROJECT_ROOT


def test_share_start_checks_serve_before_build_and_restart(tmp_path, monkeypatch) -> None:
    events: list[str] = []
    ready = TailscaleStatus(
        installed=True,
        backend_state="Running",
        dns_name="growth-host.example.ts.net.",
    )
    monkeypatch.setattr("smart_growth_agent.cli.inspect_tailscale", lambda: ready)
    monkeypatch.setattr(
        "smart_growth_agent.cli.start_tailscale_serve",
        lambda: events.append("serve") or ready,
    )
    monkeypatch.setattr(
        "smart_growth_agent.cli.build_frontend", lambda _root: events.append("build")
    )
    monkeypatch.setattr(
        "smart_growth_agent.cli.restart_runtime",
        lambda _root: events.append("restart")
        or SimpleNamespace(api_pid=1, worker_pid=2),
    )

    share_start(
        SimpleNamespace(project_root=tmp_path, build=True, restart=True)
    )

    assert events == ["serve", "build", "restart"]
