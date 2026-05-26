"""CI Monitor — polls GitHub check status and triggers retry on failure."""

from __future__ import annotations

import asyncio
import logging

from src.agent.state import get_settings
from src.agent.retry import RetryExhausted
from src.agent.notify_handler import notify_pr_ready, notify_ci_failed

logger = logging.getLogger(__name__)


async def wait_for_ci(pr_number: int, timeout_seconds: int = 600, poll_interval: int = 30) -> dict:
    """Poll CI status until completion or timeout.

    Returns: {"passed": bool, "runs": [...], "elapsed": int}
    """
    from src.tools.github_read import list_pr_checks

    elapsed = 0
    while elapsed < timeout_seconds:
        result = await list_pr_checks(pr_number)
        runs = result.get("runs", [])

        if not runs:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            continue

        all_done = all(r.get("status") == "completed" for r in runs)
        if all_done:
            passed = all(r.get("conclusion") == "success" for r in runs)
            return {"passed": passed, "runs": runs, "elapsed": elapsed}

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    return {"passed": False, "runs": [], "elapsed": elapsed, "timeout": True}


async def run_ci_with_retry(
    issue_number: int,
    pr_number: int,
    max_retries: int | None = None,
) -> bool:
    """Monitor CI and retry on failure.

    Flow:
    1. Wait for CI to complete
    2. If passed → notify success
    3. If failed → analyze failure → generate fix → push → retry (max 2)
    4. If exhausted → notify human
    """
    from src.tools.github_read import read_pr, list_pr_checks
    from src.tools.github_write import post_comment
    from src.llm.client import get_heavy_model

    settings = get_settings()
    if max_retries is None:
        max_retries = settings.max_dev_retries

    for attempt in range(max_retries + 1):
        logger.info(f"CI attempt {attempt + 1}/{max_retries + 1} for PR #{pr_number}")

        ci_result = await wait_for_ci(pr_number)

        if ci_result.get("passed"):
            logger.info(f"CI passed for PR #{pr_number} on attempt {attempt + 1}")
            await notify_pr_ready(issue_number, pr_number, f"Issue #{issue_number}")
            return True

        if ci_result.get("timeout"):
            logger.warning(f"CI timeout for PR #{pr_number}")
            break

        # CI failed — try to fix
        if attempt < max_retries:
            logger.info(f"CI failed, attempting fix (attempt {attempt + 1})")
            fixed = await _attempt_ci_fix(pr_number, ci_result, attempt + 1)
            if not fixed:
                break
            # After fix, loop back to wait for CI again
        else:
            break

    # All retries exhausted
    await notify_ci_failed(issue_number, pr_number, max_retries + 1)
    await post_comment(
        issue_number,
        f"CI failed on PR #{pr_number} after {max_retries + 1} attempts. Needs manual intervention.",
    )
    return False


async def _attempt_ci_fix(pr_number: int, ci_result: dict, attempt_num: int) -> bool:
    """Analyze CI failure and push a fix commit."""
    import json
    import base64
    import httpx

    from src.tools.github_read import read_pr
    from src.llm.client import get_heavy_model
    from src.agent.state import get_settings

    settings = get_settings()
    model = get_heavy_model()

    # Get PR details for branch name
    pr_detail = await read_pr(pr_number)
    branch = pr_detail.get("head", {}).get("ref", "")
    if not branch:
        return False

    # Build failure context
    failed_runs = [r for r in ci_result.get("runs", []) if r.get("conclusion") != "success"]
    failure_desc = "\n".join(
        f"- {r['name']}: {r.get('conclusion', 'unknown')}" for r in failed_runs
    )

    # Ask LLM to analyze and suggest fix
    prompt = f"""A CI check failed on a PR. Analyze and generate a fix.

## Failed Checks
{failure_desc}

## PR Branch: {branch}

## What to do
Based on common CI failure patterns, suggest a minimal fix.
If you cannot determine the fix from this information alone, respond with:
{{"can_fix": false}}

Otherwise respond with:
{{
    "can_fix": true,
    "file_path": "path/to/fix",
    "new_content": "full file content with fix",
    "commit_message": "fix: address CI failure"
}}"""

    try:
        response = await model.ainvoke(prompt)
        content = response.content
        if "{" not in content:
            return False

        json_str = content[content.index("{"):content.rindex("}") + 1]
        result = json.loads(json_str)

        if not result.get("can_fix"):
            return False

        # Push the fix
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        }
        repo = settings.github_target_repo
        api = "https://api.github.com"
        file_path = result["file_path"]

        async with httpx.AsyncClient(timeout=30) as client:
            # Get current file SHA
            existing = await client.get(
                f"{api}/repos/{repo}/contents/{file_path}",
                headers=headers,
                params={"ref": branch},
            )
            file_sha = None
            if existing.status_code == 200:
                file_sha = existing.json().get("sha")

            encoded = base64.b64encode(result["new_content"].encode()).decode()
            put_data = {
                "message": result.get("commit_message", f"fix: CI retry attempt {attempt_num + 1}"),
                "content": encoded,
                "branch": branch,
            }
            if file_sha:
                put_data["sha"] = file_sha

            resp = await client.put(
                f"{api}/repos/{repo}/contents/{file_path}",
                headers=headers,
                json=put_data,
            )
            return resp.status_code < 400

    except Exception as e:
        logger.error(f"CI fix attempt failed: {e}")
        return False
