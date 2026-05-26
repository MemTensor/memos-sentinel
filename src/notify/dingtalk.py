"""DingTalk notification integration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse

import httpx

from src.agent.state import get_settings

logger = logging.getLogger(__name__)


def _sign(secret: str) -> tuple[str, str]:
    """Generate DingTalk signature."""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.HMAC(
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
        "text": {"content": f"[MemOS] [Sentinel] {message}"},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errcode") == 0:
                    return True
                logger.error(f"DingTalk API error: {data}")
                return False
            logger.error(f"DingTalk HTTP error: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"DingTalk send failed: {e}")
        return False
