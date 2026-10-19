"""Shared call contracts and provider-setting inheritance."""

from pydantic import BaseModel
from sqlalchemy import select

from smart_growth_agent.db.models import RegistryItem, RegistryRevision
from smart_growth_agent.domain.enums import RegistryType, RevisionStatus
from smart_growth_agent.llm.contracts import contract_mismatch
from smart_growth_agent.llm.openai_compatible import LLMGatewayError
from smart_growth_agent.schemas.llm_config import LLMProviderTestOutput


def validate_code_contract(request, response_model):
    if request.purpose == "configuration_test":
        if request.prompt_revision_id is not None:
            raise LLMGatewayError("配置测试不得引用业务 Prompt。")
        mismatch = None if response_model is LLMProviderTestOutput else "配置测试输出契约不匹配"
    else:
        mismatch = contract_mismatch(
            purpose=request.purpose,
            response_model=response_model,
            prompt_schema_name=response_model.__name__,
        )
    if mismatch:
        raise LLMGatewayError(mismatch + "；已在调用模型前停止。")


async def validate_registry_contract(session_factory, request, response_model):
    validate_code_contract(request, response_model)
    if request.purpose == "configuration_test":
        if request.prompt_revision_id is not None:
            raise LLMGatewayError("配置测试不得引用业务 Prompt。")
        return
    async with session_factory() as session:
        prompt = await session.scalar(
            select(RegistryRevision)
            .join(RegistryItem, RegistryItem.id == RegistryRevision.item_id)
            .where(
                RegistryRevision.id == request.prompt_revision_id,
                RegistryItem.brand_id == request.brand_id,
                RegistryItem.registry_type == RegistryType.PROMPT_TEMPLATE,
                RegistryItem.stable_key
                == (
                    "xhs_compliance"
                    if request.purpose == "xhs_compliance_semantic"
                    else request.purpose
                ),
                RegistryRevision.status.in_([RevisionStatus.ACTIVE, RevisionStatus.RETIRED]),
            )
        )
    if prompt is None or prompt.payload.get("purpose") != request.purpose:
        raise LLMGatewayError(
            "缺少匹配当前品牌和用途的已激活 Prompt Revision；已在调用模型前停止。"
        )
    mismatch = contract_mismatch(
        purpose=request.purpose,
        response_model=response_model,
        prompt_schema_name=prompt.payload.get("output_schema_name"),
    )
    if mismatch:
        raise LLMGatewayError(mismatch + "；已在调用模型前停止。")


def provider_settings(settings, *, base_url, api_key, model):
    # Inherit every policy field, including future fields, without reading a new .env.
    return settings.model_copy(
        update={
            "openai_base_url": base_url,
            "openai_api_key": api_key,
            "openai_model": model,
            "llm_mode": "openai_compatible",
        }
    )


class GovernedLLMGateway:
    def __init__(self, inner, session_factory):
        self.inner = inner
        self.session_factory = session_factory

    @property
    def is_fake(self):
        return getattr(self.inner, "is_fake", False)

    async def generate(self, request, response_model: type[BaseModel]):
        await validate_registry_contract(self.session_factory, request, response_model)
        return await self.inner.generate(request, response_model)

    async def aclose(self):
        close = getattr(self.inner, "aclose", None)
        if close is not None:
            await close()
