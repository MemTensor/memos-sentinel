"""Notify handler — routes issues to humans when agent cannot auto-fix."""

from __future__ import annotations

import logging

from src.notify.dingtalk import send_notification
from src.tools.github_write import post_comment

logger = logging.getLogger(__name__)

NOT_FIXABLE_REASONS = {
    "question": "This is a question/discussion that requires human judgment.",
    "enhancement": "Feature requests need human design decisions on scope and implementation.",
    "performance": "Performance issues require profiling and benchmarking that the agent cannot perform.",
    "vague_bug": "The bug description lacks sufficient detail (no error message, repro steps, or expected behavior).",
    "complex_architecture": "This requires architectural changes beyond a simple code patch.",
    "needs_discussion": "This needs team discussion before any implementation.",
}


async def notify_needs_human(
    issue_number: int,
    title: str,
    module: str | None,
    priority: str | None,
    reason_key: str = "vague_bug",
) -> None:
    """Notify humans when an issue cannot be auto-fixed by the agent.

    1. Post a GitHub comment explaining classification + why not auto-fixable
    2. Send DingTalk push notification
    """
    reason = NOT_FIXABLE_REASONS.get(reason_key, NOT_FIXABLE_REASONS["vague_bug"])
    mod_str = module or "unclassified"
    pri_str = priority or "P2:normal"

    # GitHub comment
    comment = (
        f"## Sentinel Classification\n\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| Module | `{mod_str}` |\n"
        f"| Priority | `{pri_str}` |\n"
        f"| Auto-fixable | No |\n\n"
        f"**Reason:** {reason}\n\n"
        f"This issue has been classified and requires human attention.\n\n"
        f"---\n*Classified by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
    )

    try:
        await post_comment(issue_number, comment)
    except Exception as e:
        logger.error(f"Failed to post comment on #{issue_number}: {e}")

    # DingTalk notification
    ding_msg = f"#{issue_number} ({mod_str}/{pri_str}) 需人工处理: {title}\nReason: {reason}"
    try:
        await send_notification(ding_msg)
    except Exception as e:
        logger.error(f"Failed to send DingTalk for #{issue_number}: {e}")


async def notify_ai_task_started(issue_number: int, title: str) -> None:
    """Notify that agent has started working on an ai-task."""
    await send_notification(f"#{issue_number} ai-task 开始处理: {title}")


async def notify_pr_ready(issue_number: int, pr_number: int, title: str) -> None:
    """Notify that a fix PR is ready for review."""
    msg = f"#{issue_number} 修复 PR #{pr_number} 已就绪，请 review: {title}"
    await send_notification(msg)


async def notify_ci_failed(issue_number: int, pr_number: int, attempts: int) -> None:
    """Notify that CI failed after retries, needs human help."""
    msg = f"#{issue_number} PR #{pr_number} CI 失败 ({attempts}次重试后)，需要人工介入"
    await send_notification(msg)


async def notify_pr_reviewed(pr_number: int, title: str, event: str) -> None:
    """Notify that a PR has been reviewed by the agent."""
    msg = f"PR #{pr_number} 已审查 ({event}): {title}"
    await send_notification(msg)
