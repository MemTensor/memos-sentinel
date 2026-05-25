"""Reply engine — generates templated or LLM-powered replies to issues."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_templates: dict | None = None


def _load_templates() -> dict:
    global _templates
    if _templates is None:
        template_path = Path(__file__).parent.parent.parent / "config" / "templates.yaml"
        if template_path.exists():
            _templates = yaml.safe_load(template_path.read_text())
        else:
            _templates = {}
    return _templates


async def generate_reply(issue: dict) -> str | None:
    """Generate a reply for an issue based on its type and content.

    Flow:
    1. Check if a template matches the issue type
    2. If yes, render template with context
    3. If no, use LLM to generate a contextual reply
    """
    labels = [l.get("name", "") for l in issue.get("labels", [])]
    title = issue.get("title", "")
    body = issue.get("body", "") or ""

    templates = _load_templates()

    # Template-based reply for common patterns
    if "question" in labels and "needs-info" not in labels:
        template = templates.get("question_ack")
        if template:
            return template.format(title=title)

    if "bug" in labels and not body.strip():
        template = templates.get("bug_needs_info")
        if template:
            return template

    if "enhancement" in labels:
        template = templates.get("enhancement_ack")
        if template:
            return template.format(title=title)

    # For complex cases, use LLM
    if _needs_llm_reply(issue):
        return await _llm_reply(issue)

    return None


def _needs_llm_reply(issue: dict) -> bool:
    """Determine if an issue needs an LLM-generated reply."""
    body = issue.get("body", "") or ""
    return len(body) > 100 and "?" in body


async def _llm_reply(issue: dict) -> str | None:
    """Generate a reply using the light LLM model."""
    from src.llm.client import get_light_model

    model = get_light_model()
    # Placeholder for actual LangChain implementation
    return None
