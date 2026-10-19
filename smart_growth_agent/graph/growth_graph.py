from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from smart_growth_agent.agents.compliance_agent import (
    review_candidate_compliance,
)
from smart_growth_agent.agents.human_review_agent import (
    apply_human_edit,
    apply_requested_changes,
    approve_content,
    human_edit_approved,
    human_review,
    prepare_human_review,
    reject_content,
    route_after_human_edit,
    route_review_decision,
)
from smart_growth_agent.agents.product_agent import (
    build_policy_context,
    build_product_context,
    build_trend_context,
    check_knowledge_freshness,
)
from smart_growth_agent.agents.scoring_agent import aggregate_quality
from smart_growth_agent.agents.strategy_agent import generate_strategy
from smart_growth_agent.agents.xhs_writer_agent import aggregate_candidates, write_candidate
from smart_growth_agent.graph.runtime import GrowthRuntimeContext
from smart_growth_agent.graph.state import GrowthState


def build_growth_graph(checkpointer: Any = None) -> Any:
    """Build the Phase 2 draft-generation graph."""
    builder = StateGraph(GrowthState, context_schema=GrowthRuntimeContext)
    builder.add_node("check_knowledge_freshness", check_knowledge_freshness)
    builder.add_node("build_product_context", build_product_context)
    builder.add_node("build_policy_context", build_policy_context)
    builder.add_node("build_trend_context", build_trend_context)
    builder.add_node("generate_strategy", generate_strategy)
    builder.add_node("write_candidate", write_candidate)
    builder.add_node("aggregate_candidates", aggregate_candidates)
    builder.add_node("review_candidate_compliance", review_candidate_compliance)
    builder.add_node("aggregate_quality", aggregate_quality)
    builder.add_node("prepare_human_review", prepare_human_review)
    builder.add_node("human_review", human_review)
    builder.add_node("approve_content", approve_content)
    builder.add_node("reject_content", reject_content)
    builder.add_node("apply_requested_changes", apply_requested_changes)
    builder.add_node("apply_human_edit", apply_human_edit)
    builder.add_node("human_edit_approved", human_edit_approved)
    builder.add_edge(START, "check_knowledge_freshness")
    builder.add_conditional_edges(
        "check_knowledge_freshness",
        lambda state: END
        if state.get("gate_status") == "waiting_knowledge_review"
        else "build_product_context",
    )
    builder.add_edge("build_product_context", "build_policy_context")
    builder.add_edge("build_policy_context", "build_trend_context")
    builder.add_edge("build_trend_context", "generate_strategy")
    builder.add_conditional_edges(
        "generate_strategy",
        lambda state: [
            Send(
                "write_candidate",
                {
                    "run_id": state["run_id"],
                    "brand_id": state["brand_id"],
                    "brief_id": state["brief_id"],
                    "registry_revision_ids": state["registry_revision_ids"],
                    "route_key": route_key,
                },
            )
            for route_key in state["creative_route_keys"]
        ],
    )
    builder.add_edge("write_candidate", "aggregate_candidates")
    builder.add_conditional_edges(
        "aggregate_candidates",
        lambda state: [
            Send(
                "review_candidate_compliance",
                {
                    "run_id": state["run_id"],
                    "brand_id": state["brand_id"],
                    "candidate_id": candidate_id,
                },
            )
            for candidate_id in state["candidate_ids"]
        ],
    )
    builder.add_edge("review_candidate_compliance", "aggregate_quality")
    builder.add_edge("aggregate_quality", "prepare_human_review")
    builder.add_edge("prepare_human_review", "human_review")
    builder.add_conditional_edges("human_review", route_review_decision)
    builder.add_edge("apply_requested_changes", "aggregate_quality")
    builder.add_conditional_edges("apply_human_edit", route_after_human_edit)
    builder.add_edge("approve_content", END)
    builder.add_edge("reject_content", END)
    builder.add_edge("human_edit_approved", END)
    return builder.compile(checkpointer=checkpointer)
