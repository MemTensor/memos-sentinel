"""GitHub read-only tools — real implementation using httpx + token."""

from __future__ import annotations

import logging
from typing import Any

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


@retryable(max_retries=3, base_delay=1.0)
async def read_issue(number: int) -> dict:
    """Read issue details including body and comments."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/issues/{number}",
            headers=_headers(),
        )
        resp.raise_for_status()
        issue = resp.json()

        comments_resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/issues/{number}/comments",
            headers=_headers(),
            params={"per_page": 30},
        )
        comments_resp.raise_for_status()
        issue["comments_data"] = comments_resp.json()

    return issue


@retryable(max_retries=3, base_delay=1.0)
async def read_pr(number: int) -> dict:
    """Read PR details including diff and changed files."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/pulls/{number}",
            headers=_headers(),
        )
        resp.raise_for_status()
        pr = resp.json()

        files_resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/pulls/{number}/files",
            headers=_headers(),
            params={"per_page": 100},
        )
        files_resp.raise_for_status()
        pr["files"] = files_resp.json()

        diff_resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/pulls/{number}",
            headers={**_headers(), "Accept": "application/vnd.github.diff"},
        )
        if diff_resp.status_code == 200:
            pr["diff"] = diff_resp.text[:50000]

    return pr


@retryable(max_retries=3, base_delay=1.0)
async def read_file(path: str, ref: str = "main") -> str:
    """Read a file from the repository."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/contents/{path}",
            headers=_headers(),
            params={"ref": ref},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("encoding") == "base64":
            import base64
            return base64.b64decode(data["content"]).decode("utf-8")
        return data.get("content", "")


@retryable(max_retries=3, base_delay=1.0)
async def search_issues(
    query: str = "",
    state: str = "open",
    labels: list[str] | None = None,
) -> list[dict]:
    """Search issues with optional filters."""
    q_parts = [f"repo:{_repo()}", f"is:{state}", "is:issue"]
    if query:
        q_parts.append(query)
    if labels:
        for l in labels:
            q_parts.append(f"label:{l}")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/search/issues",
            headers=_headers(),
            params={"q": " ".join(q_parts), "per_page": 30},
        )
        resp.raise_for_status()
        return resp.json().get("items", [])


@retryable(max_retries=3, base_delay=1.0)
async def search_code(query: str) -> list[dict]:
    """Search code in the repository."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/search/code",
            headers=_headers(),
            params={"q": f"{query} repo:{_repo()}", "per_page": 20},
        )
        resp.raise_for_status()
        return resp.json().get("items", [])


@retryable(max_retries=3, base_delay=1.0)
async def list_pr_checks(number: int) -> dict:
    """Get CI/check status for a PR."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/commits/{number}/check-runs",
            headers=_headers(),
        )
        if resp.status_code == 422:
            pr_resp = await client.get(
                f"{GITHUB_API}/repos/{_repo()}/pulls/{number}",
                headers=_headers(),
            )
            pr_resp.raise_for_status()
            sha = pr_resp.json().get("head", {}).get("sha", "")
            resp = await client.get(
                f"{GITHUB_API}/repos/{_repo()}/commits/{sha}/check-runs",
                headers=_headers(),
            )
        resp.raise_for_status()
        data = resp.json()
        runs = data.get("check_runs", [])
        passed = all(r.get("conclusion") == "success" for r in runs) if runs else False
        return {
            "total": len(runs),
            "passed": passed,
            "conclusion": "success" if passed else "pending",
            "runs": [{"name": r["name"], "status": r["status"], "conclusion": r.get("conclusion")} for r in runs],
        }


@retryable(max_retries=3, base_delay=1.0)
async def get_pr_reviews(number: int) -> list[dict]:
    """Get existing reviews for a PR."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/pulls/{number}/reviews",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


@retryable(max_retries=3, base_delay=1.0)
async def list_open_issues(label: str | None = None, since_days: int | None = None) -> list[dict]:
    """List all open issues with optional filters."""
    params: dict[str, Any] = {"state": "open", "per_page": 100}
    if label:
        params["labels"] = label
    if since_days:
        from datetime import datetime, timedelta
        since = (datetime.utcnow() - timedelta(days=since_days)).isoformat() + "Z"
        params["since"] = since

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/issues",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()
        return [i for i in resp.json() if "pull_request" not in i]


@retryable(max_retries=3, base_delay=1.0)
async def list_open_prs() -> list[dict]:
    """List all open PRs."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{_repo()}/pulls",
            headers=_headers(),
            params={"state": "open", "per_page": 100},
        )
        resp.raise_for_status()
        return resp.json()
