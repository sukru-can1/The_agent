"""Redis async client management."""

from __future__ import annotations

import redis.asyncio as aioredis

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the Redis client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        await _client.ping()
        log.info("redis_connected", url=settings.redis_url)
    return _client


async def close_redis() -> None:
    """Close the Redis connection."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        log.info("redis_closed")
