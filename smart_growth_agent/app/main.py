from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from smart_growth_agent.app.api.analytics import router as analytics_router
from smart_growth_agent.app.api.audit import router as audit_router
from smart_growth_agent.app.api.auth import router as auth_router
from smart_growth_agent.app.api.compliance import router as compliance_router
from smart_growth_agent.app.api.demo import router as demo_router
from smart_growth_agent.app.api.evidence_import import router as evidence_import_router
from smart_growth_agent.app.api.feedback import router as feedback_router
from smart_growth_agent.app.api.imports import router as imports_router
from smart_growth_agent.app.api.ingestion import router as ingestion_router
from smart_growth_agent.app.api.knowledge import router as knowledge_router
from smart_growth_agent.app.api.llm_config import router as llm_config_router
from smart_growth_agent.app.api.media import public_router as media_public_router
from smart_growth_agent.app.api.media import router as media_router
from smart_growth_agent.app.api.operations import router as operations_router
from smart_growth_agent.app.api.platform_rule_import import router as platform_rule_import_router
from smart_growth_agent.app.api.product_import import router as product_import_router
from smart_growth_agent.app.api.registry import router as registry_router
from smart_growth_agent.app.api.reviews import router as reviews_router
from smart_growth_agent.app.api.runs import router as runs_router
from smart_growth_agent.app.api.scoring import router as scoring_router
from smart_growth_agent.config import get_settings
from smart_growth_agent.db.models import WorkerHeartbeat
from smart_growth_agent.db.session import SessionFactory, engine
from smart_growth_agent.domain.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from smart_growth_agent.llm.openai_compatible import LLMGatewayError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Paper Orbit AI Content Studio",
    version="0.1.0",
    description="Registry-first Phase 1 API. No automatic publishing.",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/v1")
app.include_router(demo_router, prefix="/v1")
app.include_router(analytics_router, prefix="/v1")
app.include_router(audit_router, prefix="/v1")
app.include_router(compliance_router, prefix="/v1")
app.include_router(evidence_import_router, prefix="/v1")
app.include_router(feedback_router, prefix="/v1")
app.include_router(imports_router, prefix="/v1")
app.include_router(ingestion_router, prefix="/v1")
app.include_router(knowledge_router, prefix="/v1")
app.include_router(llm_config_router, prefix="/v1")
app.include_router(media_router, prefix="/v1")
app.include_router(operations_router, prefix="/v1")
app.include_router(platform_rule_import_router, prefix="/v1")
app.include_router(product_import_router, prefix="/v1")
app.include_router(registry_router, prefix="/v1")
app.include_router(reviews_router, prefix="/v1")
app.include_router(scoring_router, prefix="/v1")
app.include_router(runs_router, prefix="/v1")
app.include_router(media_public_router)
PRODUCT_ASSET_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "knowledge" / "products" / "inbox"
)
PRODUCT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@app.get("/product-assets/{asset_path:path}", include_in_schema=False)
async def product_image(asset_path: str) -> FileResponse:
    """Expose local preview images without exposing source spreadsheets/documents."""
    requested = (PRODUCT_ASSET_DIRECTORY / asset_path).resolve()
    if (
        not requested.is_relative_to(PRODUCT_ASSET_DIRECTORY.resolve())
        or requested.suffix.lower() not in PRODUCT_IMAGE_EXTENSIONS
        or not requested.is_file()
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(requested)


ERROR_STATUS: dict[type[DomainError], int] = {
    LLMGatewayError: status.HTTP_502_BAD_GATEWAY,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    ValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
}


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    code = next(
        (
            status_code
            for error_type, status_code in ERROR_STATUS.items()
            if isinstance(exc, error_type)
        ),
        status.HTTP_400_BAD_REQUEST,
    )
    return JSONResponse(status_code=code, content={"detail": str(exc)})


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def ready() -> dict[str, Any]:
    async with SessionFactory() as session:
        await session.execute(text("SELECT 1"))
        heartbeat = await session.scalar(
            select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()).limit(1)
        )
    worker_online = bool(
        heartbeat
        and heartbeat.status != "stopped"
        and (
            heartbeat.last_seen_at
            if heartbeat.last_seen_at.tzinfo is not None
            else heartbeat.last_seen_at.replace(tzinfo=UTC)
        )
        >= datetime.now(UTC) - timedelta(seconds=settings.worker_stale_seconds)
    )
    return {
        "status": "ready" if worker_online else "degraded",
        "database": "ok",
        "frontend": "ready" if FRONTEND_INDEX.is_file() else "development_server",
        "worker": "online" if worker_online else "offline",
        "worker_last_seen_at": heartbeat.last_seen_at.isoformat() if heartbeat else None,
    }


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIRECTORY = (
    settings.frontend_dist_path
    if settings.frontend_dist_path.is_absolute()
    else PROJECT_ROOT / settings.frontend_dist_path
).resolve()
FRONTEND_INDEX = FRONTEND_DIST_DIRECTORY / "index.html"
FRONTEND_ASSETS = FRONTEND_DIST_DIRECTORY / "assets"

if settings.serve_frontend and FRONTEND_INDEX.is_file():
    if FRONTEND_ASSETS.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_ASSETS),
            name="frontend-assets",
        )

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_app(frontend_path: str) -> FileResponse:
        """Serve the production SPA on the same origin as the API.

        API-like prefixes deliberately stay 404 instead of returning index.html,
        which keeps client and monitoring failures observable.
        """

        reserved = ("v1", "health", "product-assets", "docs", "redoc", "openapi.json")
        if frontend_path and frontend_path.startswith(reserved):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        requested = (FRONTEND_DIST_DIRECTORY / frontend_path).resolve()
        if (
            frontend_path
            and requested.is_relative_to(FRONTEND_DIST_DIRECTORY)
            and requested.is_file()
        ):
            return FileResponse(requested)
        return FileResponse(FRONTEND_INDEX)


def run() -> None:
    settings = get_settings()
    reload_enabled = settings.environment == "development" and settings.llm_mode != "managed"
    uvicorn.run(
        "smart_growth_agent.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload_enabled,
        reload_dirs=["smart_growth_agent"] if reload_enabled else None,
    )


if __name__ == "__main__":
    run()
