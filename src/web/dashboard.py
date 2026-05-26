"""Dashboard — real-time status page with DB-backed statistics."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Render the dashboard with live stats."""
    from src.store.db import get_session
    from src.store.models import AuditLog
    from src.store.cost_tracker import get_cost_summary
    from src.tools.github_client import get_rate_limit_status
    from sqlalchemy import select, func

    today = datetime.utcnow().date()
    start_today = datetime(today.year, today.month, today.day)
    start_week = start_today - timedelta(days=7)

    stats = {"today": 0, "week": 0, "total": 0}

    try:
        async with get_session() as session:
            r_today = await session.execute(
                select(func.count()).where(AuditLog.created_at >= start_today)
            )
            stats["today"] = r_today.scalar() or 0

            r_week = await session.execute(
                select(func.count()).where(AuditLog.created_at >= start_week)
            )
            stats["week"] = r_week.scalar() or 0

            r_total = await session.execute(select(func.count()).select_from(AuditLog))
            stats["total"] = r_total.scalar() or 0
    except Exception:
        pass

    cost = await get_cost_summary(days=30)
    rate_limit = get_rate_limit_status()

    return _render_dashboard(stats, cost, rate_limit)


@router.get("/events", response_class=HTMLResponse)
async def events_page():
    """Show recent events."""
    from src.store.db import get_session
    from src.store.models import AuditLog
    from sqlalchemy import select

    events = []
    try:
        async with get_session() as session:
            result = await session.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50)
            )
            events = result.scalars().all()
    except Exception:
        pass

    return _render_events(events)


def _render_dashboard(stats: dict, cost: dict, rate_limit: dict) -> str:
    return f"""<!DOCTYPE html>
<html><head>
<title>Sentinel Dashboard</title>
<meta charset="utf-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 40px; }}
h1 {{ color: #58a6ff; margin-bottom: 30px; }}
.stats {{ display: flex; gap: 20px; margin-bottom: 40px; flex-wrap: wrap; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; min-width: 160px; }}
.stat h3 {{ color: #8b949e; font-size: 12px; text-transform: uppercase; margin-bottom: 8px; }}
.stat .value {{ font-size: 32px; font-weight: bold; color: #58a6ff; }}
.stat .sub {{ font-size: 12px; color: #8b949e; margin-top: 4px; }}
.section {{ margin-top: 30px; }}
.section h2 {{ color: #c9d1d9; margin-bottom: 15px; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 15px; text-align: left; border-bottom: 1px solid #21262d; }}
th {{ color: #8b949e; font-size: 12px; text-transform: uppercase; }}
a {{ color: #58a6ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; }}
.badge-ok {{ background: #238636; }}
.badge-active {{ background: #1f6feb; }}
.badge-warn {{ background: #9e6a03; }}
nav {{ margin-bottom: 30px; }}
nav a {{ margin-right: 20px; font-size: 14px; }}
</style>
</head><body>
<h1>MemOS Sentinel</h1>
<nav>
    <a href="/dashboard/">Overview</a>
    <a href="/dashboard/events">Events</a>
    <a href="/health">Health</a>
</nav>
<div class="stats">
    <div class="stat"><h3>Today</h3><div class="value">{stats['today']}</div><div class="sub">events processed</div></div>
    <div class="stat"><h3>This Week</h3><div class="value">{stats['week']}</div><div class="sub">events processed</div></div>
    <div class="stat"><h3>All Time</h3><div class="value">{stats['total']}</div><div class="sub">total events</div></div>
    <div class="stat"><h3>LLM Cost (30d)</h3><div class="value">${cost.get('total_cost_usd', 0):.2f}</div><div class="sub">{cost.get('total_calls', 0)} calls</div></div>
    <div class="stat"><h3>GitHub API</h3><div class="value">{rate_limit.get('remaining', '?')}</div><div class="sub">requests remaining</div></div>
    <div class="stat"><h3>Status</h3><div class="value"><span class="badge badge-ok">Running</span></div><div class="sub">v0.3.0</div></div>
</div>
<div class="section">
    <h2>Active Capabilities</h2>
    <table>
        <tr><th>Feature</th><th>Status</th><th>Trigger</th></tr>
        <tr><td>Issue Auto-Classification</td><td><span class="badge badge-active">Active</span></td><td>issues.opened webhook</td></tr>
        <tr><td>Duplicate Detection</td><td><span class="badge badge-active">Active</span></td><td>New issue similarity check</td></tr>
        <tr><td>Template Check (needs-info)</td><td><span class="badge badge-active">Active</span></td><td>Bug without details</td></tr>
        <tr><td>Question Auto-Reply</td><td><span class="badge badge-active">Active</span></td><td>Question-type issues</td></tr>
        <tr><td>PR Code Review (Opus)</td><td><span class="badge badge-active">Active</span></td><td>pull_request.opened</td></tr>
        <tr><td>DevAgent Auto-Fix</td><td><span class="badge badge-active">Active</span></td><td>ai-task label</td></tr>
        <tr><td>DevAgent Self-Reflection</td><td><span class="badge badge-active">Active</span></td><td>Before PR submission</td></tr>
        <tr><td>CI Monitor + Retry</td><td><span class="badge badge-active">Active</span></td><td>After DevAgent PR</td></tr>
        <tr><td>Stale Management</td><td><span class="badge badge-active">Active</span></td><td>Daily 09:00 cron</td></tr>
        <tr><td>DingTalk Notifications</td><td><span class="badge badge-active">Active</span></td><td>Classify/Error/Daily</td></tr>
        <tr><td>PR Merge Tracking</td><td><span class="badge badge-active">Active</span></td><td>pull_request.closed (merged)</td></tr>
    </table>
</div>
</body></html>"""


def _render_events(events) -> str:
    rows = ""
    for e in events:
        ts = e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else ""
        rows += f"<tr><td>{ts}</td><td>{e.event_type}</td><td>{e.event_action or ''}</td><td>#{e.target_number or ''}</td><td>{e.result_summary or ''}</td></tr>\n"

    return f"""<!DOCTYPE html>
<html><head>
<title>Sentinel Events</title>
<meta charset="utf-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 40px; }}
h1 {{ color: #58a6ff; margin-bottom: 30px; }}
nav {{ margin-bottom: 30px; }}
nav a {{ color: #58a6ff; margin-right: 20px; font-size: 14px; text-decoration: none; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 15px; text-align: left; border-bottom: 1px solid #21262d; }}
th {{ color: #8b949e; font-size: 12px; text-transform: uppercase; }}
</style>
</head><body>
<h1>Recent Events</h1>
<nav>
    <a href="/dashboard/">Overview</a>
    <a href="/dashboard/events">Events</a>
</nav>
<table>
<tr><th>Time</th><th>Event</th><th>Action</th><th>Target</th><th>Result</th></tr>
{rows if rows else '<tr><td colspan="5">No events yet</td></tr>'}
</table>
</body></html>"""
