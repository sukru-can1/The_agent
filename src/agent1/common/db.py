"""asyncpg database connection pool management."""

from __future__ import annotations

import asyncpg

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

_pool: asyncpg.Pool | None = None
_feedbacks_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the main database connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
        )
        log.info("database_pool_created", dsn=settings.database_url[:30] + "...")
    return _pool


async def get_feedbacks_pool() -> asyncpg.Pool | None:
    """Get or create read-only connection pool to the feedbacks database."""
    global _feedbacks_pool
    settings = get_settings()
    if not settings.feedbacks_database_url:
        return None
    if _feedbacks_pool is None:
        _feedbacks_pool = await asyncpg.create_pool(
            dsn=settings.feedbacks_database_url,
            min_size=1,
            max_size=3,
        )
        log.info("feedbacks_pool_created")
    return _feedbacks_pool


async def close_pools() -> None:
    """Close all database connection pools."""
    global _pool, _feedbacks_pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("database_pool_closed")
    if _feedbacks_pool is not None:
        await _feedbacks_pool.close()
        _feedbacks_pool = None
        log.info("feedbacks_pool_closed")
