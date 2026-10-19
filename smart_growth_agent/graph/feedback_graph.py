from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from smart_growth_agent.agents.feedback_agent import generate_feedback
from smart_growth_agent.graph.feedback_state import FeedbackState
from smart_growth_agent.graph.runtime import GrowthRuntimeContext


def build_feedback_graph(checkpointer: Any = None) -> Any:
    builder = StateGraph(FeedbackState, context_schema=GrowthRuntimeContext)
    builder.add_node("generate_feedback", generate_feedback)
    builder.add_edge(START, "generate_feedback")
    builder.add_edge("generate_feedback", END)
    return builder.compile(checkpointer=checkpointer)
