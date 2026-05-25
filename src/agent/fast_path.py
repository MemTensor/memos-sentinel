"""Fast path — rule-based actions that don't need LLM (stale, docs, simple labels)."""

from __future__ import annotations

import logging

from src.agent.state import AgentState

logger = logging.getLogger(__name__)


async def run_fast_path(state: AgentState) -> dict:
    """Execute simple rule-based actions without LLM invocation."""
    event = state["event"]
    actions = []

    event_type = event.get("type", "")
    action = event.get("action", "")
    payload = event.get("payload", {})

    if event_type == "issues" and action == "opened":
        labels = await _classify_by_rules(payload.get("issue", {}))
        if labels:
            state["labels_to_add"] = labels
            from src.tools.github_write import add_labels

            issue_number = payload["issue"]["number"]
            await add_labels(issue_number, labels)
            actions.append({"tool": "add_labels", "number": issue_number, "labels": labels})

    state["actions_taken"] = actions
    state["final_summary"] = f"fast-path: {len(actions)} actions"
    return {"summary": state["final_summary"], "actions": actions}


async def _classify_by_rules(issue: dict) -> list[str]:
    """Simple keyword-based classification for obvious cases."""
    title = (issue.get("title") or "").lower()
    body = (issue.get("body") or "").lower()
    text = f"{title} {body}"

    labels = []

    # Type detection
    if any(kw in text for kw in ("bug", "fix", "crash", "error", "broken", "fail")):
        labels.append("bug")
    elif any(kw in text for kw in ("feat", "add", "support", "request", "improve")):
        labels.append("enhancement")
    elif any(kw in text for kw in ("doc", "readme", "typo", "translate")):
        labels.append("documentation")

    # Module detection (simplified 4-module system)
    if any(kw in text for kw in ("plugin", "bridge", "viewer", "install.sh", "adapter", "hermes")):
        labels.append("mod:plugin")
    elif any(kw in text for kw in ("memory", "recall", "scheduler", "mcp", "hub", "schema")):
        labels.append("mod:memos")
    elif any(kw in text for kw in ("doc", "readme", "translate", "guide")):
        labels.append("mod:docs")
    elif any(kw in text for kw in ("ci", "docker", "deploy", "helm", "github action")):
        labels.append("mod:infra")

    return labels
