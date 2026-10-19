from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class TailscaleError(RuntimeError):
    """An actionable local Tailscale configuration error."""


@dataclass(frozen=True)
class TailscaleStatus:
    installed: bool
    backend_state: str | None = None
    dns_name: str | None = None

    @property
    def ready(self) -> bool:
        return self.installed and self.backend_state == "Running" and bool(self.dns_name)

    @property
    def url(self) -> str | None:
        return f"https://{self.dns_name.rstrip('.')}" if self.dns_name else None


@dataclass(frozen=True)
class TailscaleServeStatus:
    enabled: bool
    target: str | None = None
    error: str | None = None


def inspect_tailscale() -> TailscaleStatus:
    executable = shutil.which("tailscale")
    if executable is None:
        return TailscaleStatus(installed=False)
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "status", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return TailscaleStatus(installed=True, backend_state="Unavailable")
    if result.returncode != 0:
        return TailscaleStatus(installed=True, backend_state="Unavailable")
    try:
        payload: dict[str, Any] = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TailscaleError("无法解析 tailscale status --json 的输出。") from exc
    self_status = payload.get("Self") if isinstance(payload.get("Self"), dict) else {}
    dns_name = self_status.get("DNSName")
    return TailscaleStatus(
        installed=True,
        backend_state=str(payload.get("BackendState") or "Unknown"),
        dns_name=str(dns_name) if dns_name else None,
    )


def inspect_tailscale_serve() -> TailscaleServeStatus:
    executable = shutil.which("tailscale")
    if executable is None:
        return TailscaleServeStatus(enabled=False, error="tailscale not installed")
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "serve", "status", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return TailscaleServeStatus(enabled=False, error=str(exc))
    if result.returncode != 0:
        return TailscaleServeStatus(
            enabled=False,
            error=result.stderr.strip() or "serve status unavailable",
        )
    try:
        payload: dict[str, Any] = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        return TailscaleServeStatus(enabled=False, error=str(exc))
    web = payload.get("Web")
    if not isinstance(web, dict):
        return TailscaleServeStatus(enabled=False)
    for site in web.values():
        handlers = site.get("Handlers") if isinstance(site, dict) else None
        if not isinstance(handlers, dict):
            continue
        for handler in handlers.values():
            target = handler.get("Proxy") if isinstance(handler, dict) else None
            if target:
                return TailscaleServeStatus(enabled=True, target=str(target))
    return TailscaleServeStatus(enabled=False)


def build_frontend(project_root: Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise TailscaleError("找不到 npm，无法生成生产前端。")
    frontend_directory = project_root / "frontend"
    if not (frontend_directory / "package.json").is_file():
        raise TailscaleError(
            f"项目根目录无效：{project_root}；未找到 frontend/package.json。"
        )
    subprocess.run(  # noqa: S603
        [npm, "run", "build"],
        cwd=frontend_directory,
        check=True,
    )


def _privileged_tailscale_command(*arguments: str) -> None:
    tailscale = shutil.which("tailscale")
    if tailscale is None:
        raise TailscaleError(
            "尚未安装 Tailscale。请先按 README 的“Tailscale 私有共享”步骤安装。"
        )
    try:
        # Current Tailscale clients normally grant the logged-in local operator
        # access to `serve`; avoiding unconditional sudo also makes share-start
        # usable from IDE terminals and automation. A restricted host receives an
        # explicit manual fallback instead of a hidden password prompt.
        subprocess.run([tailscale, *arguments], check=True, timeout=15)  # noqa: S603
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        command = "sudo tailscale " + " ".join(arguments)
        raise TailscaleError(
            "当前用户无权修改 Tailscale Serve。请先一次性执行 "
            "sudo tailscale set --operator=$USER 后重试；"
            f"也可以临时手动执行：{command}"
        ) from exc


def start_tailscale_serve(target: str = "http://127.0.0.1:8000") -> TailscaleStatus:
    status = inspect_tailscale()
    if not status.installed:
        raise TailscaleError(
            "尚未安装 Tailscale。请先按 README 的“Tailscale 私有共享”步骤安装。"
        )
    if status.backend_state != "Running":
        raise TailscaleError("Tailscale 尚未登录或未运行，请先执行 sudo tailscale up。")
    _privileged_tailscale_command("serve", "--bg", target)
    refreshed = inspect_tailscale()
    if not refreshed.ready:
        raise TailscaleError("Serve 已配置，但暂时未取得 MagicDNS HTTPS 地址。")
    return refreshed


def stop_tailscale_serve() -> None:
    _privileged_tailscale_command("serve", "--https=443", "off")
