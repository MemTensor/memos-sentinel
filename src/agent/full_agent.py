"""Full Agent — 10-step LLM agent for PR review and complex issue handling."""

from __future__ import annotations

import logging
from src.agent.state import AgentState
from src.agent.human_gate import request_approval, ApprovalRequired

logger = logging.getLogger(__name__)

MAX_STEPS = 10


async def run_full_agent(state: AgentState) -> dict:
    """Run the full-power agent (Opus 4.6) for PR reviews and complex tasks."""
    from src.llm.client import get_heavy_model
    from src.tools.github_read import read_pr, get_pr_reviews, list_pr_checks

    event = state["event"]
    payload = event.get("payload", {})
    actions = []

    pr = payload.get("pull_request", {})
    if not pr:
        return {"summary": "full-agent: no PR in payload"}

    pr_number = pr["number"]

    # Step 1: Gather PR context
    pr_detail = await read_pr(pr_number)
    existing_reviews = await get_pr_reviews(pr_number)
    ci_status = await list_pr_checks(pr_number)

    # Step 2: LLM deep review
    model = get_heavy_model()
    review_result = await _generate_review(model, pr_detail, existing_reviews, ci_status)

    # Step 3: Post review comment
    if review_result.get("comment"):
        from src.tools.github_write import submit_review

        event_type = review_result.get("event", "COMMENT")

        if event_type == "APPROVE":
            await request_approval(
                action="approve_pr",
                target=pr_number,
                details=review_result["comment"],
            )

        await submit_review(pr_number, review_result["comment"], event_type)
        actions.append({
            "tool": "submit_review",
            "number": pr_number,
            "event": event_type,
        })

    # Step 4: Auto-label the PR
    pr_labels = _determine_pr_labels(pr_detail)
    if pr_labels:
        from src.tools.github_write import add_labels

        await add_labels(pr_number, pr_labels)
        actions.append({"tool": "add_labels", "number": pr_number, "labels": pr_labels})

    state["actions_taken"] = actions
    state["final_summary"] = f"full-agent: reviewed PR #{pr_number}"
    return {"summary": state["final_summary"], "actions": actions}


async def _generate_review(model, pr_detail: dict, reviews: list, ci: dict) -> dict:
    """Use Opus 4.6 to generate a thorough PR review."""
    # Placeholder — will be implemented with actual LangChain calls
    return {"comment": None, "event": "COMMENT"}


def _determine_pr_labels(pr_detail: dict) -> list[str]:
    """Determine labels for a PR based on changed files."""
    files = pr_detail.get("files", [])
    labels = []

    paths = [f.get("filename", "") for f in files]
    path_text = " ".join(paths)

    if any("plugin" in p or "adapter" in p for p in paths):
        labels.append("mod:plugin")
    if any("src/memos" in p or "core/" in p for p in paths):
        labels.append("mod:memos")
    if any("docs/" in p or "README" in p for p in paths):
        labels.append("mod:docs")
    if any(".github/" in p or "docker" in p or "deploy" in p for p in paths):
        labels.append("mod:infra")

    return labels
