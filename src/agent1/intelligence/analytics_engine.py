"""Analytics engine -- cross-system correlation, adaptive baselines, intelligence reports."""

from __future__ import annotations

from datetime import UTC, datetime

from agent1.common.db import get_pool
from agent1.common.logging import get_logger

log = get_logger(__name__)

# In-memory cache of baselines (refreshed weekly)
_baselines_cache: dict[tuple[str, str, int, int], dict] = {}


def is_anomaly(
    source: str,
    event_type: str,
    current_count: int,
    baseline: dict | None = None,
) -> bool:
    """Check if current_count is anomalous for this (source, event_type) at this time.

    If no baseline is available, falls back to the old fixed threshold of 3.
    """
    if baseline is None:
        return current_count >= 3

    threshold = baseline["mean"] + 2 * baseline["stddev"]
    return current_count > max(threshold, 2)


def get_baseline(source: str, event_type: str, day_of_week: int, hour_of_day: int) -> dict | None:
    """Lookup cached baseline for a specific (source, event_type, day, hour)."""
    return _baselines_cache.get((source, event_type, day_of_week, hour_of_day))


async def update_baselines() -> None:
    """Recompute baselines from 4 weeks of historical data. Run weekly."""
    global _baselines_cache
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source, event_type,
                   EXTRACT(DOW FROM created_at)::int AS dow,
                   EXTRACT(HOUR FROM created_at)::int AS hod,
                   AVG(hourly_count) AS mean_count,
                   COALESCE(STDDEV(hourly_count), 0) AS stddev_count
            FROM (
                SELECT source, event_type,
                       DATE_TRUNC('hour', created_at) AS hour_bucket,
                       COUNT(*) AS hourly_count
                FROM events
                WHERE created_at >= NOW() - INTERVAL '28 days'
                  AND status != 'dead_letter'
                GROUP BY source, event_type, hour_bucket
            ) hourly
            GROUP BY source, event_type, dow, hod
            """
        )

        new_cache: dict[tuple[str, str, int, int], dict] = {}
        for r in rows:
            key = (r["source"], r["event_type"], r["dow"], r["hod"])
            baseline = {
                "mean": float(r["mean_count"]),
                "stddev": float(r["stddev_count"]),
            }
            new_cache[key] = baseline

            # Also persist to DB for visibility
            await conn.execute(
                """
                INSERT INTO baselines (source, event_type, day_of_week, hour_of_day,
                                       mean_count, stddev_count, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (source, event_type, day_of_week, hour_of_day) DO UPDATE
                SET mean_count = EXCLUDED.mean_count,
                    stddev_count = EXCLUDED.stddev_count,
                    updated_at = NOW()
                """,
                r["source"], r["event_type"], r["dow"], r["hod"],
                float(r["mean_count"]), float(r["stddev_count"]),
            )

    _baselines_cache = new_cache
    log.info("baselines_updated", count=len(new_cache))


async def load_baselines() -> None:
    """Load baselines from DB into memory cache. Called on startup."""
    global _baselines_cache
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM baselines")

    new_cache = {}
    for r in rows:
        key = (r["source"], r["event_type"], r["day_of_week"], r["hour_of_day"])
        new_cache[key] = {"mean": float(r["mean_count"]), "stddev": float(r["stddev_count"])}

    _baselines_cache = new_cache
    log.info("baselines_loaded", count=len(new_cache))


async def track_event(event_source: str, event_type: str, classification_category: str) -> None:
    """Track an event for correlation analysis. Lightweight -- just log for now."""
    # Correlation tracking will be enhanced in a future iteration
    pass


async def check_correlations(event_source: str, event_type: str) -> list[dict]:
    """Check if recent events form a cross-system pattern.

    Returns a list of correlations found, each with:
    - sources: set of involved systems
    - count: number of related events
    - summary: human-readable description
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get events from last 2 hours, grouped by source
        rows = await conn.fetch(
            """
            SELECT source, event_type, COUNT(*) as count
            FROM events
            WHERE created_at >= NOW() - INTERVAL '2 hours'
              AND status != 'dead_letter'
            GROUP BY source, event_type
            HAVING COUNT(*) >= 2
            ORDER BY count DESC
            """
        )

    if len(rows) < 2:
        return []

    # Find source-spanning patterns: multiple sources with elevated counts
    sources_with_activity = {r["source"] for r in rows}
    if len(sources_with_activity) < 2:
        return []

    total_events = sum(r["count"] for r in rows)
    if total_events < 5:
        return []

    return [{
        "sources": list(sources_with_activity),
        "total_events": total_events,
        "breakdown": [
            {"source": r["source"], "event_type": r["event_type"], "count": r["count"]}
            for r in rows
        ],
        "summary": (
            f"Cross-system activity: {total_events} events across "
            f"{', '.join(sources_with_activity)} in last 2 hours"
        ),
    }]


async def update_threshold(config: dict) -> None:
    """Update a single baseline entry from an approved threshold_adjustment proposal."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO baselines (source, event_type, day_of_week, hour_of_day,
                                   mean_count, stddev_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (source, event_type, day_of_week, hour_of_day) DO UPDATE
            SET mean_count = EXCLUDED.mean_count,
                stddev_count = EXCLUDED.stddev_count,
                updated_at = NOW()
            """,
            config["source"],
            config["event_type"],
            config["day_of_week"],
            config["hour_of_day"],
            config["mean_count"],
            config["stddev_count"],
        )

    # Update in-memory cache too
    key = (config["source"], config["event_type"], config["day_of_week"], config["hour_of_day"])
    _baselines_cache[key] = {"mean": config["mean_count"], "stddev": config["stddev_count"]}
    log.info("threshold_updated", key=str(key))


async def generate_morning_brief() -> str:
    """Generate an enhanced morning intelligence brief."""
    pool = await get_pool()
    now = datetime.now(UTC)

    async with pool.acquire() as conn:
        events_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )
        failed_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE status = 'failed' AND created_at >= NOW() - INTERVAL '24 hours'"
        )
        pending_drafts = await conn.fetchval(
            "SELECT COUNT(*) FROM email_drafts WHERE status = 'pending'"
        )
        dlq_count = await conn.fetchval(
            "SELECT COUNT(*) FROM dead_letter_events WHERE resolved_at IS NULL"
        )

        # Pending proposals
        pending_proposals = await conn.fetchval(
            "SELECT COUNT(*) FROM proposals WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > NOW())"
        )
        proposal_types = await conn.fetch(
            """
            SELECT type, COUNT(*) as count FROM proposals
            WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > NOW())
            GROUP BY type ORDER BY count DESC
            """
        )

        # Approval rate trend (last 7 days)
        approval_stats = await conn.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE status = 'approved' OR status = 'sent') AS approved,
                   COUNT(*) FILTER (WHERE edited_body IS NOT NULL) AS edited,
                   COUNT(*) AS total
            FROM email_drafts
            WHERE created_at >= NOW() - INTERVAL '7 days'
              AND status != 'pending'
            """
        )

        # Top event sources
        top_sources = await conn.fetch(
            """
            SELECT source, COUNT(*) AS count FROM events
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY source ORDER BY count DESC LIMIT 5
            """
        )

    # Build brief
    sources_str = ", ".join(f"{r['source']}: {r['count']}" for r in top_sources) if top_sources else "none"
    proposals_str = ", ".join(f"{r['type']}: {r['count']}" for r in proposal_types) if proposal_types else "none"

    approval_rate = 0
    edit_rate = 0
    if approval_stats and approval_stats["total"]:
        approval_rate = round(approval_stats["approved"] / approval_stats["total"] * 100)
        if approval_stats["approved"]:
            edit_rate = round(approval_stats["edited"] / approval_stats["approved"] * 100)

    brief = (
        f"**Morning Intelligence Brief** -- {now.strftime('%Y-%m-%d')}\n\n"
        f"**Overnight Summary**\n"
        f"- {events_24h} events processed, {failed_24h} failed\n"
        f"- {pending_drafts} drafts pending approval\n"
        f"- {dlq_count} DLQ entries unresolved\n"
        f"- Top sources: {sources_str}\n\n"
    )

    if pending_proposals > 0:
        brief += (
            f"**Pending Proposals ({pending_proposals})**\n"
            f"- Types: {proposals_str}\n"
            f"- Review in Dashboard to approve/reject\n\n"
        )

    if approval_stats and approval_stats["total"] > 0:
        brief += (
            f"**Agent Performance (7-day)**\n"
            f"- Draft approval rate: {approval_rate}%\n"
            f"- Edit rate (of approved): {edit_rate}%\n"
        )

    if dlq_count > 0:
        brief += f"\n:warning: {dlq_count} events in dead-letter queue need attention."

    return brief
