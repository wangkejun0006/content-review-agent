from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import LLMCallLog, RegistryItem, RegistryRevision
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.document_parse import DocumentParseReport
from smart_growth_agent.schemas.platform_rule_import import (
    PlatformRuleAIOutput,
    PlatformRuleImportDraft,
)
from smart_growth_agent.services.ingestion import IngestionDedupService

PROMPT_PLATFORM_RULE_IMPORT = "platform_rule_import"


class PlatformRuleImportService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_gateway: LLMGateway,
    ) -> None:
        self.session_factory = session_factory
        self.llm_gateway = llm_gateway

    async def create_draft(
        self,
        *,
        brand_id: uuid.UUID,
        source_text: str,
        source_url: str,
        verified_at: datetime,
        actor_id: uuid.UUID = uuid.UUID(int=0),
        parse_reports: list[DocumentParseReport] | None = None,
    ) -> PlatformRuleImportDraft:
        if not source_text.strip():
            raise ValidationError("请粘贴或上传已阅读的规则原文")
        if len(source_text) > 50_000:
            raise ValidationError(
                f"规则原文共 {len(source_text)} 个字符，超过单次 AI 整理上限 50000；"
                "系统不会静默截断，请按规则章节拆分后导入"
            )
        dedup_service = IngestionDedupService(self.session_factory)
        await dedup_service.preflight(
            brand_id=brand_id,
            ingestion_type="platform_rule",
            source_text=source_text,
        )
        async with self.session_factory() as session:
            prompt = await session.scalar(
                select(RegistryRevision)
                .join(RegistryItem, RegistryItem.current_revision_id == RegistryRevision.id)
                .where(
                    RegistryItem.brand_id == brand_id,
                    RegistryItem.registry_type == RegistryType.PROMPT_TEMPLATE,
                    RegistryItem.stable_key == PROMPT_PLATFORM_RULE_IMPORT,
                )
            )
        if prompt is None:
            raise ValidationError("缺少已激活的 platform_rule_import Prompt")
        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                purpose="platform_rule_import",
                prompt_revision_id=prompt.id,
                temperature=0.1,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "source_text": source_text,
                                "source_url": source_url,
                                "verified_at": verified_at.isoformat(),
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ],
            ),
            PlatformRuleAIOutput,
        )
        value = result.value
        if value.source_excerpt.strip() not in source_text:
            raise ValidationError(
                "AI 返回的规则引用无法在原文中定位，本次结果未生成；请重试或人工整理"
            )
        if not result.telemetry_logged:
            async with self.session_factory() as session, session.begin():
                session.add(
                LLMCallLog(
                    brand_id=brand_id,
                    provider=result.provider,
                    model=result.model,
                    purpose="platform_rule_import",
                    prompt_revision_id=prompt.id,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.latency_ms,
                    provider_request_id=result.provider_request_id,
                    )
                )
        dedup = await dedup_service.analyze_platform_rule(
            brand_id=brand_id,
            actor_id=actor_id,
            source_text=source_text,
            source_uri=source_url,
            stable_key=value.stable_key,
            rule_text=value.rule_text,
        )
        return PlatformRuleImportDraft(
            stable_key=value.stable_key,
            payload={
                "platform": "xhs",
                "category": value.category,
                "rule_text": value.rule_text,
                "severity": value.severity,
                "source_url": source_url,
                "effective_from": None,
                "verified_at": verified_at.isoformat(),
            },
            search_text=value.rule_text,
            confidence=value.confidence,
            source_excerpt=value.source_excerpt,
            warnings=[
                *value.warnings,
                *[
                    notice.message
                    for report in parse_reports or []
                    for notice in report.notices
                    if notice.severity in {"warning", "blocker"}
                ],
            ],
            dedup=dedup,
            parse_reports=parse_reports or [],
        )
