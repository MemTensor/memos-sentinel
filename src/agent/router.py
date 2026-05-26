"""Router — classifies event complexity and dispatches to appropriate handler."""

from __future__ import annotations

import logging

from src.agent.state import AgentState, get_settings
from src.agent.concurrency import acquire_lock, release_lock

logger = logging.getLogger(__name__)


async def dispatch_event(event: dict) -> dict:
    """Entry point: route a GitHub event to the correct handler."""
    lock_key = _compute_lock_key(event)
    if lock_key and not await acquire_lock(lock_key):
        logger.warning(f"Skipped duplicate/concurrent event: {lock_key}")
        return {"summary": "skipped: concurrent lock", "lock_key": lock_key}

    try:
        complexity = classify_complexity(event)
        logger.info(f"Routed event as: {complexity}")

        match complexity:
            case "fast":
                result = await _handle_fast(event)
            case "classify":
                result = await _handle_new_issue(event)
            case "pr_review":
                result = await _handle_pr(event)
            case "dev":
                result = await _handle_ai_task(event)
            case "ignore":
                result = {"summary": "ignored"}
            case _:
                result = {"summary": f"unhandled: {complexity}"}

        # Write audit log
        await _write_audit(event, result)
        return result
    except Exception as e:
        logger.error(f"Error processing event: {e}", exc_info=True)
        await _notify_error(event, e)
        return {"summary": f"error: {e}"}
    finally:
        if lock_key:
            await release_lock(lock_key)


def classify_complexity(event: dict) -> str:
    """Route events to handlers."""
    event_type = event.get("type", "")
    action = event.get("action", "")
    payload = event.get("payload", {})

    # ai-task label added → dev path
    if event_type == "issues" and action == "labeled":
        label_name = payload.get("label", {}).get("name", "")
        if label_name == "ai-task":
            return "dev"

    # New issue → classify and label
    if event_type == "issues" and action == "opened":
        return "classify"

    # PR opened or updated → review
    if event_type == "pull_request" and action in ("opened", "synchronize"):
        return "pr_review"

    # Issue closed/deleted → fast (no-op for now)
    if event_type == "issues" and action in ("closed", "deleted"):
        return "fast"

    # Ping event
    if event_type == "ping":
        return "fast"

    return "ignore"


async def _handle_fast(event: dict) -> dict:
    """Handle simple events that don't need processing."""
    return {"summary": "fast: acknowledged"}


async def _handle_new_issue(event: dict) -> dict:
    """Handle new issue: classify → label → decide ai-task or notify human."""
    from src.labels.classifier import _classify_type, _classify_module, _classify_priority, _llm_classify
    from src.tools.github_write import add_labels
    from src.agent.notify_handler import notify_needs_human
    from src.phase1 import _llm_ai_task_judge

    payload = event.get("payload", {})
    issue = payload.get("issue", {})
    number = issue.get("number")
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    text = f"{title} {body}".lower()

    # Classify
    type_label = _classify_type(text)
    module_label = _classify_module(text)

    # LLM fallback
    if not type_label or not module_label:
        llm_labels = await _llm_classify(issue, missing_type=not type_label, missing_module=not module_label)
        for l in llm_labels:
            if l in ("plugin", "memos") and not module_label:
                module_label = l
            elif not type_label:
                type_label = l

    priority_label = _classify_priority(text, type_label, module_label)

    # Apply module label
    labels_to_add = []
    if module_label:
        labels_to_add.append(module_label)

    # Decide: ai-task or notify human
    can_ai_fix = await _llm_ai_task_judge(issue)

    if can_ai_fix:
        labels_to_add.append("ai-task")
    else:
        reason_key = type_label if type_label in ("question", "enhancement", "performance") else "vague_bug"
        await notify_needs_human(number, title, module_label, priority_label, reason_key)

    if labels_to_add:
        await add_labels(number, labels_to_add)

    return {
        "summary": f"classified #{number}: {module_label}/{type_label}, ai-task={can_ai_fix}",
        "labels_added": labels_to_add,
    }


async def _handle_pr(event: dict) -> dict:
    """Handle new/updated PR: review with Opus."""
    from src.agent.full_agent import review_pr

    payload = event.get("payload", {})
    pr = payload.get("pull_request", {})
    number = pr.get("number")

    result = await review_pr(number)
    return {"summary": f"reviewed PR #{number}", **result}


async def _handle_ai_task(event: dict) -> dict:
    """Handle ai-task trigger: launch dev agent."""
    from src.agent.dev_agent import run_dev_agent_for_issue

    payload = event.get("payload", {})
    issue = payload.get("issue", {})
    number = issue.get("number")

    # Don't process if already ai-reviewing
    current_labels = [l["name"] for l in issue.get("labels", [])]
    if "ai-reviewing" in current_labels:
        return {"summary": f"#{number} already being processed"}

    result = await run_dev_agent_for_issue(number)
    return {"summary": f"dev-agent processed #{number}", **result}


def _compute_lock_key(event: dict) -> str | None:
    """Generate a unique lock key to prevent duplicate processing."""
    event_type = event.get("type", "")
    payload = event.get("payload", {})

    number = None
    for key in ("issue", "pull_request"):
        if key in payload:
            number = payload[key].get("number")
            break

    if number is None:
        return None

    return f"{event_type}:{number}"


async def _write_audit(event: dict, result: dict) -> None:
    """Write an audit log entry for the processed event."""
    try:
        from src.store.db import get_session
        from src.store.models import AuditLog

        payload = event.get("payload", {})
        number = None
        for key in ("issue", "pull_request"):
            if key in payload:
                number = payload[key].get("number")
                break

        async with get_session() as session:
            log = AuditLog(
                event_type=event.get("type", ""),
                event_action=event.get("action", ""),
                target_number=number,
                result_summary=result.get("summary", "")[:500],
            )
            session.add(log)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to write audit log: {e}")


async def _notify_error(event: dict, error: Exception) -> None:
    """Send DingTalk alert when agent encounters an unhandled error."""
    try:
        from src.notify.dingtalk import send_notification

        event_type = event.get("type", "?")
        action = event.get("action", "?")
        payload = event.get("payload", {})
        number = ""
        for key in ("issue", "pull_request"):
            if key in payload:
                number = f" #{payload[key].get('number', '')}"
                break

        await send_notification(
            f"ERROR processing {event_type}.{action}{number}: {str(error)[:200]}"
        )
    except Exception:
        pass
