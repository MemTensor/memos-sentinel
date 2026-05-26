"""Scheduler — real cron jobs for stale scan, daily report, and label cleanup."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    """Start the background scheduler."""
    global _scheduler
    _scheduler = AsyncIOScheduler()

    _scheduler.add_job(daily_stale_scan, "cron", hour=9, minute=0, id="stale_scan")
    _scheduler.add_job(daily_report, "cron", hour=18, minute=0, id="daily_report")

    _scheduler.start()
    logger.info("Scheduler started: stale_scan@09:00, daily_report@18:00")


async def daily_stale_scan():
    """Scan for stale issues (30+ days no activity) and warn/close."""
    from src.tools.github_read import list_open_issues
    from src.tools.github_write import add_labels, post_comment, close_issue
    from src.agent.state import get_settings
    from datetime import datetime, timedelta

    logger.info("Running daily stale scan...")

    try:
        issues = await list_open_issues()
    except Exception as e:
        logger.error(f"Stale scan failed to fetch issues: {e}")
        return

    now = datetime.utcnow()
    stale_count = 0
    close_count = 0

    exempt_labels = {"do not close", "ai-task", "ai-reviewing", "P0:critical", "P1:important"}

    for issue in issues:
        labels = {l["name"] for l in issue.get("labels", [])}
        if labels & exempt_labels:
            continue

        updated_at = issue.get("updated_at", "")
        if not updated_at:
            continue

        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue

        days_inactive = (now - updated).days
        number = issue["number"]

        # 30+ days → mark stale
        if days_inactive >= 30 and "stale" not in labels:
            try:
                await add_labels(number, ["stale"])
                await post_comment(number, (
                    "This issue has been automatically marked as **stale** due to 30+ days "
                    "of inactivity. It will be closed in 7 days unless there is new activity.\n\n"
                    "- Comment to keep it open\n"
                    "- Add `do not close` label to prevent auto-closing\n\n"
                    "---\n*Managed by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
                ))
                stale_count += 1
            except Exception as e:
                logger.error(f"Failed to mark #{number} as stale: {e}")

        # 37+ days (stale for 7 days) → close
        elif days_inactive >= 37 and "stale" in labels:
            try:
                await close_issue(number, (
                    "Closing this issue due to continued inactivity. "
                    "If the problem persists, feel free to reopen or create a new issue.\n\n"
                    "---\n*Managed by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
                ))
                close_count += 1
            except Exception as e:
                logger.error(f"Failed to close #{number}: {e}")

    logger.info(f"Stale scan complete: {stale_count} marked stale, {close_count} closed")

    if stale_count or close_count:
        from src.notify.dingtalk import send_notification
        await send_notification(f"Stale scan: {stale_count} marked stale, {close_count} auto-closed")


async def daily_report():
    """Generate and send daily activity report."""
    from src.notify.dingtalk import send_notification
    from src.store.db import get_session
    from src.store.models import AuditLog
    from sqlalchemy import select, func
    from datetime import datetime, timedelta

    logger.info("Generating daily report...")

    today = datetime.utcnow().date()
    start = datetime(today.year, today.month, today.day)

    try:
        async with get_session() as session:
            result = await session.execute(
                select(func.count()).where(AuditLog.created_at >= start)
            )
            event_count = result.scalar() or 0
    except Exception:
        event_count = 0

    report = (
        f"Daily Report ({today.isoformat()}):\n"
        f"- Events processed: {event_count}\n"
        f"- Status: operational"
    )
    await send_notification(report)


async def cleanup_old_labels():
    """One-time job: remove 'pending' label from all issues."""
    from src.tools.github_read import list_open_issues
    from src.tools.github_write import remove_labels

    logger.info("Running old label cleanup (removing 'pending')...")

    try:
        issues = await list_open_issues(label="pending")
    except Exception as e:
        logger.error(f"Label cleanup failed: {e}")
        return

    removed = 0
    for issue in issues:
        try:
            await remove_labels(issue["number"], ["pending"])
            removed += 1
        except Exception:
            pass

    logger.info(f"Removed 'pending' from {removed} issues")
