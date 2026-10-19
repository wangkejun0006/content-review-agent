from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import HttpUrl, TypeAdapter

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.platform_rule_import import PlatformRuleImportDraft
from smart_growth_agent.services.document_parser import build_document_parser
from smart_growth_agent.services.platform_rule_import import PlatformRuleImportService

router = APIRouter(tags=["platform-rule-import"])


@router.post("/registry/platform_rule/ai-drafts", response_model=PlatformRuleImportDraft)
async def create_platform_rule_ai_draft(
    source_url: str = Form(),
    verified_at: datetime = Form(),
    pasted_text: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("registry:write")),
) -> PlatformRuleImportDraft:
    TypeAdapter(HttpUrl).validate_python(source_url)
    source_text = pasted_text.strip()
    parse_reports = []
    if file is not None:
        content = await file.read(15 * 1024 * 1024 + 1)
        if len(content) > 15 * 1024 * 1024:
            raise ValidationError("规则文件超过 15 MB")
        parsed = await build_document_parser(settings).parse(
            filename=file.filename or "rule.txt",
            media_type=file.content_type or "application/octet-stream",
            content=content,
        )
        parse_reports.append(parsed.report)
        source_text = "\n\n".join(
            part
            for part in [
                source_text,
                parsed.render_for_llm(),
            ]
            if part
        )
    gateway = build_llm_gateway(settings, SessionFactory)
    try:
        return await PlatformRuleImportService(SessionFactory, gateway).create_draft(
            brand_id=principal.brand_id,
            source_text=source_text,
            source_url=source_url,
            verified_at=verified_at,
            actor_id=principal.user_id,
            parse_reports=parse_reports,
        )
    finally:
        if hasattr(gateway, "aclose"):
            await gateway.aclose()
