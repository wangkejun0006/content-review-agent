from __future__ import annotations

import pytest
from pydantic import ValidationError

from smart_growth_agent.config import Settings


def test_fake_llm_mode_is_development_only() -> None:
    settings = Settings(
        environment="development",
        database_url="sqlite+aiosqlite:///:memory:",
        llm_mode="fake",
    )
    assert settings.llm_mode == "fake"

    with pytest.raises(ValidationError, match="forbidden in production"):
        Settings(
            environment="production",
            database_url="sqlite+aiosqlite:///:memory:",
            llm_mode="fake",
        )
