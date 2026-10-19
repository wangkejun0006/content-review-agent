from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.config import Settings
from smart_growth_agent.llm.fake import DevelopmentFakeLLMGateway
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.managed import ManagedLLMGateway
from smart_growth_agent.llm.openai_compatible import OpenAICompatibleGateway
from smart_growth_agent.llm.policy import GovernedLLMGateway
from smart_growth_agent.llm.unavailable import UnavailableLLMGateway


def build_llm_gateway(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> LLMGateway:
    if settings.llm_mode == "fake":
        return GovernedLLMGateway(DevelopmentFakeLLMGateway(), session_factory)
    if settings.llm_mode == "openai_compatible":
        return GovernedLLMGateway(OpenAICompatibleGateway(settings), session_factory)
    if settings.llm_mode == "managed":
        return ManagedLLMGateway(session_factory, settings)
    return UnavailableLLMGateway()
