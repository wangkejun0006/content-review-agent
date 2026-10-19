from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import LLMCallLog, RegistryItem, RegistryRevision
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.document_parse import DocumentParseReport
from smart_growth_agent.schemas.evidence_import import (
    EvidenceImportAIOutput,
    EvidenceImportDraft,
)
from smart_growth_agent.services.ingestion import IngestionDedupService

PROMPT_EVIDENCE_IMPORT = "evidence_registry_import"
MAX_EVIDENCE_CHARACTERS = 50_000


class EvidenceImportService:
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
        source_uri: str,
        source_text: str,
        source_name: str,
        actor_id: uuid.UUID = uuid.UUID(int=0),
        parse_reports: list[DocumentParseReport] | None = None,
    ) -> EvidenceImportDraft:
        if not source_uri.strip():
            raise ValidationError("请填写可追溯的文件位置或来源 URL")
        if not source_text.strip():
            raise ValidationError("请粘贴证据原文或上传一个支持的文件")
        content = source_text.strip()
        if len(content) > MAX_EVIDENCE_CHARACTERS:
            raise ValidationError(
                f"证据原文共 {len(content)} 个字符，超过单次 AI 整理上限 "
                f"{MAX_EVIDENCE_CHARACTERS}；系统不会静默截断，请拆分文件后导入"
            )
        dedup_service = IngestionDedupService(self.session_factory)
        await dedup_service.preflight(
            brand_id=brand_id,
            ingestion_type="evidence",
            source_text=content,
        )
        async with self.session_factory() as session:
            prompt = await session.scalar(
                select(RegistryRevision)
                .join(RegistryItem, RegistryItem.current_revision_id == RegistryRevision.id)
                .where(
                    RegistryItem.brand_id == brand_id,
                    RegistryItem.registry_type == RegistryType.PROMPT_TEMPLATE,
                    RegistryItem.stable_key == PROMPT_EVIDENCE_IMPORT,
                )
            )
        if prompt is None:
            raise ValidationError("缺少已激活的 evidence_registry_import Prompt")

        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                purpose=PROMPT_EVIDENCE_IMPORT,
                prompt_revision_id=prompt.id,
                temperature=0.1,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "source_name": source_name,
                                "source_uri": source_uri,
                                "source_text": content,
                                "governance": {
                                    "preserve_original_content": True,
                                    "verify_document": False,
                                    "create_claims": False,
                                },
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ],
            ),
            EvidenceImportAIOutput,
        )
        invalid_excerpts = [
            excerpt
            for excerpt in result.value.relevant_excerpts
            if excerpt.strip() not in content
        ]
        if invalid_excerpts:
            raise ValidationError(
                "AI 返回的证据摘录无法在原文中定位，本次结果未生成；请重试或人工整理"
            )
        if not result.telemetry_logged:
            async with self.session_factory() as session, session.begin():
                session.add(
                LLMCallLog(
                    brand_id=brand_id,
                    provider=result.provider,
                    model=result.model,
                    purpose=PROMPT_EVIDENCE_IMPORT,
                    prompt_revision_id=prompt.id,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.latency_ms,
                    provider_request_id=result.provider_request_id,
                    )
                )
        dedup = await dedup_service.analyze_evidence(
            brand_id=brand_id,
            actor_id=actor_id,
            source_text=content,
            source_uri=source_uri,
            title=result.value.title,
        )
        return EvidenceImportDraft(
            **result.value.model_dump(exclude={"warnings"}),
            warnings=[
                *result.value.warnings,
                *[
                    notice.message
                    for report in parse_reports or []
                    for notice in report.notices
                    if notice.severity in {"warning", "blocker"}
                ],
            ],
            source_uri=source_uri.strip(),
            content=content,
            dedup=dedup,
            parse_reports=parse_reports or [],
        )
