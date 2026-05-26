"""Router — classifies events, dispatches to handlers, with full enhancement suite."""

from __future__ import annotations

import logging

from src.agent.state import get_settings
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
            case "pr_merged":
                result = await _handle_pr_merged(event)
            case "ignore":
                result = {"summary": "ignored"}
            case _:
                result = {"summary": f"unhandled: {complexity}"}

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

    if event_type == "issues" and action == "labeled":
        label_name = payload.get("label", {}).get("name", "")
        if label_name == "ai-task":
            return "dev"

    if event_type == "issues" and action == "opened":
        return "classify"

    if event_type == "pull_request" and action in ("opened", "synchronize"):
        return "pr_review"

    if event_type == "pull_request" and action == "closed":
        if payload.get("pull_request", {}).get("merged"):
            return "pr_merged"

    if event_type in ("ping",) or (event_type == "issues" and action in ("closed", "deleted")):
        return "fast"

    return "ignore"


async def _handle_fast(event: dict) -> dict:
    return {"summary": "fast: acknowledged"}


async def _handle_new_issue(event: dict) -> dict:
    """Full new issue pipeline: dedup → classify → template check → ai-task/notify."""
    from src.labels.classifier import _classify_type, _classify_module, _classify_priority, _llm_classify
    from src.tools.github_write import add_labels, post_comment
    from src.agent.notify_handler import notify_needs_human
    from src.agent.duplicate_detector import find_duplicates

    payload = event.get("payload", {})
    issue = payload.get("issue", {})
    number = issue.get("number")
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    text = f"{title} {body}".lower()

    # Step 1: Duplicate detection
    duplicates = await find_duplicates(issue)
    if duplicates:
        refs = ", ".join(f"#{n}" for n in duplicates[:3])
        await post_comment(number, (
            f"This issue may be a duplicate of {refs}.\n\n"
            "If your issue is different, please clarify what distinguishes it.\n\n"
            "---\n*Detected by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
        ))
        await add_labels(number, ["duplicate"])
        return {"summary": f"#{number} marked as potential duplicate of {refs}"}

    # Step 2: Classify (rule-based)
    type_label = _classify_type(text)
    module_label = _classify_module(text)

    # Step 3: LLM fallback only if rules fail
    if not type_label or not module_label:
        llm_labels = await _llm_classify(issue, missing_type=not type_label, missing_module=not module_label)
        for l in llm_labels:
            if l in ("plugin", "memos") and not module_label:
                module_label = l
            elif not type_label:
                type_label = l

    priority_label = _classify_priority(text, type_label, module_label)

    # Step 4: Template check (bug without repro → ask for info)
    if type_label == "bug" and len(body) < 80:
        await post_comment(number, (
            "Thanks for reporting this bug! To help us investigate, please provide:\n\n"
            "1. **Steps to reproduce**\n"
            "2. **Expected vs actual behavior**\n"
            "3. **Environment** (OS, Python/Node version, MemOS version)\n"
            "4. **Error logs** (if any)\n\n"
            "Adding `needs-info` label until we have more details.\n\n"
            "---\n*Managed by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
        ))
        labels_to_add = ["needs-info"]
        if module_label:
            labels_to_add.append(module_label)
        await add_labels(number, labels_to_add)
        return {"summary": f"#{number} needs-info (bug without details)"}

    # Step 5: Auto-reply for questions
    if type_label == "question":
        await post_comment(number, (
            f"Thanks for your question!\n\n"
            "A maintainer will review this. In the meantime, you might find relevant info in:\n"
            "- [MemOS Docs](https://github.com/MemTensor/MemOS/tree/main/docs)\n"
            "- [MemOS Examples](https://github.com/MemTensor/MemOS/tree/main/examples)\n\n"
            "---\n*Managed by [memos-sentinel](https://github.com/MemTensor/memos-sentinel)*"
        ))
        labels_to_add = ["question"]
        if module_label:
            labels_to_add.append(module_label)
        await add_labels(number, labels_to_add)
        await notify_needs_human(number, title, module_label, priority_label, "question")
        return {"summary": f"#{number} question auto-replied + notified human"}

    # Step 6: ai-task decision (rule pre-filter before LLM)
    labels_to_add = []
    if module_label:
        labels_to_add.append(module_label)

    can_ai_fix = _rule_ai_task_prefilter(type_label, body)
    if can_ai_fix is None:
        # Borderline → ask LLM
        from src.phase1 import _llm_ai_task_judge
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


def _rule_ai_task_prefilter(type_label: str | None, body: str) -> bool | None:
    """Rule-based fast accept/reject for ai-task. Returns None if uncertain.

    This avoids calling LLM for obvious cases.
    """
    # Hard NO
    if type_label in ("question", "performance", "enhancement"):
        return False

    # Hard YES
    if type_label == "documentation":
        return True
    if type_label == "regression":
        return True

    # Bug: check body quality
    if type_label == "bug":
        if len(body) < 50:
            return False
        if any(s in body.lower() for s in ("```", "traceback", "error:", "exception")):
            return None  # Promising, let LLM confirm
        if len(body) > 300:
            return None  # Detailed enough, let LLM decide
        return False  # Short bug without code/error → no

    return None  # Uncertain → LLM


async def _handle_pr(event: dict) -> dict:
    """Handle new/updated PR: label + review."""
    from src.agent.full_agent import review_pr
    from src.tools.github_write import add_labels
    from src.labels.classifier import _classify_module

    payload = event.get("payload", {})
    pr = payload.get("pull_request", {})
    number = pr.get("number")
    title = pr.get("title", "")

    # Auto-label PR by changed files
    files = [f.get("filename", "") for f in pr.get("files", [])] if "files" in pr else []
    if not files:
        # Fetch files from title/body heuristic
        text = f"{title} {pr.get('body', '')}".lower()
        module = _classify_module(text)
        if module:
            try:
                await add_labels(number, [module])
            except Exception:
                pass

    # Review
    result = await review_pr(number)
    return {"summary": f"reviewed PR #{number}", **result}


async def _handle_ai_task(event: dict) -> dict:
    """Handle ai-task trigger: launch dev agent."""
    from src.agent.dev_agent import run_dev_agent_for_issue

    payload = event.get("payload", {})
    issue = payload.get("issue", {})
    number = issue.get("number")

    current_labels = [l["name"] for l in issue.get("labels", [])]
    if "ai-reviewing" in current_labels:
        return {"summary": f"#{number} already being processed"}

    result = await run_dev_agent_for_issue(number)
    return {"summary": f"dev-agent processed #{number}", **result}


async def _handle_pr_merged(event: dict) -> dict:
    """Handle merged PR: close linked issue + track for release notes."""
    payload = event.get("payload", {})
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    pr_body = pr.get("body", "") or ""
    pr_title = pr.get("title", "")

    # Find linked issue from PR body (Closes #xxx, Fixes #xxx)
    import re
    linked_issues = re.findall(r"(?:closes|fixes|resolves)\s+#(\d+)", pr_body.lower())

    # Also check PR title
    title_issues = re.findall(r"\(#(\d+)\)", pr_title)

    all_linked = list(set(linked_issues + title_issues))

    return {
        "summary": f"PR #{pr_number} merged, linked issues: {all_linked}",
        "linked_issues": all_linked,
        "pr_title": pr_title,
    }


def _compute_lock_key(event: dict) -> str | None:
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
            f"ERROR {event_type}.{action}{number}: {str(error)[:200]}"
        )
    except Exception:
        pass
