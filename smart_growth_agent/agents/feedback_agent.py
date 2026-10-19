from __future__ import annotations

from langgraph.runtime import Runtime

from smart_growth_agent.graph.feedback_state import FeedbackState
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.services.feedback import FeedbackService


async def generate_feedback(
    state: FeedbackState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    context = runtime.context
    recommendation_id, insight_revision_id = await FeedbackService(
        context.session_factory,
        context.llm_gateway,
    ).generate(
        brand_id=state["brand_id"],
        feedback_run_id=state["feedback_run_id"],
    )
    return {
        "recommendation_id": recommendation_id,
        "strategy_insight_revision_id": insight_revision_id,
        "gate_status": "feedback_ready",
    }
