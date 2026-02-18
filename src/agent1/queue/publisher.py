"""Publish events to Redis sorted set + persist in Postgres."""

from __future__ import annotations

import json

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import Event
from agent1.common.redis_client import get_redis
from agent1.queue.events import QUEUE_KEY, compute_score, event_hash_key

log = get_logger(__name__)


async def publish_event(event: Event) -> bool:
    """Enqueue an event to the Redis priority queue and persist in Postgres.

    Returns True if published, False if deduplicated.
    """
    redis = await get_redis()
    pool = await get_pool()

    # Store event payload in Redis hash (TTL 24h)
    key = event_hash_key(str(event.id))
    payload_json = event.model_dump_json()
    await redis.set(key, payload_json, ex=86400)

    # Add to sorted set
    score = compute_score(event.priority)
    await redis.zadd(QUEUE_KEY, {str(event.id): score})

    # Persist to Postgres
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO events (id, source, event_type, priority, payload, idempotency_key, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (idempotency_key) WHERE idempotency_key != '' DO NOTHING
            """,
            event.id,
            event.source.value,
            event.event_type,
            event.priority.value,
            json.dumps(event.payload),
            event.idempotency_key,
            event.status.value,
        )

    log.info(
        "event_published",
        event_id=str(event.id),
        source=event.source.value,
        event_type=event.event_type,
        priority=event.priority.value,
    )
    return True
