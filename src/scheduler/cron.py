"""Scheduler — daily cron jobs for stale scan and reporting."""

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
    """Scan for stale issues (30+ days no activity) and notify."""
    from src.tools.github_read import list_open_issues
    from src.tools.github_write import add_labels, post_comment
    from src.agent.state import get_settings

    logger.info("Running daily stale scan...")
    settings = get_settings()

    issues = await list_open_issues(since_days=30)
    stale_count = 0

    for issue in issues:
        labels = [l["name"] for l in issue.get("labels", [])]
        if "do not close" in labels or "ai-task" in labels or "ai-reviewing" in labels:
            continue

        if "stale" not in labels:
            if not settings.dry_run:
                await add_labels(issue["number"], ["stale"])
                await post_comment(
                    issue["number"],
                    "This issue has been automatically marked as stale due to 30+ days of "
                    "inactivity. It will be closed in 7 days unless there is new activity. "
                    "Add the `do not close` label to prevent this.",
                )
            stale_count += 1

    logger.info(f"Stale scan complete: {stale_count} issues marked stale")


async def daily_report():
    """Generate and send daily activity report."""
    from src.notify.dingtalk import send_notification

    logger.info("Generating daily report...")

    # Placeholder — will query audit log for today's activity
    report = "Daily report: system operational (details coming in Phase 2)"
    await send_notification(report)
