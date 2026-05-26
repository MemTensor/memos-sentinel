"""GitHub management write tools — uses shared client with rate limit handling."""

from __future__ import annotations

import logging

from src.agent.retry import retryable
from src.tools.github_client import github_request, _repo

logger = logging.getLogger(__name__)


@retryable(max_retries=2, base_delay=1.0)
async def add_labels(number: int, labels: list[str]) -> None:
    """Add labels to an issue or PR."""
    resp = await github_request(
        "POST", f"/repos/{_repo()}/issues/{number}/labels", json={"labels": labels}
    )
    resp.raise_for_status()
    logger.info(f"Added labels {labels} to #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def remove_labels(number: int, labels: list[str]) -> None:
    """Remove labels from an issue or PR."""
    for label in labels:
        resp = await github_request(
            "DELETE", f"/repos/{_repo()}/issues/{number}/labels/{label}"
        )
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
    logger.info(f"Removed labels {labels} from #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def post_comment(number: int, body: str) -> dict:
    """Post a comment on an issue or PR."""
    resp = await github_request(
        "POST", f"/repos/{_repo()}/issues/{number}/comments", json={"body": body}
    )
    resp.raise_for_status()
    logger.info(f"Posted comment on #{number}")
    return resp.json()


@retryable(max_retries=2, base_delay=1.0)
async def submit_review(pr_number: int, body: str, event: str = "COMMENT") -> dict:
    """Submit a PR review (COMMENT, APPROVE, REQUEST_CHANGES)."""
    resp = await github_request(
        "POST", f"/repos/{_repo()}/pulls/{pr_number}/reviews",
        json={"body": body, "event": event},
    )
    resp.raise_for_status()
    logger.info(f"Submitted {event} review on PR #{pr_number}")
    return resp.json()


@retryable(max_retries=2, base_delay=1.0)
async def close_issue(number: int, comment: str | None = None) -> None:
    """Close an issue with optional comment."""
    if comment:
        await post_comment(number, comment)
    resp = await github_request(
        "PATCH", f"/repos/{_repo()}/issues/{number}", json={"state": "closed"}
    )
    resp.raise_for_status()
    logger.info(f"Closed issue #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def close_pr(number: int, comment: str | None = None) -> None:
    """Close a PR with optional comment."""
    if comment:
        await post_comment(number, comment)
    resp = await github_request(
        "PATCH", f"/repos/{_repo()}/pulls/{number}", json={"state": "closed"}
    )
    resp.raise_for_status()
    logger.info(f"Closed PR #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def create_label(name: str, color: str, description: str = "") -> None:
    """Create a label in the repository."""
    resp = await github_request(
        "POST", f"/repos/{_repo()}/labels",
        json={"name": name, "color": color, "description": description},
    )
    if resp.status_code == 422:
        logger.info(f"Label '{name}' already exists")
        return
    resp.raise_for_status()
    logger.info(f"Created label: {name}")
