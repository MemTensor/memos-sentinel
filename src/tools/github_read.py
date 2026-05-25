"""GitHub read-only tools (9 tools)."""

from __future__ import annotations

import logging
from src.agent.retry import retryable

logger = logging.getLogger(__name__)


def _get_github():
    """Get authenticated GitHub client."""
    from src.agent.state import get_settings

    settings = get_settings()
    # Will use PyGitHub or httpx with GitHub App auth
    # Placeholder for actual implementation
    return None


@retryable(max_retries=3, base_delay=1.0)
async def read_issue(number: int) -> dict:
    """Read issue details including body and comments."""
    logger.info(f"Reading issue #{number}")
    # Placeholder
    return {}


@retryable(max_retries=3, base_delay=1.0)
async def read_pr(number: int) -> dict:
    """Read PR details including diff and changed files."""
    logger.info(f"Reading PR #{number}")
    return {}


@retryable(max_retries=3, base_delay=1.0)
async def read_file(path: str, ref: str = "main") -> str:
    """Read a file from the repository."""
    logger.info(f"Reading file {path}@{ref}")
    return ""


@retryable(max_retries=3, base_delay=1.0)
async def search_issues(
    query: str = "",
    state: str = "open",
    labels: list[str] | None = None,
) -> list[dict]:
    """Search issues with optional filters."""
    logger.info(f"Searching issues: query={query}, state={state}")
    return []


@retryable(max_retries=3, base_delay=1.0)
async def search_code(query: str) -> list[dict]:
    """Search code in the repository."""
    logger.info(f"Searching code: {query}")
    return []


@retryable(max_retries=3, base_delay=1.0)
async def list_pr_checks(number: int) -> dict:
    """Get CI/check status for a PR."""
    logger.info(f"Getting checks for PR #{number}")
    return {}


@retryable(max_retries=3, base_delay=1.0)
async def get_pr_reviews(number: int) -> list[dict]:
    """Get existing reviews for a PR."""
    logger.info(f"Getting reviews for PR #{number}")
    return []


@retryable(max_retries=3, base_delay=1.0)
async def list_open_issues(label: str | None = None, since_days: int | None = None) -> list[dict]:
    """List all open issues with optional filters."""
    logger.info(f"Listing open issues (label={label}, since_days={since_days})")
    return []


@retryable(max_retries=3, base_delay=1.0)
async def list_open_prs() -> list[dict]:
    """List all open PRs."""
    logger.info("Listing open PRs")
    return []
