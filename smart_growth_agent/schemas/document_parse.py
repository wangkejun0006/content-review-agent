from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int | None = Field(default=None, ge=1)
    sheet_name: str | None = None
    cell_range: str | None = None
    table_index: int | None = Field(default=None, ge=1)
    row_index: int | None = Field(default=None, ge=1)

    def label(self) -> str:
        parts: list[str] = []
        if self.page_number is not None:
            parts.append(f"第{self.page_number}页")
        if self.sheet_name:
            parts.append(f"工作表：{self.sheet_name}")
        if self.cell_range:
            parts.append(f"单元格={self.cell_range}")
        if self.table_index is not None:
            parts.append(f"表格={self.table_index}")
        if self.row_index is not None:
            parts.append(f"行={self.row_index}")
        return "，".join(parts) or "文档"


class DocumentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    block_type: Literal["text", "table_row", "markdown"]
    text: str = Field(min_length=1)
    locator: SourceLocator = Field(default_factory=SourceLocator)


class ParseNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    severity: Literal["information", "warning", "blocker"]
    message: str = Field(min_length=1)


class DocumentParseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    media_type: str
    checksum: str = Field(min_length=64, max_length=64)
    parser_name: str
    parser_version: str
    character_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    complete: bool
    notices: list[ParseNotice] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: DocumentParseReport
    blocks: list[DocumentBlock] = Field(default_factory=list)

    def render_for_llm(self) -> str:
        return "\n".join(
            f"[source_block={block.block_id}; {block.locator.label()}]\n{block.text}"
            for block in self.blocks
        )
