from __future__ import annotations

from langgraph.runtime import Runtime
from sqlalchemy import select

from smart_growth_agent.db.models import StrategyPlan
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState
from smart_growth_agent.schemas.phase2 import StrategyOutput
from smart_growth_agent.services.phase2 import Phase2Service


async def generate_strategy(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    context = runtime.context
    service = Phase2Service(
        context.session_factory, context.llm_gateway, context.research_gateway
    )
    plan_id = await service.build_strategy(
        brand_id=state["brand_id"], run_id=state["run_id"]
    )
    async with context.session_factory() as session:
        plan = await session.scalar(select(StrategyPlan).where(StrategyPlan.id == plan_id))
        if plan is None:
            raise RuntimeError("persisted strategy plan is missing")
    output = StrategyOutput.model_validate(plan.payload)
    return {
        "strategy_plan_id": plan_id,
        "creative_route_keys": [route.route_key for route in output.creative_routes],
        "gate_status": "strategy_ready",
    }
