"""Light Agent — 3-step LLM agent for classification and simple replies."""

from __future__ import annotations

import logging
from src.agent.state import AgentState

logger = logging.getLogger(__name__)

MAX_STEPS = 3


async def run_light_agent(state: AgentState) -> dict:
    """Run a lightweight LLM agent (max 3 reasoning steps)."""
    from src.llm.client import get_light_model
    from src.labels.classifier import classify_issue
    from src.agent.duplicate_detector import find_duplicates

    event = state["event"]
    payload = event.get("payload", {})
    actions = []

    issue = payload.get("issue", {})
    if not issue:
        return {"summary": "light-agent: no issue in payload"}

    issue_number = issue["number"]

    # Step 1: Check for duplicates
    duplicates = await find_duplicates(issue)
    if duplicates:
        from src.tools.github_write import post_comment, add_labels

        comment = _format_duplicate_comment(duplicates)
        await post_comment(issue_number, comment)
        await add_labels(issue_number, ["duplicate"])
        actions.append({"tool": "mark_duplicate", "number": issue_number, "duplicates": duplicates})
        state["actions_taken"] = actions
        return {"summary": f"light-agent: marked duplicate of #{duplicates[0]}"}

    # Step 2: Classify with LLM
    labels = await classify_issue(issue)
    if labels:
        from src.tools.github_write import add_labels

        await add_labels(issue_number, labels)
        actions.append({"tool": "add_labels", "number": issue_number, "labels": labels})

    # Step 3: Generate reply if needed (question type)
    if "question" in labels:
        from src.agent.reply_engine import generate_reply

        reply = await generate_reply(issue)
        if reply:
            from src.tools.github_write import post_comment

            await post_comment(issue_number, reply)
            actions.append({"tool": "post_comment", "number": issue_number})

    state["actions_taken"] = actions
    state["final_summary"] = f"light-agent: classified with {labels}"
    return {"summary": state["final_summary"], "actions": actions}


def _format_duplicate_comment(duplicate_numbers: list[int]) -> str:
    refs = ", ".join(f"#{n}" for n in duplicate_numbers)
    return (
        f"This issue appears to be a duplicate of {refs}.\n\n"
        "If you believe this is different, please provide additional context "
        "and we'll re-evaluate. Closing as duplicate for now."
    )
