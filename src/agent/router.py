"""Router — classifies event complexity and dispatches to appropriate agent path."""

from __future__ import annotations

import asyncio
import logging

from src.agent.state import AgentState, get_settings
from src.agent.concurrency import acquire_lock, release_lock

logger = logging.getLogger(__name__)


async def dispatch_event(event: dict) -> dict:
    """Entry point: route a GitHub event to the correct agent path."""
    settings = get_settings()

    lock_key = _compute_lock_key(event)
    if lock_key and not await acquire_lock(lock_key):
        logger.warning(f"Skipped duplicate/concurrent event: {lock_key}")
        return {"summary": "skipped: concurrent lock", "lock_key": lock_key}

    try:
        complexity = classify_complexity(event)
        state: AgentState = {
            "event": event,
            "complexity": complexity,
            "labels_to_add": [],
            "labels_to_remove": [],
            "messages": [],
            "actions_taken": [],
            "pending_approval": None,
            "dev_context": None,
            "final_summary": "",
            "error": None,
            "retry_count": 0,
            "lock_key": lock_key,
        }

        if settings.dry_run:
            logger.info(f"[DRY-RUN] Would dispatch {complexity} for event: {event.get('type')}")
            return {"summary": f"dry-run: {complexity}", "state": state}

        match complexity:
            case "fast":
                from src.agent.fast_path import run_fast_path
                return await run_fast_path(state)
            case "light":
                from src.agent.light_agent import run_light_agent
                return await run_light_agent(state)
            case "full":
                from src.agent.full_agent import run_full_agent
                return await run_full_agent(state)
            case "dev":
                from src.agent.dev_agent import run_dev_agent
                return await run_dev_agent(state)
            case _:
                return {"summary": f"unknown complexity: {complexity}"}
    finally:
        if lock_key:
            await release_lock(lock_key)


def classify_complexity(event: dict) -> str:
    """Four-tier routing based on event type and context."""
    event_type = event.get("type", "")
    action = event.get("action", "")
    payload = event.get("payload", {})

    # ai-task label → dev path
    if event_type == "issues" and action == "labeled":
        label_name = payload.get("label", {}).get("name", "")
        if label_name == "ai-task":
            return "dev"

    # PR opened/synchronized → full review
    if event_type == "pull_request" and action in ("opened", "synchronize"):
        return "full"

    # Issue opened → light classification
    if event_type == "issues" and action == "opened":
        return "light"

    # Issue comment → light reply
    if event_type == "issue_comment" and action == "created":
        return "light"

    # Stale/docs-only → fast path
    if event_type == "issues" and action in ("closed", "deleted"):
        return "fast"

    return "light"


def _compute_lock_key(event: dict) -> str | None:
    """Generate a unique lock key to prevent duplicate processing."""
    event_type = event.get("type", "")
    payload = event.get("payload", {})

    number = None
    for key in ("issue", "pull_request"):
        if key in payload:
            number = payload[key].get("number")
            break

    if number is None:
        return None

    return f"{event_type}:{number}"
