"""Dev Agent — ai-task triggered development flow with CI retry logic."""

from __future__ import annotations

import logging
from src.agent.state import AgentState, DevContext, get_settings
from src.agent.retry import with_retry, RetryExhausted

logger = logging.getLogger(__name__)

MAX_STEPS = 15


async def run_dev_agent(state: AgentState) -> dict:
    """Full development flow: analyze → fix → PR → CI → retry."""
    from src.llm.client import get_heavy_model
    from src.tools.github_read import read_issue, read_file, search_code
    from src.tools.github_dev import (
        create_branch,
        edit_file,
        commit_and_push,
        create_pull_request,
        trigger_ci,
    )
    from src.tools.github_write import post_comment, add_labels, remove_labels

    settings = get_settings()
    event = state["event"]
    payload = event.get("payload", {})
    issue = payload.get("issue", {})
    issue_number = issue.get("number")

    if not issue_number:
        return {"summary": "dev-agent: no issue number"}

    actions = []

    # Step 1: Read issue details
    issue_detail = await read_issue(issue_number)
    await add_labels(issue_number, ["ai-reviewing"])
    await remove_labels(issue_number, ["ai-task"])

    # Step 2: Analyze and locate relevant code
    model = get_heavy_model()
    analysis = await _analyze_issue(model, issue_detail)

    # Step 3: Create branch
    branch_name = f"{settings.dev_branch_prefix}{issue_number}"
    base_branch = _determine_base_branch(issue_detail)
    await create_branch(branch_name, base=base_branch)

    dev_ctx: DevContext = {
        "issue_number": issue_number,
        "branch_name": branch_name,
        "files_modified": [],
        "pr_number": None,
        "ci_attempts": 0,
        "clone_path": "",
    }
    state["dev_context"] = dev_ctx

    # Step 4: Generate and apply fix
    fix_result = await _generate_fix(model, analysis)
    for file_change in fix_result.get("changes", []):
        await edit_file(file_change["path"], file_change["content"])
        dev_ctx["files_modified"].append(file_change["path"])

    # Step 5: Commit and push
    commit_msg = f"fix: {analysis.get('summary', f'resolve #{issue_number}')}"
    await commit_and_push(commit_msg)

    # Step 6: Create Draft PR
    pr_body = _build_pr_body(issue_number, analysis, fix_result)
    pr = await create_pull_request(
        title=f"fix(sentinel): {analysis.get('summary', '')} (#{issue_number})",
        body=pr_body,
        base=base_branch,
        head=branch_name,
        draft=True,
    )
    dev_ctx["pr_number"] = pr.get("number")
    actions.append({"tool": "create_pr", "pr_number": pr.get("number")})

    # Step 7: Trigger CI with retry
    try:
        await _run_ci_with_retry(state, model, settings.max_dev_retries)
        await post_comment(
            issue_number,
            f"Created PR #{dev_ctx['pr_number']} with fix. CI passed. Ready for review.",
        )
        from src.notify.dingtalk import send_notification

        await send_notification(
            f"PR #{dev_ctx['pr_number']} for issue #{issue_number} — CI passed, please review."
        )
    except RetryExhausted:
        await post_comment(
            issue_number,
            f"PR #{dev_ctx['pr_number']} created but CI failed after "
            f"{settings.max_dev_retries} retries. Needs manual intervention.",
        )
        from src.notify.dingtalk import send_notification

        await send_notification(
            f"PR #{dev_ctx['pr_number']} for issue #{issue_number} — CI FAILED, needs human help."
        )

    state["actions_taken"] = actions
    state["final_summary"] = f"dev-agent: PR #{dev_ctx['pr_number']} for issue #{issue_number}"
    return {"summary": state["final_summary"], "actions": actions}


def _determine_base_branch(issue_detail: dict) -> str:
    """Determine the correct base branch for the fix.

    Strategy:
    - If issue mentions a specific version/branch → target that branch
    - If issue is a regression tagged with a release → target release branch
    - Default → main
    """
    settings = get_settings()
    body = (issue_detail.get("body") or "").lower()
    labels = [l.get("name", "") for l in issue_detail.get("labels", [])]

    # Check for release branch mentions
    for label in labels:
        if label.startswith("v") and "." in label:
            return f"release/{label}"

    return settings.default_base_branch


async def _analyze_issue(model, issue_detail: dict) -> dict:
    """Use LLM to analyze the issue and determine fix strategy."""
    # Placeholder for LangChain implementation
    return {"summary": "", "relevant_files": [], "fix_approach": ""}


async def _generate_fix(model, analysis: dict) -> dict:
    """Use LLM to generate code changes."""
    # Placeholder for LangChain implementation
    return {"changes": []}


async def _run_ci_with_retry(state: AgentState, model, max_retries: int):
    """Run CI and retry on failure up to max_retries times."""
    from src.tools.github_dev import trigger_ci
    from src.tools.github_read import list_pr_checks
    from src.agent.retry import RetryExhausted

    dev_ctx = state["dev_context"]
    pr_number = dev_ctx["pr_number"]

    for attempt in range(max_retries + 1):
        dev_ctx["ci_attempts"] = attempt + 1
        await trigger_ci(pr_number)

        ci_result = await _wait_for_ci(pr_number)
        if ci_result.get("passed"):
            return

        if attempt < max_retries:
            logger.info(f"CI failed (attempt {attempt + 1}), analyzing and retrying...")
            fix = await _fix_ci_failure(model, ci_result)
            if fix:
                from src.tools.github_dev import edit_file, commit_and_push

                for change in fix.get("changes", []):
                    await edit_file(change["path"], change["content"])
                await commit_and_push(f"fix: address CI failure (attempt {attempt + 2})")

    raise RetryExhausted(f"CI failed after {max_retries + 1} attempts")


async def _wait_for_ci(pr_number: int) -> dict:
    """Poll CI status until completion."""
    # Placeholder — will poll GitHub checks API
    return {"passed": False, "logs": ""}


async def _fix_ci_failure(model, ci_result: dict) -> dict | None:
    """Analyze CI failure and generate a fix."""
    # Placeholder for LangChain implementation
    return None


def _build_pr_body(issue_number: int, analysis: dict, fix_result: dict) -> str:
    return (
        f"## Summary\n\n"
        f"Automated fix for #{issue_number}.\n\n"
        f"**Analysis:** {analysis.get('summary', 'N/A')}\n\n"
        f"**Approach:** {analysis.get('fix_approach', 'N/A')}\n\n"
        f"## Changes\n\n"
        + "\n".join(f"- `{c['path']}`" for c in fix_result.get("changes", []))
        + "\n\n---\n*Generated by memos-sentinel*"
    )
