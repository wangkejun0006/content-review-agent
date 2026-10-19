from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SMART_GROWTH_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "postgresql+psycopg://smart_growth:smart_growth@localhost:5432/smart_growth"
    jwt_secret: SecretStr = Field(
        default=SecretStr("development-only-change-this-secret"), min_length=32
    )
    jwt_algorithm: str = "HS256"
    credential_encryption_key: SecretStr | None = None
    access_token_minutes: int = Field(default=480, ge=5, le=1440)
    frontend_origin: str = "http://localhost:5173"
    serve_frontend: bool = True
    frontend_dist_path: Path = Path("frontend/dist")
    media_storage_path: Path = Path("smart_growth_agent/knowledge/products/media")
    mineru_base_url: str | None = None
    mineru_timeout_seconds: float = Field(default=300, ge=10, le=1800)

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    llm_mode: str = "unavailable"
    llm_request_timeout_seconds: float = Field(default=180, ge=10, le=600)
    llm_max_output_tokens: int = Field(default=4096, ge=256, le=8192)
    llm_budget_path: Path = Path(".runtime/live-budget.json")
    llm_max_calls: int = Field(default=24, ge=1, le=64)
    llm_no_network_retry: bool = True
    local_demo: bool = False

    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    worker_heartbeat_seconds: float = Field(default=5.0, ge=1, le=60)
    worker_stale_seconds: int = Field(default=20, ge=5, le=300)
    job_lease_seconds: int = Field(default=300, ge=30, le=3600)
    job_max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        allowed = ("postgresql+psycopg://", "sqlite+aiosqlite://")
        if not value.startswith(allowed):
            raise ValueError("database_url must use psycopg or aiosqlite")
        return value

    @model_validator(mode="after")
    def validate_llm_mode(self) -> Settings:
        allowed = {"unavailable", "fake", "openai_compatible", "managed"}
        if self.llm_mode not in allowed:
            raise ValueError(f"llm_mode must be one of {sorted(allowed)}")
        if self.llm_mode == "fake" and self.environment == "production":
            raise ValueError("fake LLM mode is forbidden in production")
        if self.llm_mode == "openai_compatible" and (
            self.openai_api_key is None or self.openai_model is None
        ):
            raise ValueError("openai_compatible mode requires API key and model")
        if self.llm_mode == "managed" and self.credential_encryption_key is None:
            raise ValueError("managed mode requires CREDENTIAL_ENCRYPTION_KEY")
        return self

    @property
    def checkpoint_database_url(self) -> str:
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise RuntimeError("PostgreSQL is required for durable LangGraph checkpoints")
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=None) if os.environ.get("PAPER_ORBIT_OFFLINE") == "1" else Settings()
