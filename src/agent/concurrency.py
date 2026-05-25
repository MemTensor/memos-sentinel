"""Concurrency lock — prevents duplicate processing of the same issue/PR."""

from __future__ import annotations

import asyncio
import time
import logging

logger = logging.getLogger(__name__)

_locks: dict[str, float] = {}
_lock_mutex = asyncio.Lock()

LOCK_TTL_SECONDS = 300  # 5 minutes max hold time


async def acquire_lock(key: str) -> bool:
    """Try to acquire a processing lock. Returns False if already held."""
    async with _lock_mutex:
        now = time.time()
        # Expire stale locks
        if key in _locks and (now - _locks[key]) > LOCK_TTL_SECONDS:
            logger.warning(f"Expired stale lock: {key}")
            del _locks[key]

        if key in _locks:
            return False
        _locks[key] = now
        return True


async def release_lock(key: str) -> None:
    """Release a processing lock."""
    async with _lock_mutex:
        _locks.pop(key, None)


async def is_locked(key: str) -> bool:
    """Check if a key is currently locked."""
    async with _lock_mutex:
        if key not in _locks:
            return False
        if (time.time() - _locks[key]) > LOCK_TTL_SECONDS:
            del _locks[key]
            return False
        return True
