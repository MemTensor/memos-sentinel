"""Dev Agent — ai-task triggered: analyze issue, write fix, create PR."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from src.agent.state import get_settings
from src.agent.notify_handler import notify_ai_task_started, notify_pr_ready, notify_ci_failed

logger = logging.getLogger(__name__)

SANDBOX_BASE = Path("/tmp/sentinel-runs")


async def run_dev_agent_for_issue(issue_number: int) -> dict:
    """Full dev flow: analyze → fix → PR → CI check."""
    from src.tools.github_read import read_issue, search_code, read_file
    from src.tools.github_write import add_labels, remove_labels, post_comment
    from src.llm.client import get_heavy_model

    settings = get_settings()

    # Mark as in-progress
    try:
        await add_labels(issue_number, ["ai-reviewing"])
        await remove_labels(issue_number, ["ai-task"])
    except Exception:
        pass

    await notify_ai_task_started(issue_number, f"Issue #{issue_number}")

    # Step 1: Read issue details
    issue = await read_issue(issue_number)
    title = issue.get("title", "")
    body = issue.get("body", "") or ""

    # Step 2: Analyze with Opus — determine what to fix
    model = get_heavy_model()
    analysis = await _analyze_issue(model, title, body)

    if not analysis.get("can_fix"):
        await post_comment(issue_number, (
            "## Sentinel Analysis\n\n"
            f"After analyzing this issue, I've determined it requires human intervention.\n\n"
            f"**Reason:** {analysis.get('reason', 'Complex fix beyond automated scope')}\n\n"
            "Removing `ai-reviewing` label.\n\n"
            "---\n*Analyzed by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
        ))
        await remove_labels(issue_number, ["ai-reviewing"])
        return {"action": "cannot_fix", "reason": analysis.get("reason")}

    # Step 3: Search for relevant code
    relevant_files = analysis.get("files_to_check", [])
    code_context = {}
    for file_path in relevant_files[:5]:
        try:
            content = await read_file(file_path)
            code_context[file_path] = content[:5000]
        except Exception:
            pass

    # Step 4: Generate fix
    fix = await _generate_fix(model, title, body, code_context, analysis)
    if not fix.get("changes"):
        await post_comment(issue_number, (
            "## Sentinel Analysis\n\n"
            "I analyzed the issue but could not generate a confident fix.\n"
            "Needs human attention.\n\n"
            "---\n*Analyzed by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
        ))
        await remove_labels(issue_number, ["ai-reviewing"])
        return {"action": "no_fix_generated"}

    # Step 5: Self-reflection — review our own patch before submitting
    reflection = await _self_reflect(model, title, body, fix, code_context)
    if not reflection.get("approved"):
        await post_comment(issue_number, (
            "## Sentinel Analysis\n\n"
            "I generated a potential fix but my self-review flagged quality concerns:\n\n"
            f"> {reflection.get('reason', 'Low confidence in correctness')}\n\n"
            "This issue needs human attention.\n\n"
            "---\n*Analyzed by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
        ))
        await remove_labels(issue_number, ["ai-reviewing"])
        return {"action": "self_reflection_rejected", "reason": reflection.get("reason")}

    # Step 6: Create branch and PR via GitHub API
    branch_name = f"{settings.dev_branch_prefix}{issue_number}"
    pr_result = await _create_fix_pr(issue_number, branch_name, fix, title, body, analysis)

    if pr_result.get("error"):
        await post_comment(issue_number, f"Failed to create PR: {pr_result['error']}")
        await remove_labels(issue_number, ["ai-reviewing"])
        return {"action": "pr_creation_failed", "error": pr_result["error"]}

    pr_number = pr_result.get("number")
    await post_comment(issue_number, (
        f"## Sentinel Fix\n\n"
        f"I've created PR #{pr_number} with a proposed fix.\n\n"
        f"**Branch:** `{branch_name}`\n"
        f"**Analysis:** {analysis.get('summary', '')}\n\n"
        f"Please review the PR and merge if it looks good.\n\n"
        f"---\n*Fix by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
    ))

    await notify_pr_ready(issue_number, pr_number, title)

    # Start CI monitoring in background
    import asyncio
    from src.agent.ci_monitor import run_ci_with_retry
    asyncio.create_task(run_ci_with_retry(issue_number, pr_number))

    return {"action": "pr_created", "pr_number": pr_number}


async def _analyze_issue(model, title: str, body: str) -> dict:
    """Use Opus to analyze the issue and determine fix strategy."""
    import json

    prompt = f"""Analyze this GitHub issue and determine if you can write a code fix for it.

Title: {title}
Body: {body[:3000]}

Respond with JSON:
{{
    "can_fix": true/false,
    "reason": "why or why not",
    "summary": "one-line summary of the fix needed",
    "files_to_check": ["list", "of", "file", "paths", "to", "examine"],
    "fix_approach": "brief description of how to fix"
}}

Only set can_fix=true if:
1. The problem is clearly defined
2. You can identify specific files/functions to change
3. The fix is straightforward (no major refactoring)"""

    try:
        response = await model.ainvoke(prompt)
        content = response.content
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            return json.loads(json_str)
    except Exception as e:
        logger.error(f"Analysis failed: {e}")

    return {"can_fix": False, "reason": "Analysis failed"}


async def _generate_fix(model, title: str, body: str, code_context: dict, analysis: dict) -> dict:
    """Use Opus to generate code changes."""
    import json

    context_str = ""
    for path, content in code_context.items():
        context_str += f"\n### {path}\n```\n{content[:3000]}\n```\n"

    prompt = f"""Generate a code fix for this issue.

## Issue
Title: {title}
Body: {body[:2000]}

## Analysis
{analysis.get('fix_approach', '')}

## Current Code
{context_str}

## Instructions
Generate the fix as a JSON array of file changes:
{{
    "changes": [
        {{
            "path": "path/to/file.py",
            "content": "full new file content"
        }}
    ],
    "commit_message": "fix: descriptive commit message"
}}

Only include files that need changes. Provide the COMPLETE new content for each file."""

    try:
        response = await model.ainvoke(prompt)
        content = response.content
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            return json.loads(json_str)
    except Exception as e:
        logger.error(f"Fix generation failed: {e}")

    return {"changes": []}


async def _create_fix_pr(
    issue_number: int,
    branch_name: str,
    fix: dict,
    title: str,
    body: str,
    analysis: dict,
) -> dict:
    """Create a branch with fixes and open a Draft PR via GitHub API."""
    import httpx
    import base64

    settings = get_settings()
    repo = settings.github_target_repo
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }
    api = "https://api.github.com"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # Get main branch SHA
            ref_resp = await client.get(
                f"{api}/repos/{repo}/git/ref/heads/{settings.default_base_branch}",
                headers=headers,
            )
            ref_resp.raise_for_status()
            base_sha = ref_resp.json()["object"]["sha"]

            # Create branch
            create_ref_resp = await client.post(
                f"{api}/repos/{repo}/git/refs",
                headers=headers,
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            )
            if create_ref_resp.status_code == 422:
                # Branch exists, get its SHA
                pass
            elif create_ref_resp.status_code >= 400:
                return {"error": f"Failed to create branch: {create_ref_resp.text}"}

            # Commit each file change
            for change in fix.get("changes", []):
                file_path = change["path"]
                content = change["content"]
                encoded = base64.b64encode(content.encode()).decode()

                # Check if file exists
                existing = await client.get(
                    f"{api}/repos/{repo}/contents/{file_path}",
                    headers=headers,
                    params={"ref": branch_name},
                )
                file_sha = None
                if existing.status_code == 200:
                    file_sha = existing.json().get("sha")

                put_data = {
                    "message": fix.get("commit_message", f"fix: resolve #{issue_number}"),
                    "content": encoded,
                    "branch": branch_name,
                }
                if file_sha:
                    put_data["sha"] = file_sha

                put_resp = await client.put(
                    f"{api}/repos/{repo}/contents/{file_path}",
                    headers=headers,
                    json=put_data,
                )
                if put_resp.status_code >= 400:
                    return {"error": f"Failed to update {file_path}: {put_resp.text[:200]}"}

            # Create Draft PR
            pr_body = (
                f"## Summary\n\n"
                f"Automated fix for #{issue_number}.\n\n"
                f"**Analysis:** {analysis.get('summary', 'N/A')}\n\n"
                f"**Approach:** {analysis.get('fix_approach', 'N/A')}\n\n"
                f"## Changes\n\n"
                + "\n".join(f"- `{c['path']}`" for c in fix.get("changes", []))
                + f"\n\nCloses #{issue_number}\n\n"
                + "---\n*Generated by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
            )

            pr_resp = await client.post(
                f"{api}/repos/{repo}/pulls",
                headers=headers,
                json={
                    "title": f"fix(sentinel): {analysis.get('summary', title)[:60]} (#{issue_number})",
                    "body": pr_body,
                    "head": branch_name,
                    "base": settings.default_base_branch,
                    "draft": True,
                },
            )
            if pr_resp.status_code >= 400:
                return {"error": f"Failed to create PR: {pr_resp.text[:200]}"}

            pr_data = pr_resp.json()
            return {"number": pr_data["number"], "url": pr_data["html_url"]}

        except Exception as e:
            return {"error": str(e)}


async def _self_reflect(model, title: str, body: str, fix: dict, code_context: dict) -> dict:
    """Self-reflection: review our own patch for quality before submitting.

    Uses Haiku (cheap) to quickly verify the patch makes sense.
    """
    import json

    from src.llm.client import get_light_model
    reviewer = get_light_model()

    changes_desc = "\n".join(
        f"- `{c['path']}`: {len(c.get('content', ''))} chars"
        for c in fix.get("changes", [])
    )
    sample_content = ""
    for c in fix.get("changes", [])[:2]:
        sample_content += f"\n### {c['path']}\n```\n{c.get('content', '')[:2000]}\n```\n"

    prompt = f"""Review this AI-generated code patch. Does it look correct and safe to submit as a PR?

## Issue Being Fixed
Title: {title}
Body: {body[:1000]}

## Proposed Changes
{changes_desc}

{sample_content}

## Criteria
1. Does the fix address the issue described?
2. Does it introduce obvious bugs or regressions?
3. Is the change scope reasonable (not too large, not trivially wrong)?
4. Would this pass basic code review?

Respond with JSON:
{{"approved": true/false, "reason": "brief explanation"}}"""

    try:
        response = await reviewer.ainvoke(prompt)
        content = response.content
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            return json.loads(json_str)
    except Exception as e:
        logger.warning(f"Self-reflection failed: {e}")

    # If reflection fails, default to approved (don't block on reflection errors)
    return {"approved": True, "reason": "reflection unavailable, proceeding"}
