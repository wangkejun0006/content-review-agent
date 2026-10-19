from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile

from smart_growth_agent.app.dependencies import require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.llm.factory import build_llm_gateway
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.product_import import ProductImportDraft
from smart_growth_agent.services.product_import import ProductImportService

router = APIRouter(tags=["product-import"])
MIB = 1024 * 1024
MAX_FILES = 8
MAX_TOTAL_BYTES = 25 * MIB
FILE_LIMITS = {
    ".txt": 1 * MIB,
    ".md": 1 * MIB,
    ".pdf": 15 * MIB,
    ".docx": 15 * MIB,
    ".xlsx": 8 * MIB,
}


def validate_product_upload(filename: str, size: int) -> None:
    suffix = Path(filename).suffix.lower()
    limit = FILE_LIMITS.get(suffix)
    if limit is None:
        supported = "、".join(sorted(FILE_LIMITS))
        raise ValidationError(
            f"文件 {filename} 格式不支持；当前仅支持 {supported}。"
            "旧版 .xls 请先另存为 .xlsx。"
        )
    if size > limit:
        raise ValidationError(
            f"文件 {filename} 超过 {limit // MIB} MB；"
            "请压缩图片、删除无关工作表或拆分后再上传。"
        )


@router.post("/registry/product/ai-drafts", response_model=ProductImportDraft)
async def create_product_ai_draft(
    pasted_text: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("registry:write")),
) -> ProductImportDraft:
    if len(files) > MAX_FILES:
        raise ValidationError(f"单次最多上传 {MAX_FILES} 个文件")
    inputs: list[tuple[str, str, bytes]] = []
    total_bytes = 0
    for upload in files:
        filename = upload.filename or "未命名文件"
        suffix = Path(filename).suffix.lower()
        read_limit = FILE_LIMITS.get(suffix, max(FILE_LIMITS.values()))
        content = await upload.read(read_limit + 1)
        validate_product_upload(filename, len(content))
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValidationError(
                f"本次文件总大小超过 {MAX_TOTAL_BYTES // MIB} MB，请分批整理"
            )
        inputs.append(
            (
                filename,
                upload.content_type or "application/octet-stream",
                content,
            )
        )

    gateway = build_llm_gateway(settings, SessionFactory)
    try:
        return await ProductImportService(SessionFactory, gateway).create_draft(
            brand_id=principal.brand_id,
            pasted_text=pasted_text,
            files=inputs,
            actor_id=principal.user_id,
        )
    finally:
        if hasattr(gateway, "aclose"):
            await gateway.aclose()
