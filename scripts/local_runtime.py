"""Offline local instances. No ambient provider credentials or historical budget."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def identity(instance):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", instance):
        raise ValueError("instance must be 1-24 lowercase letters/digits/hyphens")
    scope = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    return "paper-orbit-" + scope + "-" + instance


def private_directory(namespace):
    base = Path(
        os.environ.get("PAPER_ORBIT_PRIVATE_HOME", str(Path.home() / ".local/share/paper-orbit"))
    )
    if base.is_symlink():
        raise RuntimeError("private_home_symlink")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = base / namespace
    if directory.is_symlink():
        raise RuntimeError("private_directory_symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.stat().st_uid != os.getuid() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise RuntimeError("private_directory_permissions")
    return directory


def load_private(namespace, port, db_port):
    directory = private_directory(namespace)
    path = directory / "session.json"
    if not path.exists():
        # Never invent a new password for an existing persistent database.
        volume = subprocess.run(
            ["docker", "volume", "inspect", namespace + "-data"], capture_output=True
        )
        if volume.returncode == 0:
            raise RuntimeError("volume_exists_without_private_config_restore_config_first")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(
                {
                    "db_password": secrets.token_urlsafe(32),
                    "jwt": secrets.token_urlsafe(48),
                    "admin_password": secrets.token_urlsafe(24),
                    "port": port,
                    "db_port": db_port,
                    "namespace": namespace,
                },
                stream,
            )
    if (
        path.is_symlink()
        or path.stat().st_uid != os.getuid()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
    ):
        raise RuntimeError("private_session_permissions")
    private = json.loads(path.read_text())
    if any(
        private[k] != v
        for k, v in {"namespace": namespace, "port": port, "db_port": db_port}.items()
    ):
        raise RuntimeError("instance_configuration_mismatch_use_original_ports_or_new_instance")
    return directory, private


def configure(instance="demo", port=8766, db_port=55433):
    namespace = identity(instance)
    directory, private = load_private(namespace, port, db_port)
    state = ROOT / ".runtime/instances" / instance
    if state.is_symlink():
        raise RuntimeError("state_directory_symlink")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    # This launcher is deliberately offline. Do not resolve .env or provider files.
    for name in list(os.environ):
        if name.startswith("SMART_GROWTH_"):
            del os.environ[name]
    os.environ.update(
        {
            "PAPER_ORBIT_OFFLINE": "1",
            "SMART_GROWTH_DATABASE_URL": "postgresql+psycopg://paper_orbit:"
            + private["db_password"]
            + "@127.0.0.1:"
            + str(db_port)
            + "/paper_orbit",
            "SMART_GROWTH_JWT_SECRET": private["jwt"],
            "SMART_GROWTH_FRONTEND_ORIGIN": "http://localhost:" + str(port),
            "SMART_GROWTH_MEDIA_STORAGE_PATH": str(state / "media"),
            "SMART_GROWTH_DEMO_STATE_PATH": str(state / "demo-state.json"),
            "SMART_GROWTH_DEMO_SCENARIO_PATH": str(state / "scenarios.json"),
            "SMART_GROWTH_LLM_MODE": "fake",
            "SMART_GROWTH_LOCAL_DEMO": "true",
            "SMART_GROWTH_LLM_BUDGET_PATH": str(state / "not-authorized-budget.json"),
            "SMART_GROWTH_JOB_MAX_ATTEMPTS": "1",
            "SMART_GROWTH_MINERU_BASE_URL": "",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
        }
    )
    from smart_growth_agent.offline_boundary import install

    install()
    return namespace, directory, private, state


def wait_for_database(private):
    import psycopg

    # pg_isready against a local socket can succeed for Docker's temporary init
    # server. Authenticate through the actual mapped TCP port before migrations.
    for _ in range(120):
        try:
            connection = psycopg.connect(
                host="127.0.0.1",
                port=private["db_port"],
                dbname="paper_orbit",
                user="paper_orbit",
                password=private["db_password"],
                connect_timeout=1,
            )
        except psycopg.OperationalError:
            time.sleep(0.25)
        else:
            connection.close()
            return
    raise RuntimeError("postgres_tcp_not_ready")


def database(namespace, directory, private):
    name, volume = namespace + "-db", namespace + "-data"
    label = "paper-orbit.instance=" + namespace
    check = subprocess.run(
        ["docker", "container", "inspect", name, "--format", "{{json .Config.Labels}}"],
        capture_output=True,
        text=True,
    )
    if check.returncode:
        existing = subprocess.run(
            ["docker", "volume", "inspect", volume, "--format", "{{json .Labels}}"],
            capture_output=True,
            text=True,
        )
        if (
            existing.returncode == 0
            and (json.loads(existing.stdout or "null") or {}).get("paper-orbit.instance")
            != namespace
        ):
            raise RuntimeError("volume_owned_by_another_instance")
        subprocess.run(
            ["docker", "volume", "create", "--label", label, volume],
            check=True,
            capture_output=True,
        )
        env_file = directory / "postgres.env"
        fd = (
            os.open(env_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            if not env_file.exists()
            else None
        )
        if fd is not None:
            with os.fdopen(fd, "w") as stream:
                stream.write(
                    "POSTGRES_DB=paper_orbit\nPOSTGRES_USER=paper_orbit\nPOSTGRES_PASSWORD="
                    + private["db_password"]
                    + "\n"
                )
        if env_file.is_symlink() or stat.S_IMODE(env_file.stat().st_mode) != 0o600:
            raise RuntimeError("private_environment_permissions")
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--label",
                label,
                "--env-file",
                str(env_file),
                "-p",
                "127.0.0.1:" + str(private["db_port"]) + ":5432",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "-v",
                volume + ":/var/lib/postgresql/data",
                "pgvector/pgvector:pg16",
            ],
            capture_output=True,
        )
        if result.returncode:
            raise RuntimeError("database_container_start_failed_check_docker_and_port")
    else:
        if (json.loads(check.stdout) or {}).get("paper-orbit.instance") != namespace:
            raise RuntimeError("container_owned_by_another_instance")
        subprocess.run(["docker", "start", name], check=True, capture_output=True)
    wait_for_database(private)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        # Do not print connection strings or credentials from migration errors.
        raise RuntimeError("database_migration_failed_inspect_instance_privately")


def main():
    parser = argparse.ArgumentParser(description="Offline instance; real model calls are disabled")
    parser.add_argument("command", choices=["setup", "serve", "worker", "demo-scenarios", "info"])
    parser.add_argument("--instance", default="demo")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--db-port", type=int, default=55433)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if (
        not (1024 <= args.port <= 65535 and 1024 <= args.db_port <= 65535)
        or args.port == args.db_port
    ):
        parser.error("use distinct unprivileged ports")
    os.chdir(ROOT)
    namespace, directory, private, state = configure(args.instance, args.port, args.db_port)
    if args.command == "info":
        print(
            json.dumps(
                {
                    "namespace": namespace,
                    "state": str(state),
                    "private_config_directory": str(directory),
                    "url": "http://localhost:" + str(args.port),
                    "model_mode": "fake",
                }
            )
        )
    elif args.command == "setup":
        database(namespace, directory, private)
        from smart_growth_agent.demo_seed import seed_demo

        asyncio.run(seed_demo(private["admin_password"]))
        print("Offline fictional database initialized; original data and budgets are not used.")
    elif args.command == "demo-scenarios":
        from smart_growth_agent.demo_scenarios import install_local_scenarios

        print(json.dumps(asyncio.run(install_local_scenarios()), ensure_ascii=False))
    elif args.command == "serve":
        import uvicorn

        from smart_growth_agent.app.main import app

        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
    else:
        from smart_growth_agent.worker import async_main

        asyncio.run(async_main(once=args.once))


if __name__ == "__main__":
    main()
