from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.research.gateway import ResearchGateway


@dataclass(frozen=True)
class GrowthRuntimeContext:
    session_factory: async_sessionmaker[AsyncSession]
    llm_gateway: LLMGateway
    research_gateway: ResearchGateway
