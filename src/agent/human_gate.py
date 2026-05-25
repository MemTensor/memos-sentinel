"""Human Gate — approval flow for dangerous actions (close, approve, merge)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from src.agent.state import get_settings

logger = logging.getLogger(__name__)


class ApprovalRequired(Exception):
    """Raised when an action requires human approval."""

    def __init__(self, action_id: str, details: str):
        self.action_id = action_id
        self.details = details
        super().__init__(f"Approval required: {details}")


async def request_approval(
    action: str,
    target: int | str,
    details: str,
) -> str:
    """Request human approval for a dangerous action.

    Creates a pending approval record, sends DingTalk notification,
    and returns the approval ID.
    """
    from src.store.db import get_session
    from src.store.models import PendingAction
    from src.notify.dingtalk import send_approval_request

    settings = get_settings()
    action_id = str(uuid.uuid4())

    async with get_session() as session:
        pending = PendingAction(
            id=action_id,
            action_type=action,
            target=str(target),
            details=details,
            created_at=datetime.utcnow(),
            status="pending",
        )
        session.add(pending)
        await session.commit()

    confirm_url = f"{settings.web_base_url}/confirm/{action_id}"
    await send_approval_request(
        action=action,
        target=target,
        details=details,
        confirm_url=confirm_url,
    )

    logger.info(f"Approval requested: {action} on {target} (id={action_id})")
    return action_id


async def check_approval(action_id: str) -> str:
    """Check the status of a pending approval."""
    from src.store.db import get_session
    from src.store.models import PendingAction

    async with get_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(PendingAction).where(PendingAction.id == action_id)
        )
        pending = result.scalar_one_or_none()
        if not pending:
            return "not_found"
        return pending.status


async def approve_action(action_id: str) -> bool:
    """Approve a pending action."""
    from src.store.db import get_session
    from src.store.models import PendingAction

    async with get_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(PendingAction).where(PendingAction.id == action_id)
        )
        pending = result.scalar_one_or_none()
        if not pending or pending.status != "pending":
            return False
        pending.status = "approved"
        pending.resolved_at = datetime.utcnow()
        await session.commit()
    return True


async def reject_action(action_id: str) -> bool:
    """Reject a pending action."""
    from src.store.db import get_session
    from src.store.models import PendingAction

    async with get_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(PendingAction).where(PendingAction.id == action_id)
        )
        pending = result.scalar_one_or_none()
        if not pending or pending.status != "pending":
            return False
        pending.status = "rejected"
        pending.resolved_at = datetime.utcnow()
        await session.commit()
    return True
