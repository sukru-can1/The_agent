"""Feedback pattern analyzer — extracts learning from draft edits."""

from __future__ import annotations

from agent1.common.db import get_pool
from agent1.common.logging import get_logger

log = get_logger(__name__)


async def analyze_edit_patterns(min_edits: int = 5) -> list[dict]:
    """Analyze draft edit patterns grouped by sender domain and category.

    Returns patterns where the agent consistently gets corrected,
    so they can be stored as learned knowledge.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT sender_domain, category,
                   COUNT(*) as edit_count,
                   AVG(edit_ratio) as avg_edit_ratio,
                   AVG(edit_distance) as avg_edit_distance
            FROM draft_feedback
            GROUP BY sender_domain, category
            HAVING COUNT(*) >= $1 AND AVG(edit_ratio) > 0.1
            ORDER BY avg_edit_ratio DESC
            """,
            min_edits,
        )

    patterns = []
    for row in rows:
        patterns.append({
            "sender_domain": row["sender_domain"],
            "category": row["category"],
            "edit_count": row["edit_count"],
            "avg_edit_ratio": round(float(row["avg_edit_ratio"]), 3),
            "avg_edit_distance": round(float(row["avg_edit_distance"]), 1),
        })

    log.info("edit_patterns_analyzed", count=len(patterns))
    return patterns


async def get_edit_examples(sender_domain: str, limit: int = 5) -> list[dict]:
    """Get recent edit examples for a specific sender domain."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT df.draft_id, ed.draft_body, ed.edited_body,
                   df.edit_distance, df.edit_ratio, df.created_at
            FROM draft_feedback df
            JOIN email_drafts ed ON ed.id = df.draft_id
            WHERE df.sender_domain = $1
            ORDER BY df.created_at DESC
            LIMIT $2
            """,
            sender_domain,
            limit,
        )
    return [dict(r) for r in rows]
