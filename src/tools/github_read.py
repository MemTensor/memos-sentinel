"""GitHub read-only tools — uses shared client with rate limit handling."""

from __future__ import annotations

import logging
from typing import Any

from src.agent.retry import retryable
from src.tools.github_client import github_request, _repo, _headers, GITHUB_API

logger = logging.getLogger(__name__)


@retryable(max_retries=3, base_delay=1.0)
async def read_issue(number: int) -> dict:
    """Read issue details including body and comments."""
    resp = await github_request("GET", f"/repos/{_repo()}/issues/{number}")
    resp.raise_for_status()
    issue = resp.json()

    comments_resp = await github_request(
        "GET", f"/repos/{_repo()}/issues/{number}/comments", params={"per_page": 30}
    )
    comments_resp.raise_for_status()
    issue["comments_data"] = comments_resp.json()

    return issue


@retryable(max_retries=3, base_delay=1.0)
async def read_pr(number: int) -> dict:
    """Read PR details including diff and changed files."""
    resp = await github_request("GET", f"/repos/{_repo()}/pulls/{number}")
    resp.raise_for_status()
    pr = resp.json()

    files_resp = await github_request(
        "GET", f"/repos/{_repo()}/pulls/{number}/files", params={"per_page": 100}
    )
    files_resp.raise_for_status()
    pr["files"] = files_resp.json()

    diff_headers = {**_headers(), "Accept": "application/vnd.github.diff"}
    diff_resp = await github_request(
        "GET", f"/repos/{_repo()}/pulls/{number}", headers_override=diff_headers
    )
    if diff_resp.status_code == 200:
        pr["diff"] = diff_resp.text[:50000]

    return pr


@retryable(max_retries=3, base_delay=1.0)
async def read_file(path: str, ref: str = "main") -> str:
    """Read a file from the repository."""
    resp = await github_request(
        "GET", f"/repos/{_repo()}/contents/{path}", params={"ref": ref}
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

    resp = await github_request(
        "GET", "/search/issues", params={"q": " ".join(q_parts), "per_page": 30}
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


@retryable(max_retries=3, base_delay=1.0)
async def search_code(query: str) -> list[dict]:
    """Search code in the repository."""
    resp = await github_request(
        "GET", "/search/code", params={"q": f"{query} repo:{_repo()}", "per_page": 20}
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


@retryable(max_retries=3, base_delay=1.0)
async def list_pr_checks(number: int) -> dict:
    """Get CI/check status for a PR."""
    # First get the PR to find HEAD sha
    pr_resp = await github_request("GET", f"/repos/{_repo()}/pulls/{number}")
    if pr_resp.status_code != 200:
        return {"total": 0, "passed": False, "conclusion": "unknown", "runs": []}

    sha = pr_resp.json().get("head", {}).get("sha", "")
    if not sha:
        return {"total": 0, "passed": False, "conclusion": "unknown", "runs": []}

    resp = await github_request("GET", f"/repos/{_repo()}/commits/{sha}/check-runs")
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
    resp = await github_request("GET", f"/repos/{_repo()}/pulls/{number}/reviews")
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

    resp = await github_request("GET", f"/repos/{_repo()}/issues", params=params)
    resp.raise_for_status()
    return [i for i in resp.json() if "pull_request" not in i]


@retryable(max_retries=3, base_delay=1.0)
async def list_open_prs() -> list[dict]:
    """List all open PRs."""
    resp = await github_request(
        "GET", f"/repos/{_repo()}/pulls", params={"state": "open", "per_page": 100}
    )
    resp.raise_for_status()
    return resp.json()
