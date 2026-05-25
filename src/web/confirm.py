"""Web confirmation page — approve/reject actions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.agent.human_gate import approve_action, reject_action, check_approval

router = APIRouter()


@router.get("/{action_id}", response_class=HTMLResponse)
async def confirm_page(action_id: str, action: str = Query(None)):
    """Render confirmation page or process action."""
    status = await check_approval(action_id)
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Action not found")

    if action == "approve":
        success = await approve_action(action_id)
        if success:
            return _render_result("Approved", "The action has been approved and will be executed.")
        return _render_result("Error", "Could not approve. Action may have already been processed.")

    if action == "reject":
        success = await reject_action(action_id)
        if success:
            return _render_result("Rejected", "The action has been rejected.")
        return _render_result("Error", "Could not reject. Action may have already been processed.")

    if status != "pending":
        return _render_result("Already Processed", f"This action has been {status}.")

    return _render_confirm(action_id)


def _render_confirm(action_id: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>Sentinel — Confirm Action</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
.btn {{ display: inline-block; padding: 12px 24px; margin: 10px; border-radius: 6px; text-decoration: none; font-weight: bold; }}
.approve {{ background: #2ea44f; color: white; }}
.reject {{ background: #d73a4a; color: white; }}
</style></head>
<body>
<h1>Confirm Action</h1>
<p>An automated action requires your approval.</p>
<a class="btn approve" href="/confirm/{action_id}?action=approve">Approve</a>
<a class="btn reject" href="/confirm/{action_id}?action=reject">Reject</a>
</body></html>"""


def _render_result(title: str, message: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>Sentinel — {title}</title>
<style>body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}</style>
</head><body><h1>{title}</h1><p>{message}</p></body></html>"""
