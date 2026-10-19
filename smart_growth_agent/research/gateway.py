from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from smart_growth_agent.schemas.phase2 import TrendResearchOutput


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_id: uuid.UUID
    run_id: uuid.UUID
    product_keywords: list[str] = Field(default_factory=list)
    audience_keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    time_window_days: int = Field(default=7, ge=1, le=90)


class ResearchGateway(Protocol):
    async def research(self, request: ResearchRequest) -> TrendResearchOutput: ...


class NullResearchGateway:
    async def research(self, request: ResearchRequest) -> TrendResearchOutput:
        del request
        return TrendResearchOutput(
            limitations=[
                "未配置网页搜索或平台官方 API；本次策略不包含实时热点观察。"
            ]
        )
