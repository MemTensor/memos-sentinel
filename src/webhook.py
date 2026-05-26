"""GitHub Webhook handler — receives events and dispatches to Orchestrator."""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from src.agent.router import dispatch_event

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.HMAC(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    payload = await request.body()

    from src.agent.state import get_settings

    settings = get_settings()

    if settings.github_webhook_secret:
        if not x_hub_signature_256 or not verify_signature(
            payload, x_hub_signature_256, settings.github_webhook_secret
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")

    event_data = await request.json()

    # Ignore bot's own actions to prevent loops
    sender = event_data.get("sender", {}).get("login", "")
    if sender in ("memos-sentinel[bot]", "Memtensor-AI"):
        return {"status": "skipped", "reason": "self-event"}

    event = {
        "type": x_github_event,
        "action": event_data.get("action"),
        "payload": event_data,
    }

    logger.info(f"Webhook: {x_github_event}/{event_data.get('action')} from {sender}")

    result = await dispatch_event(event)
    return {"status": "processed", "result": result}
