"""Full Agent — PR code review using Opus."""

from __future__ import annotations

import logging

from src.agent.notify_handler import notify_pr_reviewed

logger = logging.getLogger(__name__)


async def review_pr(pr_number: int) -> dict:
    """Review a PR using Claude Opus: read diff, generate structured review."""
    from src.tools.github_read import read_pr, get_pr_reviews
    from src.tools.github_write import submit_review, add_labels
    from src.llm.client import get_heavy_model
    from src.labels.classifier import _classify_module

    # Gather context
    pr_detail = await read_pr(pr_number)
    existing_reviews = await get_pr_reviews(pr_number)

    title = pr_detail.get("title", "")
    body = pr_detail.get("body", "") or ""
    diff = pr_detail.get("diff", "")[:30000]
    files = pr_detail.get("files", [])
    file_names = [f.get("filename", "") for f in files]

    # Skip if already reviewed by us
    for review in existing_reviews:
        if review.get("user", {}).get("login") in ("Memtensor-AI", "memos-sentinel[bot]"):
            return {"action": "skipped", "reason": "already reviewed"}

    # Determine module label from changed files
    file_text = " ".join(file_names).lower()
    module = _classify_module(file_text)
    if module:
        try:
            await add_labels(pr_number, [module])
        except Exception:
            pass

    # Skip review for docs-only PRs
    if all(f.get("filename", "").startswith("docs/") or f.get("filename", "").endswith(".md") for f in files):
        return {"action": "skipped", "reason": "docs-only PR"}

    # Generate review with Opus
    model = get_heavy_model()
    prompt = _build_review_prompt(title, body, diff, file_names)

    try:
        response = await model.ainvoke(prompt)
        review_body = response.content

        # Determine review event based on content
        event = "COMMENT"
        content_lower = review_body.lower()
        if any(w in content_lower for w in ("blocking", "must fix", "critical bug", "security issue")):
            event = "REQUEST_CHANGES"

        # Post review
        await submit_review(pr_number, review_body, event)
        await notify_pr_reviewed(pr_number, title, event)

        return {"action": "reviewed", "event": event}
    except Exception as e:
        logger.error(f"Failed to review PR #{pr_number}: {e}")
        return {"action": "error", "error": str(e)}


def _build_review_prompt(title: str, body: str, diff: str, files: list[str]) -> str:
    return f"""You are a senior code reviewer for the MemOS project (memory operating system with LLM integration).

Review this pull request and provide actionable feedback.

## PR Title
{title}

## PR Description
{body[:2000]}

## Changed Files
{chr(10).join(f'- {f}' for f in files[:30])}

## Diff
```diff
{diff[:25000]}
```

## Review Guidelines
1. Focus on correctness, potential bugs, and edge cases
2. Note any security concerns
3. Check for proper error handling
4. Suggest performance improvements if obvious
5. Keep feedback constructive and specific
6. Reference specific lines/files when possible
7. If the change looks good overall, say so briefly

## Response Format
Write your review as a GitHub PR review comment. Use markdown.
Start with a one-line summary (LGTM / Needs changes / Has concerns).
Then list specific findings if any.
Keep it concise — developers prefer short, actionable reviews."""
