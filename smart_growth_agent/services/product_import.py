from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.config import get_settings
from smart_growth_agent.db.models import LLMCallLog, RegistryItem, RegistryRevision
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.product_import import (
    ExtractedProductSource,
    ProductImportAIOutput,
    ProductImportDraft,
)
from smart_growth_agent.services.document_parser import (
    NativeDocumentParser,
    build_document_parser,
)
from smart_growth_agent.services.ingestion import IngestionDedupService

PROMPT_PRODUCT_IMPORT = "product_registry_import"
MAX_LLM_INPUT_CHARACTERS = 50_000
logger = logging.getLogger(__name__)


class ProductImportService:
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
        pasted_text: str,
        files: list[tuple[str, str, bytes]],
        actor_id: uuid.UUID = uuid.UUID(int=0),
    ) -> ProductImportDraft:
        sources: list[ExtractedProductSource] = []
        parse_reports = []
        if pasted_text.strip():
            sources.append(
                ExtractedProductSource(
                    name="运营人员粘贴内容",
                    media_type="text/plain",
                    text=pasted_text.strip(),
                )
            )
        parser = build_document_parser(get_settings())
        for filename, media_type, content in files:
            parsed = await parser.parse(
                filename=filename,
                media_type=media_type,
                content=content,
            )
            parse_reports.append(parsed.report)
            sources.append(
                ExtractedProductSource(
                    name=filename,
                    media_type=media_type,
                    text=parsed.render_for_llm(),
                )
            )
        if not sources:
            raise ValidationError("请粘贴产品资料或上传至少一个支持的文件")

        complete_sources = [source for source in sources if source.text.strip()]
        if not complete_sources:
            raise ValidationError("上传资料中没有提取到可分析的文字")
        source_text = "\n\n".join(source.text for source in complete_sources)
        if len(source_text) > MAX_LLM_INPUT_CHARACTERS:
            raise ValidationError(
                f"本次资料共提取 {len(source_text)} 个字符，超过单次 AI 整理上限 "
                f"{MAX_LLM_INPUT_CHARACTERS}；系统不会静默截断，请拆分资料后分批导入"
            )
        dedup_service = IngestionDedupService(self.session_factory)
        await dedup_service.preflight(
            brand_id=brand_id,
            ingestion_type="product",
            source_text=source_text,
        )

        async with self.session_factory() as session:
            prompt = await session.scalar(
                select(RegistryRevision)
                .join(RegistryItem, RegistryItem.current_revision_id == RegistryRevision.id)
                .where(
                    RegistryItem.brand_id == brand_id,
                    RegistryItem.registry_type == RegistryType.PROMPT_TEMPLATE,
                    RegistryItem.stable_key == PROMPT_PRODUCT_IMPORT,
                )
            )
        if prompt is None:
            raise ValidationError("缺少已激活的 product_registry_import Prompt")

        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                purpose="product_registry_import",
                prompt_revision_id=prompt.id,
                temperature=0.1,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "sources": [
                                    source.model_dump(mode="json")
                                    for source in complete_sources
                                ],
                                "governance": {
                                    "create_claims": False,
                                    "activate_revision": False,
                                    "unverified_facts_are_warnings": True,
                                },
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ],
            ),
            ProductImportAIOutput,
        )
        if not result.telemetry_logged:
            async with self.session_factory() as session, session.begin():
                session.add(
                LLMCallLog(
                    brand_id=brand_id,
                    run_id=None,
                    provider=result.provider,
                    model=result.model,
                    purpose="product_registry_import",
                    prompt_revision_id=prompt.id,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.latency_ms,
                    provider_request_id=result.provider_request_id,
                    )
                )
        dedup = None
        dedup_warnings: list[str] = []
        try:
            dedup = await dedup_service.analyze_product(
                brand_id=brand_id,
                actor_id=actor_id,
                source_text=source_text,
                source_uri=",".join(source.name for source in complete_sources),
                stable_key=result.value.stable_key,
                payload=result.value.payload.model_dump(mode="json"),
            )
        except SQLAlchemyError:
            # Deduplication is a governance aid. A transient persistence error after a
            # paid LLM call must not discard an otherwise valid editable draft.
            logger.exception("failed to persist product ingestion dedup analysis")
            dedup_warnings.append(
                "AI 草稿已生成，但重复内容检测记录暂时保存失败；"
                "保存产品前请人工确认系统中是否已有相同型号。"
            )
        parser_warnings = [
            notice.message
            for report in parse_reports
            for notice in report.notices
            if notice.severity in {"warning", "blocker"}
        ]
        return ProductImportDraft(
            **result.value.model_dump(
                exclude={"warnings"},
            ),
            warnings=[*result.value.warnings, *parser_warnings, *dedup_warnings],
            dedup=dedup,
            parse_reports=parse_reports,
        )

    @staticmethod
    def extract_text(filename: str, content: bytes) -> str:
        """Compatibility helper for callers that still require synchronous extraction."""
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            parsed = asyncio.run(
                NativeDocumentParser().parse(
                    filename=filename,
                    media_type="application/octet-stream",
                    content=content,
                )
            )
            return parsed.render_for_llm()
        raise RuntimeError("extract_text cannot run inside an event loop; use DocumentParser.parse")
