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
    """Rule-based type classification.

    Order matters — more specific types checked first to avoid
    'fix' in title catching everything as 'bug'.
    """
    # Check regression first (most specific)
    if any(kw in text for kw in ("regression", "worked before", "downgrade")):
        return "regression"

    if any(kw in text for kw in ("security", "vulnerability", "cve", "auth bypass")):
        return "security"

    # Documentation
    if any(kw in text for kw in ("translate", "typo", "readme", "api docs")):
        return "documentation"

    # Questions / discussions
    if any(kw in text for kw in ("discussion", "how should", "question", "feedback")):
        return "question"

    # Performance
    if any(kw in text for kw in ("slow", "perf", "timeout", "latency", "memory leak", "100% cpu", "too slow")):
        return "performance"

    # Enhancement — check BEFORE bug, because "feat:" and "feature request" are explicit
    if any(kw in text for kw in ("feat:", "feature request", "feature/", "enhancement", "希望", "建议", "能否", "support")):
        return "enhancement"

    # Bug — "fix:" prefix, explicit "bug", crash/error signals
    if any(kw in text for kw in ("bug", "crash", "broken", "fail", "error", "breaks", "not working", "not found", "mismatch")):
        return "bug"
    # "fix:" in title strongly implies bug
    if "fix:" in text or "fix(" in text:
        return "bug"

    # Refactor
    if any(kw in text for kw in ("refactor", "remove dead", "cleanup")):
        return "enhancement"

    return None


def _classify_module(text: str) -> str | None:
    """Rule-based module classification (2 modules).

    Simplified system:
    - plugin → everything under apps/ (plugin, adapter, bridge, hermes, openclaw, openwork, viewer)
    - memos  → everything else (core memory, MCP, scheduler, API, etc.)
    """
    plugin_keywords = [
        "plugin", "bridge", "viewer", "install.sh", "adapter",
        "hermes", "openclaw", "openwork", "electron", "cloud plugin",
        "memos-local", "qclaw", "copaw", "gateway",
        "openclaw-local", "registertools", "registermemorycapability",
    ]

    if any(kw in text for kw in plugin_keywords):
        return "plugin"

    memos_keywords = [
        "memory", "recall", "scheduler", "mcp", "search_memory",
        "hub", "sharing", "schema", "model", "interface",
        "evaluation", "benchmark", "database", "sqlite", "neo4j", "qdrant",
        "embedding", "vector", "chunk", "episode", "reward",
        "dream", "skill", "cube", "product", "knowledge",
        "docker", "deploy", "ci", "api", "http",
        "doc", "translate", "readme",
    ]

    if any(kw in text for kw in memos_keywords):
        return "memos"

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
    import json as json_mod
    from src.llm.client import get_light_model

    title = issue.get("title", "")
    body = (issue.get("body") or "")[:1000]

    fields_needed = []
    if missing_type:
        fields_needed.append('"type": one of [bug, enhancement, documentation, question, performance, security, regression]')
    if missing_module:
        fields_needed.append('"module": one of [plugin, memos]. plugin = anything related to apps/ directory (plugins, adapters, bridge, hermes, openclaw, openwork, viewer, gateway). memos = everything else (core memory, MCP, scheduler, API, database, docs, infra)')

    prompt = f"""Classify this GitHub issue. Respond with ONLY a JSON object.

Title: {title}
Body: {body[:800]}

Return JSON with these fields:
{chr(10).join(f"- {f}" for f in fields_needed)}

JSON:"""

    model = get_light_model()
    try:
        response = await model.ainvoke(prompt)
        content = response.content.strip()
        # Extract JSON from response
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            result = json_mod.loads(json_str)
        else:
            return []

        labels = []
        if missing_type and "type" in result:
            t = result["type"].lower().strip()
            valid_types = {"bug", "enhancement", "documentation", "question", "performance", "security", "regression"}
            if t in valid_types:
                labels.append(t)
        if missing_module and "module" in result:
            m = result["module"].lower().strip()
            if m in ("plugin", "memos"):
                labels.append(m)
        return labels
    except Exception as e:
        logger.warning(f"LLM classify failed for #{issue.get('number')}: {e}")
        return []
