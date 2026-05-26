"""GitHub management write tools — real implementation using httpx + token."""

from __future__ import annotations

import logging

import httpx

from src.agent.state import get_settings
from src.agent.retry import retryable

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo() -> str:
    return get_settings().github_target_repo


@retryable(max_retries=2, base_delay=1.0)
async def add_labels(number: int, labels: list[str]) -> None:
    """Add labels to an issue or PR."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{_repo()}/issues/{number}/labels",
            headers=_headers(),
            json={"labels": labels},
        )
        resp.raise_for_status()
    logger.info(f"Added labels {labels} to #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def remove_labels(number: int, labels: list[str]) -> None:
    """Remove labels from an issue or PR."""
    async with httpx.AsyncClient(timeout=30) as client:
        for label in labels:
            resp = await client.delete(
                f"{GITHUB_API}/repos/{_repo()}/issues/{number}/labels/{label}",
                headers=_headers(),
            )
            if resp.status_code not in (200, 404):
                resp.raise_for_status()
    logger.info(f"Removed labels {labels} from #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def post_comment(number: int, body: str) -> dict:
    """Post a comment on an issue or PR."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{_repo()}/issues/{number}/comments",
            headers=_headers(),
            json={"body": body},
        )
        resp.raise_for_status()
    logger.info(f"Posted comment on #{number}")
    return resp.json()


@retryable(max_retries=2, base_delay=1.0)
async def submit_review(pr_number: int, body: str, event: str = "COMMENT") -> dict:
    """Submit a PR review (COMMENT, APPROVE, REQUEST_CHANGES)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{_repo()}/pulls/{pr_number}/reviews",
            headers=_headers(),
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
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{GITHUB_API}/repos/{_repo()}/issues/{number}",
            headers=_headers(),
            json={"state": "closed"},
        )
        resp.raise_for_status()
    logger.info(f"Closed issue #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def close_pr(number: int, comment: str | None = None) -> None:
    """Close a PR with optional comment."""
    if comment:
        await post_comment(number, comment)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{GITHUB_API}/repos/{_repo()}/pulls/{number}",
            headers=_headers(),
            json={"state": "closed"},
        )
        resp.raise_for_status()
    logger.info(f"Closed PR #{number}")


@retryable(max_retries=2, base_delay=1.0)
async def create_label(name: str, color: str, description: str = "") -> None:
    """Create a label in the repository."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{_repo()}/labels",
            headers=_headers(),
            json={"name": name, "color": color, "description": description},
        )
        if resp.status_code == 422:
            logger.info(f"Label '{name}' already exists")
            return
        resp.raise_for_status()
    logger.info(f"Created label: {name}")
