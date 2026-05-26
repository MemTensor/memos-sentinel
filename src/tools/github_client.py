"""GitHub HTTP client with rate limit handling."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from src.agent.state import get_settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_rate_limit_reset: float = 0
_rate_limit_remaining: int = 5000


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo() -> str:
    return get_settings().github_target_repo


async def github_request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    headers_override: dict | None = None,
    timeout: int = 30,
) -> httpx.Response:
    """Make a GitHub API request with automatic rate limit handling.

    If rate limited (403/429), sleeps until reset time then retries.
    Updates global rate limit counters from response headers.
    """
    global _rate_limit_reset, _rate_limit_remaining

    # Pre-check: if we know we're rate limited, sleep first
    if _rate_limit_remaining <= 5:
        wait_time = _rate_limit_reset - time.time()
        if wait_time > 0:
            logger.warning(f"Rate limit low ({_rate_limit_remaining}), sleeping {wait_time:.0f}s")
            await asyncio.sleep(min(wait_time + 1, 60))

    url = f"{GITHUB_API}{path}" if path.startswith("/") else path
    hdrs = headers_override or _headers()

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, json=json, params=params, headers=hdrs)

    # Update rate limit info from headers
    _update_rate_limit(resp)

    # Handle rate limit response
    if resp.status_code in (403, 429):
        reset_header = resp.headers.get("X-RateLimit-Reset")
        retry_after = resp.headers.get("Retry-After")

        if reset_header or retry_after or "rate limit" in resp.text.lower():
            if retry_after:
                sleep_time = int(retry_after)
            elif reset_header:
                sleep_time = max(int(reset_header) - int(time.time()), 1)
            else:
                sleep_time = 60

            sleep_time = min(sleep_time, 300)
            logger.warning(f"Rate limited! Sleeping {sleep_time}s before retry")
            await asyncio.sleep(sleep_time)

            # Retry once
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url, json=json, params=params, headers=hdrs)
            _update_rate_limit(resp)

    return resp


def _update_rate_limit(resp: httpx.Response) -> None:
    """Extract rate limit info from response headers."""
    global _rate_limit_reset, _rate_limit_remaining

    remaining = resp.headers.get("X-RateLimit-Remaining")
    reset = resp.headers.get("X-RateLimit-Reset")

    if remaining is not None:
        _rate_limit_remaining = int(remaining)
    if reset is not None:
        _rate_limit_reset = float(reset)

    if _rate_limit_remaining <= 100 and _rate_limit_remaining % 50 == 0:
        logger.warning(f"GitHub API rate limit low: {_rate_limit_remaining} remaining")


def get_rate_limit_status() -> dict:
    """Get current rate limit status (for dashboard)."""
    return {
        "remaining": _rate_limit_remaining,
        "resets_at": _rate_limit_reset,
        "resets_in": max(0, int(_rate_limit_reset - time.time())),
    }
