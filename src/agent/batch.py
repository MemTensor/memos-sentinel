"""Batch processing — Phase 1 scan and bulk operations."""

from __future__ import annotations

import logging
from src.agent.state import get_settings

logger = logging.getLogger(__name__)


async def scan_all_issues() -> dict:
    """Scan all open issues and classify them."""
    from src.tools.github_read import list_open_issues
    from src.labels.classifier import classify_issue

    issues = await list_open_issues()
    report = {"total": len(issues), "classified": [], "errors": []}

    for issue in issues:
        try:
            labels = await classify_issue(issue)
            report["classified"].append({
                "number": issue["number"],
                "title": issue["title"],
                "current_labels": [l["name"] for l in issue.get("labels", [])],
                "suggested_labels": labels,
            })
        except Exception as e:
            report["errors"].append({"number": issue["number"], "error": str(e)})
            logger.error(f"Failed to classify issue #{issue['number']}: {e}")

    return report


async def scan_all_prs() -> dict:
    """Scan all open PRs and generate review priority list."""
    from src.tools.github_read import list_open_prs, list_pr_checks

    prs = await list_open_prs()
    report = {"total": len(prs), "prs": []}

    for pr in prs:
        ci_status = await list_pr_checks(pr["number"])
        report["prs"].append({
            "number": pr["number"],
            "title": pr["title"],
            "author": pr.get("user", {}).get("login", ""),
            "ci_status": ci_status.get("conclusion", "unknown"),
            "updated_at": pr.get("updated_at", ""),
            "labels": [l["name"] for l in pr.get("labels", [])],
        })

    return report


async def execute_batch_labels(plan: list[dict], dry_run: bool = True) -> dict:
    """Execute batch label changes based on the scan report.

    Args:
        plan: List of {"number": int, "add": [...], "remove": [...]}
        dry_run: If True, only log without making changes
    """
    from src.tools.github_write import add_labels, remove_labels

    results = {"applied": 0, "skipped": 0, "errors": []}

    for item in plan:
        number = item["number"]
        to_add = item.get("add", [])
        to_remove = item.get("remove", [])

        if dry_run:
            logger.info(f"[DRY-RUN] #{number}: +{to_add} -{to_remove}")
            results["skipped"] += 1
            continue

        try:
            if to_add:
                await add_labels(number, to_add)
            if to_remove:
                await remove_labels(number, to_remove)
            results["applied"] += 1
        except Exception as e:
            results["errors"].append({"number": number, "error": str(e)})

    return results
