"""Redis-based session write lock — prevents concurrent writes to the same session."""

from __future__ import annotations

import asyncio

from agent1.common.logging import get_logger
from agent1.common.redis_client import get_redis

log = get_logger(__name__)

SESSION_LOCK_PREFIX = "agent1:session:lock:"
LOCK_TTL_SECONDS = 60
POLL_INTERVAL = 0.5
MAX_WAIT_SECONDS = 30


async def acquire_session_lock(session_key: str) -> bool:
    """Acquire a write lock for the given session key.

    Polls every 0.5s, waits up to 30s.  Returns True if acquired.
    """
    redis = await get_redis()
    key = f"{SESSION_LOCK_PREFIX}{session_key}"
    elapsed = 0.0

    while elapsed < MAX_WAIT_SECONDS:
        acquired = await redis.set(key, "1", nx=True, ex=LOCK_TTL_SECONDS)
        if acquired:
            log.debug("session_lock_acquired", session_key=session_key)
            return True
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    log.warning("session_lock_timeout", session_key=session_key, waited=elapsed)
    return False


async def release_session_lock(session_key: str) -> None:
    """Release the session write lock."""
    redis = await get_redis()
    key = f"{SESSION_LOCK_PREFIX}{session_key}"
    await redis.delete(key)
    log.debug("session_lock_released", session_key=session_key)
