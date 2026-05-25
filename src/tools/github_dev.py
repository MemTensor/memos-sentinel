"""GitHub development tools (6 tools) — only triggered by ai-task."""

from __future__ import annotations

import logging
from src.agent.retry import retryable
from src.agent.state import get_settings

logger = logging.getLogger(__name__)


@retryable(max_retries=2, base_delay=2.0)
async def clone_repo(ref: str = "main") -> str:
    """Clone the target repository to a temporary directory."""
    settings = get_settings()
    logger.info(f"Cloning {settings.github_target_repo}@{ref}")
    # Implementation: git clone to temp dir
    return ""


@retryable(max_retries=2, base_delay=1.0)
async def create_branch(name: str, base: str = "main") -> None:
    """Create a new branch from the specified base."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would create branch {name} from {base}")
        return
    logger.info(f"Creating branch {name} from {base}")


@retryable(max_retries=2, base_delay=1.0)
async def edit_file(path: str, content: str) -> None:
    """Edit (create or update) a file in the working branch."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would edit file {path}")
        return
    logger.info(f"Editing file {path}")


@retryable(max_retries=2, base_delay=2.0)
async def commit_and_push(message: str) -> None:
    """Commit all changes and push to remote."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would commit and push: {message}")
        return
    logger.info(f"Committing and pushing: {message}")


@retryable(max_retries=2, base_delay=1.0)
async def create_pull_request(
    title: str,
    body: str,
    base: str = "main",
    head: str = "",
    draft: bool = True,
) -> dict:
    """Create a pull request (draft by default).

    Merge strategy: squash (configured in settings).
    """
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would create PR: {title}")
        return {"number": 0, "url": ""}
    logger.info(f"Creating PR: {title} ({head} → {base})")
    return {"number": 0, "url": ""}


@retryable(max_retries=3, base_delay=5.0)
async def trigger_ci(pr_number: int) -> None:
    """Trigger CI checks on a PR (re-run or push empty commit)."""
    settings = get_settings()
    if settings.dry_run:
        logger.info(f"[DRY-RUN] Would trigger CI on PR #{pr_number}")
        return
    logger.info(f"Triggering CI on PR #{pr_number}")
