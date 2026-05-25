"""Dual-model LLM client — light model for routing + heavy model for deep tasks."""

from __future__ import annotations

import logging
from functools import lru_cache

from src.agent.state import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_light_model():
    """Get the lightweight model for routing, classification, and simple replies.

    Used for: Router, label classification, quick replies
    Suggested: Claude 3.5 Haiku or similar fast model
    """
    settings = get_settings()
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=settings.anthropic_api_key,
        max_tokens=2048,
        temperature=0,
    )


@lru_cache
def get_heavy_model():
    """Get the heavy model for deep review, code analysis, and code generation.

    Used for: PR review, bug analysis, code fixes
    Model: Claude Opus 4.6
    """
    settings = get_settings()
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model="claude-opus-4-20250514",
        api_key=settings.anthropic_api_key,
        max_tokens=8192,
        temperature=0,
    )
