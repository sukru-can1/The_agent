"""Redis-based event deduplication."""

from __future__ import annotations

from agent1.common.redis_client import get_redis
from agent1.common.settings import get_settings
from agent1.queue.events import dedup_key


async def is_duplicate(source: str, identifier: str) -> bool:
    """Check if an event with this source+identifier was already processed.

    Returns True if duplicate (skip), False if new (process).
    """
    redis = await get_redis()
    key = dedup_key(source, identifier)
    exists = await redis.exists(key)
    return bool(exists)


async def mark_processed(source: str, identifier: str) -> None:
    """Mark an event as processed for dedup purposes."""
    redis = await get_redis()
    settings = get_settings()
    key = dedup_key(source, identifier)
    await redis.set(key, "1", ex=settings.dedup_ttl_seconds)
