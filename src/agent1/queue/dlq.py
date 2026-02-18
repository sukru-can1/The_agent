"""Dead-letter queue for failed events."""

from __future__ import annotations

import json

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import Event, EventStatus

log = get_logger(__name__)


async def move_to_dlq(event: Event) -> None:
    """Move a failed event to the dead-letter queue in Postgres."""
    pool = await get_pool()

    error_entry = {
        "retry": event.retry_count,
        "error": event.error or "unknown",
    }

    async with pool.acquire() as conn:
        # Update event status
        await conn.execute(
            "UPDATE events SET status = $1, error = $2 WHERE id = $3",
            EventStatus.DEAD_LETTER.value,
            event.error,
            event.id,
        )

        # Insert into DLQ
        await conn.execute(
            """
            INSERT INTO dead_letter_events
                (original_event_id, source, event_type, priority, payload, error_history, retry_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            event.id,
            event.source.value,
            event.event_type,
            event.priority.value,
            json.dumps(event.payload),
            json.dumps([error_entry]),
            event.retry_count,
        )

    log.error(
        "event_moved_to_dlq",
        event_id=str(event.id),
        source=event.source.value,
        event_type=event.event_type,
        error=event.error,
    )


async def get_dlq_entries(limit: int = 20) -> list[dict]:
    """Fetch unresolved DLQ entries."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, original_event_id, source, event_type, priority,
                   payload, error_history, retry_count, created_at
            FROM dead_letter_events
            WHERE resolved_at IS NULL
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]


async def resolve_dlq_entry(dlq_id: str, resolved_by: str = "admin") -> bool:
    """Mark a DLQ entry as resolved."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE dead_letter_events
            SET resolved_at = NOW(), resolved_by = $1
            WHERE id = $2 AND resolved_at IS NULL
            """,
            resolved_by,
            dlq_id,
        )
        return result == "UPDATE 1"


async def retry_dlq_entry(dlq_id: str) -> bool:
    """Retry a DLQ entry by re-publishing it."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM dead_letter_events WHERE id = $1 AND resolved_at IS NULL",
            dlq_id,
        )
        if row is None:
            return False

        from agent1.common.models import Event, EventSource, Priority
        from agent1.queue.publisher import publish_event

        event = Event(
            source=EventSource(row["source"]),
            event_type=row["event_type"],
            priority=Priority(row["priority"]),
            payload=json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"],
            retry_count=0,
        )
        await publish_event(event)
        await resolve_dlq_entry(dlq_id, resolved_by="retry")
        return True
