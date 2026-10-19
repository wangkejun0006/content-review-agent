from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RUNTIME_NAMES = ("smart-growth-api", "smart-growth-worker")
MANAGED_ENVIRONMENT_KEYS = (
    "SMART_GROWTH_LLM_MODE",
    "SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY",
    "SMART_GROWTH_JWT_SECRET",
)


@dataclass(frozen=True)
class RuntimeProcesses:
    api_pid: int
    worker_pid: int
    runtime_directory: Path


@dataclass(frozen=True)
class RuntimeInspection:
    api_pids: tuple[int, ...]
    worker_pids: tuple[int, ...]
    health: dict[str, object] | None
    health_error: str | None
    autostart_installed: bool


def _read_cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError):
        return ""


def _project_processes(project_root: Path) -> dict[str, set[int]]:
    processes = {name: set() for name in RUNTIME_NAMES}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        command = _read_cmdline(pid)
        matched = next((name for name in RUNTIME_NAMES if name in command), None)
        if matched is None:
            continue
        try:
            process_root = Path(f"/proc/{pid}/cwd").resolve()
        except (FileNotFoundError, PermissionError):
            continue
        if process_root == project_root:
            processes[matched].add(pid)
    return processes


def _project_process_groups(project_root: Path) -> set[int]:
    groups: set[int] = set()
    own_group = os.getpgrp()
    for pids in _project_processes(project_root).values():
        for pid in pids:
            try:
                process_group = os.getpgid(pid)
            except (ProcessLookupError, PermissionError):
                continue
            if process_group != own_group:
                groups.add(process_group)
    return groups


def _runtime_directory(project_root: Path) -> Path:
    path = project_root / ".runtime"
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _rotate_log(path: Path, keep: int = 5) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    path.with_name(f"{path.name}.{keep}").unlink(missing_ok=True)
    for index in range(keep - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))


def _signal_groups(groups: set[int], signal_number: signal.Signals) -> None:
    for process_group in groups:
        try:
            os.killpg(process_group, signal_number)
        except ProcessLookupError:
            continue


def _alive_groups(groups: set[int]) -> set[int]:
    alive: set[int] = set()
    for process_group in groups:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            continue
        alive.add(process_group)
    return alive


def stop_runtime(project_root: Path) -> None:
    groups = _project_process_groups(project_root)
    if not groups:
        return
    _signal_groups(groups, signal.SIGINT)
    deadline = time.monotonic() + 5
    while groups and time.monotonic() < deadline:
        time.sleep(0.1)
        groups = _alive_groups(groups)
    if groups:
        _signal_groups(groups, signal.SIGTERM)
        deadline = time.monotonic() + 3
        while groups and time.monotonic() < deadline:
            time.sleep(0.1)
            groups = _alive_groups(groups)
    if groups:
        _signal_groups(groups, signal.SIGKILL)


def _executable(name: str) -> str:
    sibling = Path(sys.executable).with_name(name)
    if sibling.is_file():
        return str(sibling)
    discovered = shutil.which(name)
    if discovered is None:
        raise RuntimeError(f"cannot find {name}; run this command through uv")
    return discovered


def _child_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in MANAGED_ENVIRONMENT_KEYS:
        environment.pop(key, None)
    return environment


def _autostart_paths(project_root: Path) -> tuple[Path, Path]:
    unit_directory = Path.home() / ".config" / "systemd" / "user"
    slug = hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:10]
    return (
        unit_directory / f"smart-growth-api-{slug}.service",
        unit_directory / f"smart-growth-worker-{slug}.service",
    )


def autostart_installed(project_root: Path) -> bool:
    return all(path.is_file() for path in _autostart_paths(project_root))


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _autostart_unit_contents(project_root: Path) -> tuple[str, str]:
    project_root = project_root.resolve()
    runtime_directory = _runtime_directory(project_root)
    api_unit, _worker_unit = _autostart_paths(project_root)
    api = f"""[Unit]
Description=Smart Growth API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={_systemd_quote(str(project_root))}
Environment=PYTHONUNBUFFERED=1
ExecStartPre={_systemd_quote(_executable('alembic'))} upgrade head
ExecStart={_systemd_quote(_executable('smart-growth-api'))}
Restart=on-failure
RestartSec=3
StandardOutput=append:{runtime_directory / 'api.log'}
StandardError=append:{runtime_directory / 'api.log'}

[Install]
WantedBy=default.target
"""
    worker = f"""[Unit]
Description=Smart Growth Worker
After=network-online.target {api_unit.name}
Wants=network-online.target
Requires={api_unit.name}

[Service]
Type=simple
WorkingDirectory={_systemd_quote(str(project_root))}
Environment=PYTHONUNBUFFERED=1
ExecStart={_systemd_quote(_executable('smart-growth-worker'))}
Restart=on-failure
RestartSec=3
StandardOutput=append:{runtime_directory / 'worker.log'}
StandardError=append:{runtime_directory / 'worker.log'}

[Install]
WantedBy=default.target
"""
    return api, worker


def install_autostart(project_root: Path) -> tuple[Path, Path]:
    if shutil.which("systemctl") is None:
        raise RuntimeError("systemctl is unavailable; WSL systemd must be enabled first")
    project_root = project_root.resolve()
    if not (project_root / "pyproject.toml").is_file():
        raise RuntimeError(f"invalid project root: {project_root}")
    paths = _autostart_paths(project_root)
    paths[0].parent.mkdir(parents=True, exist_ok=True)
    for path, content in zip(
        paths, _autostart_unit_contents(project_root), strict=True
    ):
        path.write_text(content, encoding="utf-8")
    stop_runtime(project_root)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        ["systemctl", "--user", "enable", "--now", paths[0].name, paths[1].name],
        check=True,
    )
    return paths


def remove_autostart(project_root: Path) -> None:
    paths = _autostart_paths(project_root.resolve())
    subprocess.run(  # noqa: S603
        ["systemctl", "--user", "disable", "--now", *(path.name for path in paths)],
        check=False,
    )
    for path in paths:
        path.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)  # noqa: S603


def stop_runtime_services(project_root: Path) -> None:
    project_root = project_root.resolve()
    if autostart_installed(project_root):
        paths = _autostart_paths(project_root)
        subprocess.run(  # noqa: S603
            ["systemctl", "--user", "stop", paths[1].name, paths[0].name],
            check=True,
        )
        return
    stop_runtime(project_root)


def _systemd_pid(unit: Path) -> int:
    result = subprocess.run(  # noqa: S603
        ["systemctl", "--user", "show", "--property=MainPID", "--value", unit.name],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip() or 0)


def _spawn(name: str, project_root: Path, runtime_directory: Path) -> subprocess.Popen[bytes]:
    log_path = runtime_directory / f"{name.removeprefix('smart-growth-')}.log"
    _rotate_log(log_path)
    log_path.touch(mode=0o600, exist_ok=True)
    log_path.chmod(0o600)
    with log_path.open("wb", buffering=0) as log_file:
        process = subprocess.Popen(  # noqa: S603
            [_executable(name)],
            cwd=project_root,
            env=_child_environment(),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path = runtime_directory / f"{name.removeprefix('smart-growth-')}.pid"
    pid_path.write_text(str(process.pid), encoding="utf-8")
    pid_path.chmod(0o600)
    return process


def upgrade_database(project_root: Path) -> None:
    subprocess.run(  # noqa: S603
        [_executable("alembic"), "upgrade", "head"],
        cwd=project_root,
        env=_child_environment(),
        check=True,
    )


def _wait_for_api_endpoint(
    api: subprocess.Popen[bytes] | None = None,
    timeout_seconds: float = 180,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "API did not become ready"
    while time.monotonic() < deadline:
        if api is not None and api.poll() is not None:
            raise RuntimeError(f"API exited with status {api.returncode}")
        try:
            with urllib.request.urlopen(  # noqa: S310
                "http://127.0.0.1:8000/health/ready", timeout=1
            ) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(last_error)


def _wait_for_api(api: subprocess.Popen[bytes], timeout_seconds: float = 180) -> None:
    _wait_for_api_endpoint(api, timeout_seconds)


def _wait_for_worker(worker: subprocess.Popen[bytes], seconds: float = 3) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if worker.poll() is not None:
            raise RuntimeError(f"Worker exited with status {worker.returncode}")
        time.sleep(0.1)


def _runtime_log_tail(runtime_directory: Path, lines: int = 20) -> str:
    excerpts: list[str] = []
    for name in ("api.log", "worker.log"):
        path = runtime_directory / name
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            continue
        excerpts.append(f"--- {name} ---\n" + "\n".join(content[-lines:]))
    return "\n".join(excerpts)


def runtime_log_tail(project_root: Path, lines: int = 50) -> str:
    return _runtime_log_tail(project_root.resolve() / ".runtime", lines=lines)


def inspect_runtime(project_root: Path) -> RuntimeInspection:
    project_root = project_root.resolve()
    processes = _project_processes(project_root)
    health: dict[str, object] | None = None
    health_error: str | None = None
    try:
        with urllib.request.urlopen(  # noqa: S310
            "http://127.0.0.1:8000/health/ready", timeout=2
        ) as response:
            payload = json.loads(response.read())
            health = payload if isinstance(payload, dict) else None
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        health_error = str(exc)
    return RuntimeInspection(
        api_pids=tuple(sorted(processes["smart-growth-api"])),
        worker_pids=tuple(sorted(processes["smart-growth-worker"])),
        health=health,
        health_error=health_error,
        autostart_installed=autostart_installed(project_root),
    )


def _restart_systemd_runtime(project_root: Path) -> RuntimeProcesses:
    runtime_directory = _runtime_directory(project_root)
    api_unit, worker_unit = _autostart_paths(project_root)
    subprocess.run(  # noqa: S603
        ["systemctl", "--user", "stop", worker_unit.name, api_unit.name], check=True
    )
    for name in ("api.log", "worker.log"):
        _rotate_log(runtime_directory / name)
    subprocess.run(  # noqa: S603
        ["systemctl", "--user", "start", api_unit.name], check=True
    )
    _wait_for_api_endpoint()
    subprocess.run(  # noqa: S603
        ["systemctl", "--user", "start", worker_unit.name], check=True
    )
    time.sleep(1)
    return RuntimeProcesses(
        api_pid=_systemd_pid(api_unit),
        worker_pid=_systemd_pid(worker_unit),
        runtime_directory=runtime_directory,
    )


def restart_runtime(project_root: Path) -> RuntimeProcesses:
    project_root = project_root.resolve()
    runtime_directory = _runtime_directory(project_root)
    if autostart_installed(project_root):
        return _restart_systemd_runtime(project_root)
    upgrade_database(project_root)
    stop_runtime(project_root)
    api = _spawn("smart-growth-api", project_root, runtime_directory)
    try:
        _wait_for_api(api)
        worker = _spawn("smart-growth-worker", project_root, runtime_directory)
        _wait_for_worker(worker)
    except Exception as exc:
        stop_runtime(project_root)
        for name in ("api.pid", "worker.pid"):
            (runtime_directory / name).unlink(missing_ok=True)
        diagnostic = _runtime_log_tail(runtime_directory)
        raise RuntimeError(f"runtime restart failed: {exc}\n{diagnostic}") from exc
    return RuntimeProcesses(
        api_pid=api.pid,
        worker_pid=worker.pid,
        runtime_directory=runtime_directory,
    )
