"""Label schema — defines the complete label system for MemOS."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LabelDef:
    name: str
    description: str
    color: str
    category: str  # type | module | priority | status


# Type labels
TYPE_LABELS = [
    LabelDef("bug", "Defect or broken behavior", "d73a4a", "type"),
    LabelDef("enhancement", "New feature or improvement", "a2eeef", "type"),
    LabelDef("documentation", "Documentation only", "0075ca", "type"),
    LabelDef("question", "Question or discussion", "d876e3", "type"),
    LabelDef("performance", "Performance issue", "fbca04", "type"),
    LabelDef("security", "Security vulnerability", "b60205", "type"),
    LabelDef("regression", "Regression from a previous version", "e11d48", "type"),
    LabelDef("duplicate", "Duplicate issue", "cfd3d7", "type"),
    LabelDef("wontfix", "Will not be fixed", "ffffff", "type"),
]

# Module labels (simplified to 4)
MODULE_LABELS = [
    LabelDef("mod:plugin", "Plugin/adapter/bridge layer", "c5def5", "module"),
    LabelDef("mod:memos", "Core memos logic (memory, MCP, hub, scheduler, schema)", "bfd4f2", "module"),
    LabelDef("mod:docs", "Documentation", "0e8a16", "module"),
    LabelDef("mod:infra", "CI/CD, Docker, deployment, infrastructure", "f9d0c4", "module"),
]

# Priority labels
PRIORITY_LABELS = [
    LabelDef("P0:critical", "Blocking: data loss, security, crash", "b60205", "priority"),
    LabelDef("P1:important", "Core functionality affected, has workaround", "d93f0b", "priority"),
    LabelDef("P2:normal", "Standard priority", "fbca04", "priority"),
    LabelDef("P3:nice-to-have", "Low priority, cosmetic, docs", "c2e0c6", "priority"),
]

# Status labels
STATUS_LABELS = [
    LabelDef("needs-triage", "New, awaiting classification", "e4e669", "status"),
    LabelDef("needs-info", "Missing information, waiting for author", "d4c5f9", "status"),
    LabelDef("needs-review", "PR awaiting review", "fbca04", "status"),
    LabelDef("ai-task", "Can be handled by the agent", "1d76db", "status"),
    LabelDef("ai-reviewing", "Agent is currently processing", "0052cc", "status"),
    LabelDef("stale", "No activity for 30+ days", "ededed", "status"),
    LabelDef("do not close", "Protected from stale bot", "006b75", "status"),
]

ALL_LABELS = TYPE_LABELS + MODULE_LABELS + PRIORITY_LABELS + STATUS_LABELS


def get_label_names_by_category(category: str) -> list[str]:
    return [l.name for l in ALL_LABELS if l.category == category]
