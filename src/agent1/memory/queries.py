"""Common memory queries used by multiple components."""

from __future__ import annotations

from agent1.common.db import get_pool
from agent1.common.logging import get_logger

log = get_logger(__name__)


async def get_recent_incidents(category: str | None = None, limit: int = 10) -> list[dict]:
    """Get recent incidents, optionally filtered by category."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category:
            rows = await conn.fetch(
                """
                SELECT id, category, description, resolution, market, tags, timestamp
                FROM incidents
                WHERE category = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                category,
                limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, category, description, resolution, market, tags, timestamp FROM incidents ORDER BY timestamp DESC LIMIT $1",
                limit,
            )
    return [dict(r) for r in rows]


async def get_active_knowledge(category: str | None = None) -> list[dict]:
    """Get all active knowledge entries, optionally filtered."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category:
            rows = await conn.fetch(
                "SELECT id, category, content, source, confidence FROM knowledge WHERE active = true AND category = $1 ORDER BY confidence DESC",
                category,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, category, content, source, confidence FROM knowledge WHERE active = true ORDER BY confidence DESC",
            )
    return [dict(r) for r in rows]


async def get_sender_history(email_address: str, limit: int = 5) -> list[dict]:
    """Get past actions and conversations involving a specific email address."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, timestamp, system, action_type, details, outcome
            FROM actions_log
            WHERE details::text ILIKE $1
            ORDER BY timestamp DESC
            LIMIT $2
            """,
            f"%{email_address}%",
            limit,
        )
    return [dict(r) for r in rows]
