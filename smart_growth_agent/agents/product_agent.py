from __future__ import annotations

from langgraph.runtime import Runtime

from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState
from smart_growth_agent.services.phase2 import Phase2Service


def _service(runtime: Runtime[GrowthRuntimeContext]) -> Phase2Service:
    context = runtime.context
    return Phase2Service(
        context.session_factory,
        context.llm_gateway,
        context.research_gateway,
    )


async def check_knowledge_freshness(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    blocked, issues = await _service(runtime).check_knowledge_freshness(
        brand_id=state["brand_id"],
        run_id=state["run_id"],
    )
    if blocked:
        return {
            "gate_status": "waiting_knowledge_review",
            "errors": [{"code": "stale_critical_rules", "issues": issues}],
        }
    return {
        "gate_status": "knowledge_ready",
        "errors": ([{"code": "stale_rules_warning", "issues": issues}] if issues else []),
    }


async def build_product_context(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    package_id = await _service(runtime).build_product_context(
        brand_id=state["brand_id"], run_id=state["run_id"]
    )
    return {"product_context_package_id": package_id, "gate_status": "product_context_ready"}


async def build_policy_context(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    package_id = await _service(runtime).build_policy_context(
        brand_id=state["brand_id"], run_id=state["run_id"]
    )
    return {"policy_context_package_id": package_id, "gate_status": "policy_context_ready"}


async def build_trend_context(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    package_id = await _service(runtime).build_trend_context(
        brand_id=state["brand_id"], run_id=state["run_id"]
    )
    return {"trend_context_package_id": package_id, "gate_status": "trend_context_ready"}
