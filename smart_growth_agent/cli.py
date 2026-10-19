from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import secrets
import tempfile
import uuid
from pathlib import Path

from smart_growth_agent.db.session import SessionFactory, engine
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.runtime import (
    inspect_runtime,
    install_autostart,
    remove_autostart,
    restart_runtime,
    runtime_log_tail,
    stop_runtime_services,
)
from smart_growth_agent.services.auth import AuthService
from smart_growth_agent.services.prompt_seed import (
    load_prompt_seed_file,
    load_single_seed_file,
    seed_prompts,
    seed_registry_entries,
    seed_scoring_rubric,
)
from smart_growth_agent.sharing import (
    TailscaleError,
    build_frontend,
    inspect_tailscale,
    inspect_tailscale_serve,
    start_tailscale_serve,
    stop_tailscale_serve,
)

DEFAULT_PROMPTS = (
    Path(__file__).resolve().parent / "prompts" / "phase2_templates.json"
)
DEFAULT_RUBRIC = (
    Path(__file__).resolve().parent
    / "knowledge"
    / "brand"
    / "phase4_rubric.json"
)
DEFAULT_PLATFORM_RULES = (
    Path(__file__).resolve().parent
    / "knowledge"
    / "platform"
    / "xhs_demo_rules.json"
)
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _upsert_env_values(path: Path, values: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    updated: list[str] = []
    for line in existing:
        key = (
            line.split("=", 1)[0].strip()
            if "=" in line and not line.lstrip().startswith("#")
            else None
        )
        if key in remaining:
            updated.append(f"{key}={remaining.pop(key)}")
        else:
            updated.append(line)
    if updated and updated[-1] != "":
        updated.append("")
    updated.extend(f"{key}={value}" for key, value in remaining.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write("\n".join(updated).rstrip() + "\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def configure_managed_llm(args: argparse.Namespace) -> None:
    env_file = args.env_file.resolve()
    existing_text = env_file.read_text(encoding="utf-8") if env_file.exists() else ""

    def has_real_secret(key: str) -> bool:
        prefix = f"{key}="
        value = next(
            (
                line.split("=", 1)[1].strip()
                for line in existing_text.splitlines()
                if line.startswith(prefix)
            ),
            "",
        )
        return bool(value) and not value.startswith(("replace-with-", "development-only-"))

    has_jwt_secret = has_real_secret("SMART_GROWTH_JWT_SECRET")
    has_encryption_key = has_real_secret("SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY")
    values = {"SMART_GROWTH_LLM_MODE": "managed"}
    if not has_jwt_secret:
        values["SMART_GROWTH_JWT_SECRET"] = secrets.token_urlsafe(48)
    if not has_encryption_key:
        values["SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY"] = secrets.token_urlsafe(48)
    _upsert_env_values(env_file, values)
    print(f"configured managed LLM environment in {env_file}")
    if args.restart:
        print("applying database migrations and restarting API/Worker...")
        processes = restart_runtime(env_file.parent)
        print(
            f"runtime ready: api_pid={processes.api_pid} "
            f"worker_pid={processes.worker_pid} mode=managed"
        )
        print(f"logs: {processes.runtime_directory}")
        if not has_jwt_secret:
            print("security note: JWT secret was initialized; browser users must sign in again")
        print("next: add provider and Agent bindings in 模型设置")
    else:
        print("runtime restart skipped")


async def bootstrap_admin(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Admin password: ")
    if len(password) < 12:
        raise SystemExit("Admin password must contain at least 12 characters")
    async with SessionFactory() as session:
        brand, user = await AuthService(session).bootstrap_admin(
            brand_name=args.brand_name,
            brand_slug=args.brand_slug,
            email=args.email,
            display_name=args.display_name,
            password=password,
        )
    print(f"brand_id={brand.id}")
    print(f"user_id={user.id}")
    await engine.dispose()


async def reset_password(args: argparse.Namespace) -> None:
    password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    async with SessionFactory() as session:
        user = await AuthService(session).reset_password(email=args.email, password=password)
    print(f"password reset for {user.email}")
    await engine.dispose()


async def seed_prompt_assets(args: argparse.Namespace) -> None:
    entries = load_prompt_seed_file(args.file)
    results = await seed_prompts(
        session_factory=SessionFactory,
        brand_id=uuid.UUID(args.brand_id),
        actor_id=uuid.UUID(args.actor_id),
        entries=entries,
        source_uri=args.source_uri,
        replace_changed_active=True,
    )
    for result in results:
        print(
            f"{result.action} stable_key={result.stable_key} "
            f"item_id={result.item_id} revision_id={result.revision_id}"
        )
    await engine.dispose()


async def seed_scoring_assets(args: argparse.Namespace) -> None:
    prompts = load_prompt_seed_file(args.prompts_file)
    prompt_results = await seed_prompts(
        session_factory=SessionFactory,
        brand_id=uuid.UUID(args.brand_id),
        actor_id=uuid.UUID(args.actor_id),
        entries=prompts,
        source_uri="repo://smart_growth_agent/prompts/phase2_templates.json",
        replace_changed_active=True,
    )
    rubric = await seed_scoring_rubric(
        session_factory=SessionFactory,
        brand_id=uuid.UUID(args.brand_id),
        actor_id=uuid.UUID(args.actor_id),
        entry=load_single_seed_file(args.rubric_file),
        source_uri="repo://smart_growth_agent/knowledge/brand/phase4_rubric.json",
        replace_changed_active=True,
    )
    for result in [*prompt_results, rubric]:
        print(
            f"{result.action} stable_key={result.stable_key} "
            f"item_id={result.item_id} revision_id={result.revision_id}"
        )
    await engine.dispose()


async def seed_platform_rules(args: argparse.Namespace) -> None:
    entries = load_prompt_seed_file(args.file)
    results = await seed_registry_entries(
        session_factory=SessionFactory,
        brand_id=uuid.UUID(args.brand_id),
        actor_id=uuid.UUID(args.actor_id),
        entries=entries,
        source_uri=args.source_uri,
        registry_type=RegistryType.PLATFORM_RULE,
        replace_changed_active=True,
    )
    for result in results:
        print(
            f"{result.action} stable_key={result.stable_key} "
            f"item_id={result.item_id} revision_id={result.revision_id}"
        )
    await engine.dispose()


def share_start(args: argparse.Namespace) -> None:
    project_root = args.project_root.resolve()
    status = inspect_tailscale()
    if not status.installed:
        raise TailscaleError(
            "尚未安装 Tailscale。请先按 README 的“Tailscale 私有共享”步骤安装。"
        )
    if status.backend_state != "Running":
        raise TailscaleError("Tailscale 尚未登录或未运行，请先执行 sudo tailscale up。")
    # Verify Serve authorization before spending time on a frontend build or
    # interrupting the local API/Worker. The proxy may safely point at the currently
    # running instance while the production bundle is rebuilt.
    shared = start_tailscale_serve()
    if args.build:
        print("building production frontend...")
        build_frontend(project_root)
    if args.restart:
        print("applying migrations and restarting API/Worker...")
        processes = restart_runtime(project_root)
        print(
            f"runtime ready: api_pid={processes.api_pid} "
            f"worker_pid={processes.worker_pid}"
        )
    print(f"private service ready: {shared.url}")
    print("access: only users/devices allowed by this tailnet; no public Funnel enabled")


def share_status() -> None:
    status = inspect_tailscale()
    if not status.installed:
        print("tailscale: not installed")
        return
    print(f"tailscale: {status.backend_state}")
    print(f"private_url: {status.url or 'unavailable'}")
    serve = inspect_tailscale_serve()
    print(
        f"serve: {'enabled' if serve.enabled else 'disabled'} "
        f"target={serve.target or '-'}"
    )


def share_stop() -> None:
    stop_tailscale_serve()
    print("Tailscale Serve stopped; local API/Worker remain running")


def runtime_restart(args: argparse.Namespace) -> None:
    project_root = args.project_root.resolve()
    print("applying migrations and restarting API/Worker...")
    processes = restart_runtime(project_root)
    print(
        f"runtime ready: api_pid={processes.api_pid} worker_pid={processes.worker_pid}"
    )
    print("local login: http://localhost:8000/login")
    print(f"logs: {processes.runtime_directory}")


def runtime_status(args: argparse.Namespace) -> None:
    project_root = args.project_root.resolve()
    status = inspect_runtime(project_root)
    print(f"api: {'running' if status.api_pids else 'stopped'} pids={status.api_pids or '-'}")
    print(
        f"worker: {'running' if status.worker_pids else 'stopped'} "
        f"pids={status.worker_pids or '-'}"
    )
    if status.health:
        print(
            "health: "
            f"{status.health.get('status')} database={status.health.get('database')} "
            f"worker={status.health.get('worker')}"
        )
    else:
        print(f"health: unavailable ({status.health_error or 'unknown error'})")
    print(f"autostart: {'installed' if status.autostart_installed else 'not installed'}")
    tailscale = inspect_tailscale()
    print(
        f"tailscale: {tailscale.backend_state or 'not installed'} "
        f"url={tailscale.url or '-'}"
    )
    serve = inspect_tailscale_serve()
    print(
        f"tailscale_serve: {'enabled' if serve.enabled else 'disabled'} "
        f"target={serve.target or '-'}"
        f"{f' error={serve.error}' if serve.error else ''}"
    )


def runtime_logs(args: argparse.Namespace) -> None:
    output = runtime_log_tail(args.project_root, lines=args.lines)
    print(output or "no runtime logs found")


def runtime_stop(args: argparse.Namespace) -> None:
    stop_runtime_services(args.project_root)
    print("API and Worker stopped")


def autostart_install(args: argparse.Namespace) -> None:
    paths = install_autostart(args.project_root)
    print("autostart installed and services started:")
    for path in paths:
        print(path)
    print("note: WSL and this Linux distribution must be running for the service to be available")


def autostart_remove(args: argparse.Namespace) -> None:
    remove_autostart(args.project_root)
    print("autostart removed; services stopped")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart Growth administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap-admin", help="create the first brand and admin")
    bootstrap.add_argument("--brand-name", required=True)
    bootstrap.add_argument("--brand-slug", required=True)
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--display-name", required=True)
    bootstrap.add_argument("--password", help="omit to read securely from the terminal")
    password_reset = subparsers.add_parser(
        "reset-password",
        help="securely reset a local user's password",
    )
    password_reset.add_argument("--email", required=True)
    subparsers.add_parser(
        "generate-credential-key",
        help="generate a server-side encryption key for .env",
    )
    managed = subparsers.add_parser(
        "configure-managed-llm",
        help="prepare encrypted LLM settings and restart API/Worker",
    )
    managed.add_argument("--env-file", type=Path, default=Path(".env"))
    managed.add_argument(
        "--no-restart",
        action="store_false",
        dest="restart",
        help="only update .env; do not restart API and Worker",
    )
    prompts = subparsers.add_parser(
        "seed-prompts",
        help="idempotently create and activate prompt templates",
    )
    prompts.add_argument("--brand-id", required=True)
    prompts.add_argument("--actor-id", required=True)
    prompts.add_argument("--file", type=Path, default=DEFAULT_PROMPTS)
    prompts.add_argument(
        "--source-uri",
        default="repo://smart_growth_agent/prompts/phase2_templates.json",
    )
    scoring = subparsers.add_parser(
        "seed-scoring-assets",
        help="idempotently activate scoring prompt and rubric",
    )
    scoring.add_argument("--brand-id", required=True)
    scoring.add_argument("--actor-id", required=True)
    scoring.add_argument("--prompts-file", type=Path, default=DEFAULT_PROMPTS)
    scoring.add_argument("--rubric-file", type=Path, default=DEFAULT_RUBRIC)
    platform_rules = subparsers.add_parser(
        "seed-platform-rules",
        help="idempotently create and activate concise platform rules",
    )
    platform_rules.add_argument("--brand-id", required=True)
    platform_rules.add_argument("--actor-id", required=True)
    platform_rules.add_argument("--file", type=Path, default=DEFAULT_PLATFORM_RULES)
    platform_rules.add_argument(
        "--source-uri",
        default="synthetic://paper-orbit/demo-rules",
    )
    sharing = subparsers.add_parser(
        "share-start",
        help="build, restart and privately share the app through Tailscale Serve",
    )
    sharing.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    sharing.add_argument(
        "--no-build",
        action="store_false",
        dest="build",
        help="reuse the existing frontend/dist build",
    )
    sharing.add_argument(
        "--no-restart",
        action="store_false",
        dest="restart",
        help="do not restart API and Worker",
    )
    subparsers.add_parser("share-status", help="show the private Tailscale URL")
    subparsers.add_parser("share-stop", help="stop private Tailscale sharing")
    runtime_restart_parser = subparsers.add_parser(
        "runtime-restart",
        help="apply migrations and safely restart API and Worker",
    )
    runtime_restart_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT
    )
    runtime_status_parser = subparsers.add_parser(
        "runtime-status",
        help="show API, Worker, database heartbeat and Tailscale status",
    )
    runtime_status_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT
    )
    runtime_logs_parser = subparsers.add_parser(
        "runtime-logs", help="show recent API and Worker logs"
    )
    runtime_logs_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT
    )
    runtime_logs_parser.add_argument("--lines", type=int, default=50)
    runtime_stop_parser = subparsers.add_parser(
        "runtime-stop", help="stop API and Worker"
    )
    runtime_stop_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT
    )
    autostart_install_parser = subparsers.add_parser(
        "autostart-install",
        help="install user-level systemd services with crash restart",
    )
    autostart_install_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT
    )
    autostart_remove_parser = subparsers.add_parser(
        "autostart-remove", help="remove user-level systemd services"
    )
    autostart_remove_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT
    )
    return parser


def run() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "bootstrap-admin":
            asyncio.run(bootstrap_admin(args))
        elif args.command == "reset-password":
            asyncio.run(reset_password(args))
        elif args.command == "generate-credential-key":
            print(secrets.token_urlsafe(48))
        elif args.command == "configure-managed-llm":
            configure_managed_llm(args)
        elif args.command == "seed-prompts":
            asyncio.run(seed_prompt_assets(args))
        elif args.command == "seed-scoring-assets":
            asyncio.run(seed_scoring_assets(args))
        elif args.command == "seed-platform-rules":
            asyncio.run(seed_platform_rules(args))
        elif args.command == "share-start":
            share_start(args)
        elif args.command == "share-status":
            share_status()
        elif args.command == "share-stop":
            share_stop()
        elif args.command == "runtime-restart":
            runtime_restart(args)
        elif args.command == "runtime-status":
            runtime_status(args)
        elif args.command == "runtime-logs":
            runtime_logs(args)
        elif args.command == "runtime-stop":
            runtime_stop(args)
        elif args.command == "autostart-install":
            autostart_install(args)
        elif args.command == "autostart-remove":
            autostart_remove(args)
    except TailscaleError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    run()
