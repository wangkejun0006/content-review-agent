from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.evidence_import import EvidenceImportDraft
from smart_growth_agent.services.document_parser import build_document_parser
from smart_growth_agent.services.evidence_import import EvidenceImportService

router = APIRouter(tags=["evidence-import"])
MAX_FILE_BYTES = 15 * 1024 * 1024


@router.post("/evidence/ai-drafts", response_model=EvidenceImportDraft)
async def create_evidence_ai_draft(
    source_uri: str = Form(),
    pasted_text: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("registry:write")),
) -> EvidenceImportDraft:
    source_text = pasted_text.strip()
    source_name = "运营人员粘贴内容"
    parse_reports = []
    if file is not None:
        content = await file.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise ValidationError("证据文件超过 15 MB")
        source_name = file.filename or "未命名证据文件"
        parsed = await build_document_parser(settings).parse(
            filename=source_name,
            media_type=file.content_type or "application/octet-stream",
            content=content,
        )
        parse_reports.append(parsed.report)
        source_text = "\n\n".join(
            part for part in [source_text, parsed.render_for_llm()] if part
        )
    gateway = build_llm_gateway(settings, SessionFactory)
    try:
        return await EvidenceImportService(SessionFactory, gateway).create_draft(
            brand_id=principal.brand_id,
            source_uri=source_uri,
            source_text=source_text,
            source_name=source_name,
            actor_id=principal.user_id,
            parse_reports=parse_reports,
        )
    finally:
        if hasattr(gateway, "aclose"):
            await gateway.aclose()
