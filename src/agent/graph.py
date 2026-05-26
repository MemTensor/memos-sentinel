"""LangGraph StateGraph — orchestrates all agent paths with observability."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from langgraph.graph import StateGraph, END
from langsmith import traceable

from src.agent.state import AgentState

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Build the Sentinel orchestrator graph.

    Paths:
    - classify: new issue → label + ai-task decision
    - pr_review: PR opened → Opus review
    - dev: ai-task → analyze → fix → PR
    - fast: no-op acknowledgment
    """
    graph = StateGraph(AgentState)

    graph.add_node("route", route_node)
    graph.add_node("classify_issue", classify_issue_node)
    graph.add_node("review_pr", review_pr_node)
    graph.add_node("dev_agent", dev_agent_node)
    graph.add_node("fast_ack", fast_ack_node)
    graph.add_node("audit", audit_node)

    graph.set_entry_point("route")

    graph.add_conditional_edges(
        "route",
        lambda state: state.get("complexity", "ignore"),
        {
            "classify": "classify_issue",
            "pr_review": "review_pr",
            "dev": "dev_agent",
            "fast": "fast_ack",
            "ignore": END,
        },
    )

    graph.add_edge("classify_issue", "audit")
    graph.add_edge("review_pr", "audit")
    graph.add_edge("dev_agent", "audit")
    graph.add_edge("fast_ack", "audit")
    graph.add_edge("audit", END)

    return graph.compile()


@traceable(name="route")
async def route_node(state: AgentState) -> AgentState:
    """Determine which path to take based on event."""
    from src.agent.router import classify_complexity

    event = state.get("event", {})
    complexity = classify_complexity(event)

    state["complexity"] = complexity
    return state


@traceable(name="classify_issue")
async def classify_issue_node(state: AgentState) -> AgentState:
    """Classify a new issue and apply labels."""
    from src.agent.router import _handle_new_issue

    event = state.get("event", {})
    result = await _handle_new_issue(event)
    state["final_summary"] = result.get("summary", "")
    state["actions_taken"] = [result]
    return state


@traceable(name="review_pr")
async def review_pr_node(state: AgentState) -> AgentState:
    """Review a PR with Opus."""
    from src.agent.router import _handle_pr

    event = state.get("event", {})
    result = await _handle_pr(event)
    state["final_summary"] = result.get("summary", "")
    state["actions_taken"] = [result]
    return state


@traceable(name="dev_agent")
async def dev_agent_node(state: AgentState) -> AgentState:
    """Run the dev agent to fix an issue."""
    from src.agent.router import _handle_ai_task

    event = state.get("event", {})
    result = await _handle_ai_task(event)
    state["final_summary"] = result.get("summary", "")
    state["actions_taken"] = [result]
    return state


@traceable(name="fast_ack")
async def fast_ack_node(state: AgentState) -> AgentState:
    """Fast acknowledgment for simple events."""
    state["final_summary"] = "acknowledged"
    return state


@traceable(name="audit")
async def audit_node(state: AgentState) -> AgentState:
    """Log the action for audit purposes."""
    logger.info(f"Audit: {state.get('final_summary', 'no summary')}")
    return state


def setup_langsmith():
    """Configure LangSmith tracing if API key is available."""
    from src.agent.state import get_settings

    settings = get_settings()
    if settings.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info(f"LangSmith tracing enabled: project={settings.langsmith_project}")
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
