"""Rehearse the original workflow without credentials or external HTTP."""

import argparse
import asyncio
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def run(output):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from smart_growth_agent.db.base import Base
    from smart_growth_agent.demo_scenarios import exercise_scenarios, product_diagram
    from smart_growth_agent.demo_seed import seed_demo

    async def reject_network(*args, **kwargs):
        raise AssertionError("External HTTP is forbidden in offline rehearsal")

    with tempfile.TemporaryDirectory(prefix="paper-orbit-p0-") as directory:
        temporary = Path(directory)
        engine = create_async_engine(
            "sqlite+aiosqlite:///" + str(temporary / "demo.db"), connect_args={"timeout": 30}
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", reject_network):
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)
                state = await seed_demo(
                    secrets.token_urlsafe(24),
                    session_factory=factory,
                    state_path=temporary / "state.json",
                )
                report = await exercise_scenarios(factory, state, media_path=temporary / "media")
            assets = output.parent / "assets"
            assets.mkdir(parents=True, exist_ok=False)
            (assets / "paper-orbit-fictional.png").write_bytes(product_diagram())
            report["database"] = "temporary SQLite, disposed after rehearsal"
            report["network_guard"] = "external HTTP transport blocked"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return report
        finally:
            await engine.dispose()


if __name__ == "__main__":
    os.environ["PAPER_ORBIT_OFFLINE"] = "1"
    os.environ["SMART_GROWTH_LLM_MODE"] = "fake"
    os.environ.pop("SMART_GROWTH_OPENAI_API_KEY", None)
    os.environ["SMART_GROWTH_MINERU_BASE_URL"] = ""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".runtime/offline-rehearsal/report.json"
    )
    args = parser.parse_args()
    if args.output.exists() or args.output.parent.exists():
        parser.error("fresh output path required; historical reports are immutable")
    result = asyncio.run(run(args.output))
    raise SystemExit(0 if result["pass"] else 1)
