"""Pattern detection — finds ticket spikes, CSAT trends, and systemic issues."""

from __future__ import annotations

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def detect_patterns() -> None:
    """Run all pattern detection checks. Called periodically by the scheduler."""
    await _detect_ticket_spikes()
    await _detect_csat_trends()
    await _detect_error_spikes()


async def _detect_ticket_spikes() -> None:
    """Detect 3+ events from the same source with same event_type in the last hour."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source, event_type, COUNT(*) AS count
            FROM events
            WHERE created_at >= NOW() - INTERVAL '1 hour'
              AND status != 'dead_letter'
            GROUP BY source, event_type
            HAVING COUNT(*) >= 2
            """
        )

    for row in rows:
        # Check if we already alerted about this pattern recently
        pattern_key = f"pattern:spike:{row['source']}:{row['event_type']}"
        from agent1.common.redis_client import get_redis

        redis = await get_redis()
        already_alerted = await redis.exists(pattern_key)
        if already_alerted:
            continue

        # Check against adaptive baseline
        try:
            from agent1.intelligence.analytics_engine import get_baseline, is_anomaly
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            baseline = get_baseline(row["source"], row["event_type"], now.weekday(), now.hour)
            if not is_anomaly(row["source"], row["event_type"], row["count"], baseline):
                continue
        except Exception:
            pass  # Fall through to legacy threshold (HAVING COUNT >= 3)

        # Set a 2-hour cooldown to avoid repeat alerts
        await redis.set(pattern_key, "1", ex=7200)

        event = Event(
            source=EventSource.SCHEDULER,
            event_type="pattern_detected",
            priority=Priority.CRITICAL,
            payload={
                "pattern_type": "event_spike",
                "source": row["source"],
                "event_type": row["event_type"],
                "count": row["count"],
                "window": "1 hour",
                "message": (
                    f"Spike detected: {row['count']} '{row['event_type']}' events "
                    f"from {row['source']} in the last hour"
                ),
            },
            idempotency_key=f"pattern:spike:{row['source']}:{row['event_type']}:{__import__('datetime').datetime.now().strftime('%Y%m%d%H')}",
        )
        await publish_event(event)
        log.info(
            "pattern_spike_detected",
            source=row["source"],
            event_type=row["event_type"],
            count=row["count"],
        )


async def _detect_csat_trends() -> None:
    """Check feedbacks DB for negative CSAT trend (if available)."""
    try:
        from agent1.common.settings import get_settings

        settings = get_settings()
        if not settings.feedbacks_database_url:
            return

        import asyncpg

        conn = await asyncpg.connect(settings.feedbacks_database_url)
        try:
            # Check for negative sentiment spike in last 24 hours vs previous 24 hours
            current = await conn.fetchval(
                """
                SELECT COUNT(*) FROM "SurveyResponse"
                WHERE sentiment = 'negative'
                  AND "createdAt" >= NOW() - INTERVAL '24 hours'
                """
            )
            previous = await conn.fetchval(
                """
                SELECT COUNT(*) FROM "SurveyResponse"
                WHERE sentiment = 'negative'
                  AND "createdAt" >= NOW() - INTERVAL '48 hours'
                  AND "createdAt" < NOW() - INTERVAL '24 hours'
                """
            )

            if current and previous and current > previous * 1.5 and current >= 3:
                # Significant increase in negative feedback
                from agent1.common.redis_client import get_redis

                redis = await get_redis()
                pattern_key = "pattern:csat_trend"
                if not await redis.exists(pattern_key):
                    await redis.set(pattern_key, "1", ex=86400)

                    event = Event(
                        source=EventSource.FEEDBACKS,
                        event_type="pattern_detected",
                        priority=Priority.HIGH,
                        payload={
                            "pattern_type": "csat_negative_trend",
                            "current_24h": current,
                            "previous_24h": previous,
                            "increase_pct": round((current - previous) / max(previous, 1) * 100, 1),
                            "message": (
                                f"Negative CSAT trend: {current} negative responses in last 24h "
                                f"vs {previous} in previous 24h ({round((current - previous) / max(previous, 1) * 100)}% increase)"
                            ),
                        },
                    )
                    await publish_event(event)
                    log.info(
                        "csat_trend_detected",
                        current=current,
                        previous=previous,
                    )
        finally:
            await conn.close()
    except Exception:
        log.exception("csat_trend_detection_failed")


async def _detect_error_spikes() -> None:
    """Detect if error rate is unusually high."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE created_at >= NOW() - INTERVAL '1 hour'"
        )
        failed = await conn.fetchval(
            """
            SELECT COUNT(*) FROM events
            WHERE created_at >= NOW() - INTERVAL '1 hour'
              AND status = 'failed'
            """
        )

    if total and total >= 5 and failed / total > 0.3:
        from agent1.common.redis_client import get_redis

        redis = await get_redis()
        pattern_key = "pattern:error_spike"
        if not await redis.exists(pattern_key):
            await redis.set(pattern_key, "1", ex=3600)

            event = Event(
                source=EventSource.SCHEDULER,
                event_type="pattern_detected",
                priority=Priority.CRITICAL,
                payload={
                    "pattern_type": "error_spike",
                    "total_events": total,
                    "failed_events": failed,
                    "error_rate": round(failed / total * 100, 1),
                    "message": (
                        f"High error rate: {failed}/{total} events failed "
                        f"in the last hour ({round(failed / total * 100)}%)"
                    ),
                },
            )
            await publish_event(event)
            log.info("error_spike_detected", total=total, failed=failed)
