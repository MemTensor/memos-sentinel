"""Dashboard — simple status page and daily report view."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Render the main dashboard."""
    return """<!DOCTYPE html>
<html><head><title>Sentinel Dashboard</title>
<style>
body { font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }
.stat { display: inline-block; padding: 20px; margin: 10px; background: #f6f8fa; border-radius: 8px; }
</style></head>
<body>
<h1>MemOS Sentinel Dashboard</h1>
<div class="stat"><h3>Status</h3><p>Running</p></div>
<div class="stat"><h3>Mode</h3><p>Dry Run</p></div>
<div class="stat"><h3>Events Today</h3><p>—</p></div>
<hr>
<p><em>Full dashboard coming in Phase 2.</em></p>
</body></html>"""
