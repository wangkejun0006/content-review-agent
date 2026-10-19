from __future__ import annotations

import time
from typing import TypeVar

from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import (
    AgentLLMBinding,
    LLMCallLog,
    LLMProviderConfig,
)
from smart_growth_agent.llm.openai_compatible import LLMGatewayError, OpenAICompatibleGateway
from smart_growth_agent.llm.policy import provider_settings, validate_registry_contract
from smart_growth_agent.llm.types import LLMRequest, LLMResult
from smart_growth_agent.security import CredentialCipher

T = TypeVar("T", bound=BaseModel)


class ManagedLLMGateway:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.cipher = CredentialCipher(settings)

    async def generate(self, request: LLMRequest, response_model: type[T]) -> LLMResult[T]:
        await validate_registry_contract(self.session_factory, request, response_model)
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(AgentLLMBinding, LLMProviderConfig)
                    .join(
                        LLMProviderConfig,
                        LLMProviderConfig.id == AgentLLMBinding.provider_config_id,
                    )
                    .where(
                        AgentLLMBinding.brand_id == request.brand_id,
                        AgentLLMBinding.purpose == request.purpose,
                        LLMProviderConfig.brand_id == request.brand_id,
                        LLMProviderConfig.is_enabled.is_(True),
                    )
                )
            ).one_or_none()
        if row is None:
            raise LLMGatewayError(f"Agent 用途 {request.purpose} 尚未绑定已启用的模型服务。")
        binding, provider = row
        dynamic_settings = provider_settings(
            self.settings,
            base_url=provider.base_url,
            api_key=SecretStr(self.cipher.decrypt(provider.api_key_encrypted)),
            model=binding.model_override or provider.default_model,
        )
        gateway = OpenAICompatibleGateway(dynamic_settings)
        started = time.perf_counter()
        try:
            result = await gateway.generate(
                request.model_copy(
                    update={"model": binding.model_override or provider.default_model}
                ),
                response_model,
            )
        except LLMGatewayError as exc:
            try:
                async with self.session_factory() as session, session.begin():
                    session.add(
                        LLMCallLog(
                            brand_id=request.brand_id,
                            run_id=request.run_id,
                            provider=provider.name,
                            model=binding.model_override or provider.default_model,
                            purpose=request.purpose,
                            prompt_revision_id=request.prompt_revision_id,
                            latency_ms=round((time.perf_counter() - started) * 1000),
                            error={
                                "message": str(exc),
                                "provider_status": exc.provider_status,
                                "provider_code": exc.provider_code,
                            },
                        )
                    )
            except Exception:
                # Failure telemetry must never replace the original provider error.
                pass
            raise
        finally:
            await gateway.aclose()
        result = result.model_copy(update={"provider": provider.name})
        telemetry_logged = False
        try:
            async with self.session_factory() as session, session.begin():
                session.add(
                    LLMCallLog(
                        brand_id=request.brand_id,
                        run_id=request.run_id,
                        provider=provider.name,
                        model=result.model,
                        purpose=request.purpose,
                        prompt_revision_id=request.prompt_revision_id,
                        input_tokens=result.usage.input_tokens,
                        output_tokens=result.usage.output_tokens,
                        latency_ms=result.latency_ms,
                        provider_request_id=result.provider_request_id,
                    )
                )
            telemetry_logged = True
        except Exception:
            # Telemetry is best-effort. The calling service retains its legacy
            # success logger when this insert cannot be committed.
            telemetry_logged = False
        return result.model_copy(
            update={
                "raw_metadata": {
                    **result.raw_metadata,
                    "telemetry_logged": telemetry_logged,
                }
            }
        )
