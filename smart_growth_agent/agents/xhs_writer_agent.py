from __future__ import annotations

from langgraph.runtime import Runtime

from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState
from smart_growth_agent.services.phase2 import Phase2Service


async def write_candidate(
    state: GrowthState, runtime: Runtime[GrowthRuntimeContext]
) -> dict:
    context = runtime.context
    route_key = state["route_key"]
    service = Phase2Service(
        context.session_factory, context.llm_gateway, context.research_gateway
    )
    candidate_id = await service.write_candidate(
        brand_id=state["brand_id"],
        run_id=state["run_id"],
        route_key=route_key,
    )
    return {"candidate_refs": {route_key: candidate_id}}


async def aggregate_candidates(state: GrowthState) -> dict:
    expected = state.get("creative_route_keys", [])
    refs = state.get("candidate_refs", {})
    if len(expected) != 3 or set(expected) != set(refs):
        raise RuntimeError("all three creative routes must produce a candidate")
    return {
        "candidate_ids": [refs[route_key] for route_key in expected],
        "gate_status": "content_draft_ready",
    }
