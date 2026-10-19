from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import SecretStr
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import AgentLLMBinding, LLMCallLog, LLMProviderConfig
from smart_growth_agent.domain.errors import ConflictError, NotFoundError, ValidationError
from smart_growth_agent.schemas.llm_config import (
    MANAGED_LLM_PURPOSES,
    AgentLLMBindingUpsert,
    LLMProviderCreate,
    LLMProviderUpdate,
    LLMUsageProviderBreakdown,
    LLMUsagePurposeBreakdown,
    LLMUsageReport,
    LLMUsageTotals,
)
from smart_growth_agent.security import CredentialCipher
from smart_growth_agent.services.audit import record_audit


class LLMConfigService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def _cipher(self) -> CredentialCipher:
        try:
            return CredentialCipher(self.settings)
        except RuntimeError as exc:
            raise ValidationError(
                "服务器尚未配置 SMART_GROWTH_CREDENTIAL_ENCRYPTION_KEY"
            ) from exc

    @staticmethod
    def _usage_totals(row: Any) -> LLMUsageTotals:
        input_tokens = int(row.input_tokens or 0)
        output_tokens = int(row.output_tokens or 0)
        return LLMUsageTotals(
            calls=int(row.calls or 0),
            successful_calls=int(row.successful_calls or 0),
            failed_calls=int(row.failed_calls or 0),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            unreported_token_calls=int(row.unreported_token_calls or 0),
            average_latency_ms=round(float(row.average_latency_ms or 0)),
        )

    async def get_usage_report(
        self, *, brand_id: uuid.UUID, days: int | None
    ) -> LLMUsageReport:
        period_end = datetime.now(UTC)
        cutoff = period_end - timedelta(days=days) if days is not None else None
        filters = [LLMCallLog.brand_id == brand_id]
        if cutoff is not None:
            filters.append(LLMCallLog.created_at >= cutoff)

        aggregate_columns = (
            func.count(LLMCallLog.id).label("calls"),
            func.sum(case((LLMCallLog.error.is_(None), 1), else_=0)).label(
                "successful_calls"
            ),
            func.sum(case((LLMCallLog.error.is_not(None), 1), else_=0)).label(
                "failed_calls"
            ),
            func.coalesce(func.sum(LLMCallLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(LLMCallLog.output_tokens), 0).label("output_tokens"),
            func.sum(
                case(
                    (
                        LLMCallLog.input_tokens.is_(None)
                        & LLMCallLog.output_tokens.is_(None),
                        1,
                    ),
                    else_=0,
                )
            ).label("unreported_token_calls"),
            func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("average_latency_ms"),
        )
        total_row = (
            await self.session.execute(
                select(*aggregate_columns, func.min(LLMCallLog.created_at).label("first_call_at"))
                .where(*filters)
            )
        ).one()
        provider_rows = (
            await self.session.execute(
                select(LLMCallLog.provider, LLMCallLog.model, *aggregate_columns)
                .where(*filters)
                .group_by(LLMCallLog.provider, LLMCallLog.model)
                .order_by(
                    (
                        func.coalesce(func.sum(LLMCallLog.input_tokens), 0)
                        + func.coalesce(func.sum(LLMCallLog.output_tokens), 0)
                    ).desc()
                )
            )
        ).all()
        purpose_rows = (
            await self.session.execute(
                select(LLMCallLog.purpose, *aggregate_columns)
                .where(*filters)
                .group_by(LLMCallLog.purpose)
                .order_by(
                    (
                        func.coalesce(func.sum(LLMCallLog.input_tokens), 0)
                        + func.coalesce(func.sum(LLMCallLog.output_tokens), 0)
                    ).desc()
                )
            )
        ).all()
        return LLMUsageReport(
            requested_days=days,
            period_start=cutoff if cutoff is not None else total_row.first_call_at,
            period_end=period_end,
            totals=self._usage_totals(total_row),
            by_provider=[
                LLMUsageProviderBreakdown(
                    provider=row.provider,
                    model=row.model,
                    **self._usage_totals(row).model_dump(),
                )
                for row in provider_rows
            ],
            by_purpose=[
                LLMUsagePurposeBreakdown(
                    purpose=row.purpose,
                    **self._usage_totals(row).model_dump(),
                )
                for row in purpose_rows
            ],
        )

    async def create_provider(
        self,
        *,
        brand_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: LLMProviderCreate,
    ) -> LLMProviderConfig:
        async with self.session.begin():
            existing = await self.session.scalar(
                select(LLMProviderConfig.id).where(
                    LLMProviderConfig.brand_id == brand_id,
                    LLMProviderConfig.name == data.name,
                )
            )
            if existing is not None:
                raise ConflictError("模型服务名称已存在，请使用其他名称")
            provider = LLMProviderConfig(
                brand_id=brand_id,
                name=data.name,
                provider_type=data.provider_type,
                base_url=str(data.base_url).rstrip("/"),
                api_key_encrypted=self._cipher().encrypt(data.api_key.get_secret_value()),
                default_model=data.default_model,
                created_by=actor_id,
            )
            self.session.add(provider)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="llm.provider_created",
                resource_type="llm_provider_config",
                resource_id=provider.id,
                details={"name": provider.name, "base_url": provider.base_url},
            )
        return provider

    async def update_provider(
        self,
        *,
        brand_id: uuid.UUID,
        provider_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: LLMProviderUpdate,
    ) -> LLMProviderConfig:
        async with self.session.begin():
            provider = await self.session.scalar(
                select(LLMProviderConfig)
                .where(LLMProviderConfig.id == provider_id, LLMProviderConfig.brand_id == brand_id)
                .with_for_update()
            )
            if provider is None:
                raise NotFoundError("LLM provider not found")
            values = data.model_dump(exclude_unset=True)
            if "name" in values:
                duplicate = await self.session.scalar(
                    select(LLMProviderConfig.id).where(
                        LLMProviderConfig.brand_id == brand_id,
                        LLMProviderConfig.name == values["name"],
                        LLMProviderConfig.id != provider_id,
                    )
                )
                if duplicate is not None:
                    raise ConflictError("模型服务名称已存在，请使用其他名称")
            api_key = values.pop("api_key", None)
            if api_key is not None:
                assert isinstance(api_key, SecretStr)
                provider.api_key_encrypted = self._cipher().encrypt(api_key.get_secret_value())
            for key, value in values.items():
                if key == "base_url":
                    value = str(value).rstrip("/")
                setattr(provider, key, value)
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="llm.provider_updated",
                resource_type="llm_provider_config",
                resource_id=provider.id,
                details={"fields": sorted(data.model_fields_set)},
            )
            # Load server/on-update timestamps before committing and serializing the ORM row.
            await self.session.flush()
            await self.session.refresh(provider)
        return provider

    async def upsert_binding(
        self,
        *,
        brand_id: uuid.UUID,
        purpose: str,
        actor_id: uuid.UUID,
        data: AgentLLMBindingUpsert,
    ) -> AgentLLMBinding:
        if purpose not in MANAGED_LLM_PURPOSES:
            raise ValidationError("unsupported LLM purpose")
        async with self.session.begin():
            provider = await self.session.scalar(
                select(LLMProviderConfig).where(
                    LLMProviderConfig.id == data.provider_config_id,
                    LLMProviderConfig.brand_id == brand_id,
                )
            )
            if provider is None:
                raise ValidationError("provider does not belong to current brand")
            binding = await self.session.scalar(
                select(AgentLLMBinding)
                .where(AgentLLMBinding.brand_id == brand_id, AgentLLMBinding.purpose == purpose)
                .with_for_update()
            )
            if binding is None:
                binding = AgentLLMBinding(
                    brand_id=brand_id,
                    purpose=purpose,
                    provider_config_id=data.provider_config_id,
                    model_override=data.model_override,
                    created_by=actor_id,
                )
                self.session.add(binding)
            else:
                binding.provider_config_id = data.provider_config_id
                binding.model_override = data.model_override
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="llm.binding_upserted",
                resource_type="agent_llm_binding",
                resource_id=binding.id,
                details={"purpose": purpose, "provider_id": str(data.provider_config_id)},
            )
        return binding

    async def mark_test(
        self,
        *,
        brand_id: uuid.UUID,
        provider_id: uuid.UUID,
        status: str,
        message: str,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        async with self.session.begin():
            provider = await self.session.scalar(
                select(LLMProviderConfig).where(
                    LLMProviderConfig.id == provider_id,
                    LLMProviderConfig.brand_id == brand_id,
                )
            )
            if provider is None:
                raise NotFoundError("LLM provider not found")
            provider.last_tested_at = datetime.now(UTC)
            provider.last_test_status = status
            provider.last_test_message = message[:1000]
            if model is not None and latency_ms is not None:
                self.session.add(
                    LLMCallLog(
                        brand_id=brand_id,
                        run_id=None,
                        provider=provider.name,
                        model=model,
                        purpose="configuration_test",
                        prompt_revision_id=None,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        provider_request_id=provider_request_id,
                    )
                )
