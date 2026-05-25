"""DingTalk notification integration."""

from __future__ import annotations

import hashlib
import hmac
import base64
import time
import logging
import urllib.parse

import httpx

from src.agent.state import get_settings

logger = logging.getLogger(__name__)


def _sign(secret: str) -> tuple[str, str]:
    """Generate DingTalk signature."""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


async def send_notification(message: str) -> bool:
    """Send a simple text notification to DingTalk."""
    settings = get_settings()
    if not settings.dingtalk_webhook_url:
        logger.warning("DingTalk webhook URL not configured")
        return False

    url = settings.dingtalk_webhook_url
    if settings.dingtalk_secret:
        timestamp, sign = _sign(settings.dingtalk_secret)
        url += f"&timestamp={timestamp}&sign={sign}"

    payload = {
        "msgtype": "text",
        "text": {"content": f"[Sentinel] {message}"},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"DingTalk send failed: {resp.status_code} {resp.text}")
        return False


async def send_approval_request(
    action: str,
    target: int | str,
    details: str,
    confirm_url: str,
) -> bool:
    """Send an approval request notification with action link."""
    settings = get_settings()
    if not settings.dingtalk_webhook_url:
        return False

    url = settings.dingtalk_webhook_url
    if settings.dingtalk_secret:
        timestamp, sign = _sign(settings.dingtalk_secret)
        url += f"&timestamp={timestamp}&sign={sign}"

    payload = {
        "msgtype": "actionCard",
        "actionCard": {
            "title": f"Sentinel: Approval needed — {action}",
            "text": (
                f"### Action: {action}\n\n"
                f"**Target:** #{target}\n\n"
                f"**Details:** {details}\n\n"
                f"Please review and approve/reject."
            ),
            "btnOrientation": "1",
            "btns": [
                {"title": "Approve", "actionURL": f"{confirm_url}?action=approve"},
                {"title": "Reject", "actionURL": f"{confirm_url}?action=reject"},
            ],
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error(f"DingTalk approval request failed: {resp.status_code}")
        return False
