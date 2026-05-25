"""GitHub management write tools (6 tools)."""

from __future__ import annotations

import logging
from src.agent.retry import retryable
from src.agent.state import get_settings

logger = logging.getLogger(__name__)


@retryable(max_retries=2, base_delay=1.0)
async def add_labels(number: int, labels: list[str]) -> None:
    """Add labels to an issue or PR."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would add labels {labels} to #{number}")
        return
    logger.info(f"Adding labels {labels} to #{number}")
    # Implementation with PyGitHub / httpx


@retryable(max_retries=2, base_delay=1.0)
async def remove_labels(number: int, labels: list[str]) -> None:
    """Remove labels from an issue or PR."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would remove labels {labels} from #{number}")
        return
    logger.info(f"Removing labels {labels} from #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def post_comment(number: int, body: str) -> None:
    """Post a comment on an issue or PR."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would comment on #{number}: {body[:80]}...")
        return
    logger.info(f"Posting comment on #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def submit_review(pr_number: int, body: str, event: str = "COMMENT") -> None:
    """Submit a PR review (COMMENT, APPROVE, REQUEST_CHANGES)."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would submit {event} review on PR #{pr_number}")
        return
    logger.info(f"Submitting {event} review on PR #{pr_number}")


@retryable(max_retries=2, base_delay=1.0)
async def close_issue(number: int, comment: str | None = None) -> None:
    """Close an issue with optional comment. REQUIRES APPROVAL."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would close issue #{number}")
        return
    if comment:
        await post_comment(number, comment)
    logger.info(f"Closing issue #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def close_pr(number: int, comment: str | None = None) -> None:
    """Close a PR with optional comment. REQUIRES APPROVAL."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would close PR #{number}")
        return
    if comment:
        await post_comment(number, comment)
    logger.info(f"Closing PR #{number}")
