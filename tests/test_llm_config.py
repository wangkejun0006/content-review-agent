from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import Brand, LLMCallLog
from smart_growth_agent.domain.errors import ConflictError
from smart_growth_agent.schemas.llm_config import (
    AgentLLMBindingUpsert,
    LLMProviderCreate,
    LLMProviderRead,
    LLMProviderUpdate,
)
from smart_growth_agent.security import CredentialCipher
from smart_growth_agent.services.llm_config import LLMConfigService


async def test_llm_provider_key_is_encrypted_and_binding_is_version_independent(
    session_factory,
) -> None:
    settings = Settings(
        credential_encryption_key=SecretStr("independent-test-encryption-key-123"),
    )
    async with session_factory() as session, session.begin():
        brand = Brand(name="LLM Brand", slug="llm-brand")
        session.add(brand)
        await session.flush()
        brand_id = brand.id

    async with session_factory() as session:
        service = LLMConfigService(session, settings)
        provider = await service.create_provider(
            brand_id=brand_id,
            actor_id=brand_id,
            data=LLMProviderCreate(
                name="Primary",
                base_url="https://api.example.com/v1",
                api_key=SecretStr("expensive-secret-api-key"),
                default_model="model-a",
            ),
        )
        assert "expensive-secret-api-key" not in provider.api_key_encrypted
        assert (
            CredentialCipher(settings).decrypt(provider.api_key_encrypted)
            == "expensive-secret-api-key"
        )
        binding = await service.upsert_binding(
            brand_id=brand_id,
            purpose="xhs_writer",
            actor_id=brand_id,
            data=AgentLLMBindingUpsert(
                provider_config_id=provider.id,
                model_override="writer-model",
            ),
        )
        assert binding.model_override == "writer-model"

        encrypted_key = provider.api_key_encrypted
        updated = await service.update_provider(
            brand_id=brand_id,
            provider_id=provider.id,
            actor_id=brand_id,
            data=LLMProviderUpdate(default_model="model-a2", is_enabled=False),
        )
        assert updated.default_model == "model-a2"
        assert updated.is_enabled is False
        assert updated.api_key_encrypted == encrypted_key
        assert LLMProviderRead.model_validate(updated).updated_at is not None

        await service.mark_test(
            brand_id=brand_id,
            provider_id=provider.id,
            status="passed",
            message="Connected",
            model="model-a2",
            input_tokens=3,
            output_tokens=2,
            latency_ms=25,
            provider_request_id="config-test-1",
        )
        test_log = await session.scalar(
            select(LLMCallLog).where(LLMCallLog.purpose == "configuration_test")
        )
        assert test_log is not None
        assert test_log.input_tokens == 3
        assert test_log.output_tokens == 2
        await session.rollback()

        with pytest.raises(ConflictError, match="名称已存在"):
            await service.create_provider(
                brand_id=brand_id,
                actor_id=brand_id,
                data=LLMProviderCreate(
                    name="Primary",
                    base_url="https://api.example.com/v1",
                    api_key=SecretStr("another-secret"),
                    default_model="model-b",
                ),
            )
