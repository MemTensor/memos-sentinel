"""GitHub Webhook handler — receives events and dispatches to Orchestrator."""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from src.agent.router import dispatch_event
from src.store.db import get_session
from src.store.models import AuditLog

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
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
    event = {
        "type": x_github_event,
        "action": event_data.get("action"),
        "payload": event_data,
    }

    logger.info(f"Received webhook: {x_github_event}/{event_data.get('action')}")

    result = await dispatch_event(event)

    async with get_session() as session:
        log = AuditLog(
            event_type=x_github_event,
            event_action=event_data.get("action"),
            target_number=_extract_number(event_data),
            result_summary=result.get("summary", ""),
        )
        session.add(log)
        await session.commit()

    return {"status": "processed", "result": result}


def _extract_number(event_data: dict) -> int | None:
    for key in ("issue", "pull_request"):
        if key in event_data:
            return event_data[key].get("number")
    return None
