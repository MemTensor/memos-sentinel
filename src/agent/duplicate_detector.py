"""Duplicate detection — finds similar existing issues to avoid duplicates."""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.75


async def find_duplicates(issue: dict, max_candidates: int = 5) -> list[int]:
    """Find potential duplicate issues based on title and body similarity.

    Strategy:
    1. Title similarity (SequenceMatcher ratio > 0.75)
    2. If title match found, verify body similarity
    3. Return sorted by confidence

    Returns list of issue numbers that are potential duplicates.
    """
    from src.tools.github_read import search_issues

    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    issue_number = issue.get("number")

    # Search for issues with similar keywords
    keywords = _extract_keywords(title)
    if not keywords:
        return []

    query = " ".join(keywords[:5])
    candidates = await search_issues(query=query, state="all")

    duplicates = []
    for candidate in candidates[:20]:
        if candidate.get("number") == issue_number:
            continue

        cand_title = candidate.get("title", "")
        title_ratio = SequenceMatcher(None, title.lower(), cand_title.lower()).ratio()

        if title_ratio >= SIMILARITY_THRESHOLD:
            cand_body = candidate.get("body", "") or ""
            body_ratio = SequenceMatcher(None, body.lower()[:500], cand_body.lower()[:500]).ratio()

            if body_ratio >= 0.5 or title_ratio >= 0.9:
                duplicates.append({
                    "number": candidate["number"],
                    "confidence": (title_ratio + body_ratio) / 2,
                })

    duplicates.sort(key=lambda x: x["confidence"], reverse=True)
    return [d["number"] for d in duplicates[:max_candidates]]


def _extract_keywords(title: str) -> list[str]:
    """Extract meaningful keywords from issue title."""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "it", "this", "that", "not", "no", "but", "or", "and", "if",
    }
    words = title.lower().split()
    return [w for w in words if w not in stop_words and len(w) > 2]
