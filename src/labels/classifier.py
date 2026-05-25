"""Label classifier — rule-based + LLM classification with simplified 4-module system."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_label_config: dict | None = None


def _load_label_config() -> dict:
    global _label_config
    if _label_config is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "labels.yaml"
        if config_path.exists():
            _label_config = yaml.safe_load(config_path.read_text())
        else:
            _label_config = {}
    return _label_config


async def classify_issue(issue: dict) -> list[str]:
    """Classify an issue into the 3-dimensional label system.

    Dimensions:
    1. Type (bug, enhancement, documentation, question, etc.)
    2. Module (plugin, memos, docs, infra) — simplified to 4
    3. Priority (P0-P3)
    """
    title = (issue.get("title") or "").lower()
    body = (issue.get("body") or "").lower()
    text = f"{title} {body}"

    labels = []

    # Dimension 1: Type
    type_label = _classify_type(text)
    if type_label:
        labels.append(type_label)

    # Dimension 2: Module (simplified to 4)
    module_label = _classify_module(text)
    if module_label:
        labels.append(module_label)

    # Dimension 3: Priority
    priority_label = _classify_priority(text, type_label, module_label)
    labels.append(priority_label)

    # If rule-based fails, fallback to LLM
    if not type_label or not module_label:
        llm_labels = await _llm_classify(issue, missing_type=not type_label, missing_module=not module_label)
        labels.extend(llm_labels)

    return labels


def _classify_type(text: str) -> str | None:
    """Rule-based type classification."""
    type_rules = {
        "bug": ["bug", "fix", "crash", "error", "broken", "fail", "issue", "wrong"],
        "enhancement": ["feat", "add", "support", "request", "improve", "enhance"],
        "documentation": ["doc", "readme", "typo", "translate", "wiki"],
        "question": ["how to", "question", "help", "what is", "why does"],
        "performance": ["slow", "perf", "timeout", "latency", "memory leak"],
        "security": ["security", "vulnerability", "cve", "auth bypass"],
        "regression": ["regression", "broke", "worked before", "downgrade"],
    }

    for label, keywords in type_rules.items():
        if any(kw in text for kw in keywords):
            return label
    return None


def _classify_module(text: str) -> str | None:
    """Rule-based module classification (4 modules only).

    Simplified system:
    - mod:plugin → all plugin/adapter/bridge code
    - mod:memos  → core memos logic (memory, MCP, hub, schema, scheduler)
    - mod:docs   → documentation
    - mod:infra  → CI/CD, docker, deployment
    """
    module_rules = {
        "mod:plugin": [
            "plugin", "bridge", "viewer", "install.sh", "adapter",
            "hermes", "openclaw", "openwork", "electron", "cloud plugin",
        ],
        "mod:memos": [
            "memory", "recall", "scheduler", "mcp", "search_memory",
            "hub", "sharing", "schema", "model", "interface",
            "evaluation", "benchmark", "database", "sqlite", "neo4j", "qdrant",
        ],
        "mod:docs": [
            "doc", "readme", "translate", "wiki", "guide", "tutorial",
        ],
        "mod:infra": [
            "ci", "docker", "deploy", "helm", "github action",
            "workflow", "pipeline", "build", "release",
        ],
    }

    for label, keywords in module_rules.items():
        if any(kw in text for kw in keywords):
            return label
    return None


def _classify_priority(text: str, type_label: str | None, module_label: str | None) -> str:
    """Determine priority based on type + module + keywords."""
    # P0: critical
    if type_label == "regression" or type_label == "security":
        return "P0:critical"
    if any(kw in text for kw in ("crash", "data loss", "security")):
        return "P0:critical"

    # P1: important
    if type_label == "bug" and module_label in ("mod:plugin", "mod:memos"):
        return "P1:important"

    # P3: nice-to-have
    if type_label in ("documentation", "question"):
        return "P3:nice-to-have"

    # P2: normal (default)
    return "P2:normal"


async def _llm_classify(
    issue: dict, missing_type: bool = False, missing_module: bool = False
) -> list[str]:
    """Fallback: use LLM for classification when rules don't match."""
    from src.llm.client import get_light_model

    # Placeholder for actual LangChain implementation
    return []
