"""Label migrator — Phase 1 migration from old label system to new 3-dimensional system."""

from __future__ import annotations

import logging
from src.labels.schema import ALL_LABELS

logger = logging.getLogger(__name__)

MIGRATION_MAP = {
    "openclaw-local-plugin": "mod:plugin",
    "[Interface]": "mod:memos",
    "[Evaluation]": "mod:memos",
    "[MemScheduler]": "mod:memos",
    "[Database]": "mod:memos",
    "[TreeTextualMemory]": "mod:memos",
    "[BasicModules]": "mod:memos",
}

LABELS_TO_REMOVE = ["pending"]


async def create_missing_labels() -> list[str]:
    """Create all labels defined in schema that don't exist in the repo."""
    # Placeholder: will use GitHub API to create labels
    created = []
    for label_def in ALL_LABELS:
        logger.info(f"Would create label: {label_def.name} ({label_def.color})")
        created.append(label_def.name)
    return created


async def migrate_labels(dry_run: bool = True) -> dict:
    """Rename old labels and remove deprecated ones.

    Returns migration report.
    """
    from src.tools.github_read import list_open_issues
    from src.tools.github_write import add_labels, remove_labels

    report = {"renamed": [], "removed": [], "errors": []}

    issues = await list_open_issues()

    for issue in issues:
        number = issue["number"]
        current_labels = [l["name"] for l in issue.get("labels", [])]

        to_add = []
        to_remove = []

        # Rename mapped labels
        for old, new in MIGRATION_MAP.items():
            if old in current_labels:
                to_add.append(new)
                to_remove.append(old)

        # Remove deprecated labels
        for label in LABELS_TO_REMOVE:
            if label in current_labels:
                to_remove.append(label)

        if not to_add and not to_remove:
            continue

        if dry_run:
            logger.info(f"[DRY-RUN] #{number}: +{to_add} -{to_remove}")
            report["renamed"].append({"number": number, "add": to_add, "remove": to_remove})
        else:
            try:
                if to_add:
                    await add_labels(number, to_add)
                if to_remove:
                    await remove_labels(number, to_remove)
                report["renamed"].append({"number": number, "add": to_add, "remove": to_remove})
            except Exception as e:
                report["errors"].append({"number": number, "error": str(e)})

    return report
