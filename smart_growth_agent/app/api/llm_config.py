from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.models import AgentLLMBinding, LLMProviderConfig
from smart_growth_agent.db.session import get_session
from smart_growth_agent.llm.openai_compatible import LLMGatewayError, OpenAICompatibleGateway
from smart_growth_agent.llm.policy import provider_settings
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.llm_config import (
    MANAGED_LLM_PURPOSES,
    AgentLLMBindingRead,
    AgentLLMBindingUpsert,
    LLMConfigurationStatus,
    LLMProviderCreate,
    LLMProviderRead,
    LLMProviderTestOutput,
    LLMProviderUpdate,
    LLMUsageReport,
)
from smart_growth_agent.security import CredentialCipher
from smart_growth_agent.services.llm_config import LLMConfigService

router = APIRouter(prefix="/llm", tags=["llm-configuration"])


def _provider_read(provider: LLMProviderConfig) -> LLMProviderRead:
    return LLMProviderRead.model_validate(provider)


@router.get("/status", response_model=LLMConfigurationStatus)
async def configuration_status(
    settings: Settings = Depends(get_settings),
    _principal: Principal = Depends(get_principal),
) -> LLMConfigurationStatus:
    return LLMConfigurationStatus(
        credential_storage_ready=settings.credential_encryption_key is not None,
        runtime_mode=settings.llm_mode,
    )


@router.get("/providers", response_model=list[LLMProviderRead])
async def list_providers(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[LLMProviderRead]:
    rows = list(
        await session.scalars(
            select(LLMProviderConfig)
            .where(LLMProviderConfig.brand_id == principal.brand_id)
            .order_by(LLMProviderConfig.created_at)
        )
    )
    return [_provider_read(row) for row in rows]


@router.get("/usage", response_model=LLMUsageReport)
async def llm_usage(
    days: int = Query(default=30, ge=0, le=3650),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(get_principal),
) -> LLMUsageReport:
    return await LLMConfigService(session, settings).get_usage_report(
        brand_id=principal.brand_id,
        days=days or None,
    )


@router.post("/providers", response_model=LLMProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    data: LLMProviderCreate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("llm:manage")),
) -> LLMProviderRead:
    provider = await LLMConfigService(session, settings).create_provider(
        brand_id=principal.brand_id,
        actor_id=principal.user_id,
        data=data,
    )
    return _provider_read(provider)


@router.patch("/providers/{provider_id}", response_model=LLMProviderRead)
async def update_provider(
    provider_id: uuid.UUID,
    data: LLMProviderUpdate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("llm:manage")),
) -> LLMProviderRead:
    provider = await LLMConfigService(session, settings).update_provider(
        brand_id=principal.brand_id,
        provider_id=provider_id,
        actor_id=principal.user_id,
        data=data,
    )
    return _provider_read(provider)


@router.post("/providers/{provider_id}/test", response_model=LLMProviderTestOutput)
async def test_provider(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("llm:manage")),
) -> LLMProviderTestOutput:
    provider = await session.scalar(
        select(LLMProviderConfig).where(
            LLMProviderConfig.id == provider_id,
            LLMProviderConfig.brand_id == principal.brand_id,
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="LLM provider not found")
    persisted_provider_id = provider.id
    try:
        key = CredentialCipher(settings).decrypt(provider.api_key_encrypted)
        dynamic = provider_settings(
            settings,
            base_url=provider.base_url,
            api_key=SecretStr(key),
            model=provider.default_model,
        )
        gateway = OpenAICompatibleGateway(dynamic)
        try:
            result = await gateway.generate(
                LLMRequest(
                    brand_id=principal.brand_id,
                    purpose="configuration_test",
                    temperature=0.1,
                    messages=[
                        ChatMessage(
                            role="user",
                            content="Return JSON with status=ok and a short message.",
                        )
                    ],
                ),
                LLMProviderTestOutput,
            )
        finally:
            await gateway.aclose()
        await session.rollback()
        await LLMConfigService(session, settings).mark_test(
            brand_id=principal.brand_id,
            provider_id=persisted_provider_id,
            status="passed",
            message=f"Connected to {result.model}",
            model=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            latency_ms=result.latency_ms,
            provider_request_id=result.provider_request_id,
        )
        return result.value
    except Exception as exc:
        await session.rollback()
        safe_message = (
            str(exc)
            if isinstance(exc, LLMGatewayError)
            else "模型连接测试失败，请检查服务配置和供应商状态。"
        )
        await LLMConfigService(session, settings).mark_test(
            brand_id=principal.brand_id,
            provider_id=persisted_provider_id,
            status="failed",
            message=safe_message,
        )
        raise HTTPException(status_code=502, detail=safe_message) from exc


@router.get("/bindings", response_model=list[AgentLLMBindingRead])
async def list_bindings(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[AgentLLMBindingRead]:
    rows = list(
        await session.scalars(
            select(AgentLLMBinding)
            .where(AgentLLMBinding.brand_id == principal.brand_id)
            .order_by(AgentLLMBinding.purpose)
        )
    )
    return [AgentLLMBindingRead.model_validate(row) for row in rows]


@router.put("/bindings/{purpose}", response_model=AgentLLMBindingRead)
async def upsert_binding(
    purpose: str,
    data: AgentLLMBindingUpsert,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("llm:manage")),
) -> AgentLLMBindingRead:
    if purpose not in MANAGED_LLM_PURPOSES:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported purpose; choose one of {json.dumps(MANAGED_LLM_PURPOSES)}",
        )
    binding = await LLMConfigService(session, settings).upsert_binding(
        brand_id=principal.brand_id,
        purpose=purpose,
        actor_id=principal.user_id,
        data=data,
    )
    return AgentLLMBindingRead.model_validate(binding)
