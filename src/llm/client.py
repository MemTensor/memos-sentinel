"""Dual-model LLM client — OpenAI-compatible relay to internal API."""

from __future__ import annotations

import logging
from functools import lru_cache

from src.agent.state import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_light_model():
    """Lightweight model for routing, classification, ai-task judgment.

    Model: Claude Haiku 4.5 (via OpenAI-compatible relay)
    """
    settings = get_settings()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.light_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        max_tokens=2048,
        temperature=0,
    )


@lru_cache
def get_heavy_model():
    """Heavy model for PR review, code analysis, code generation.

    Model: Claude Opus 4.6 (via OpenAI-compatible relay)
    """
    settings = get_settings()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.heavy_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        max_tokens=8192,
        temperature=0.2,
    )
