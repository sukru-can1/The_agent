"""Consume events from Redis sorted set by priority."""

from __future__ import annotations

import asyncio
import json

from agent1.common.logging import get_logger
from agent1.common.models import Event
from agent1.common.redis_client import get_redis
from agent1.common.settings import get_settings
from agent1.queue.events import QUEUE_KEY, event_hash_key, lock_key

log = get_logger(__name__)


async def acquire_lock(redis, resource: str, ttl: int = 30) -> bool:
    """Acquire a distributed lock via Redis SET NX."""
    key = lock_key(resource)
    return await redis.set(key, "1", nx=True, ex=ttl)


async def release_lock(redis, resource: str) -> None:
    """Release a distributed lock."""
    key = lock_key(resource)
    await redis.delete(key)


async def consume_one() -> Event | None:
    """Pop the highest-priority event from the queue.

    Returns None if queue is empty.
    """
    redis = await get_redis()

    # ZPOPMIN returns the member with the lowest score (highest priority)
    result = await redis.zpopmin(QUEUE_KEY, count=1)
    if not result:
        return None

    event_id, _score = result[0]

    # Fetch full event payload from hash
    key = event_hash_key(event_id)
    payload_json = await redis.get(key)

    if payload_json is None:
        log.warning("event_payload_missing", event_id=event_id)
        return None

    event = Event.model_validate_json(payload_json)

    # Acquire processing lock
    if not await acquire_lock(redis, f"event:{event_id}"):
        log.warning("event_lock_failed", event_id=event_id)
        return None

    log.info(
        "event_consumed",
        event_id=event_id,
        source=event.source.value,
        event_type=event.event_type,
    )
    return event


async def ack_event(event: Event) -> None:
    """Acknowledge successful processing of an event."""
    redis = await get_redis()

    # Clean up hash and lock
    key = event_hash_key(str(event.id))
    await redis.delete(key)
    await release_lock(redis, f"event:{event.id}")

    log.info("event_acked", event_id=str(event.id))


async def nack_event(event: Event, error: str) -> None:
    """Negative-acknowledge: event processing failed."""
    redis = await get_redis()
    settings = get_settings()

    event.retry_count += 1
    event.error = error

    if event.retry_count >= settings.queue_max_retries:
        # Move to DLQ
        from agent1.queue.dlq import move_to_dlq

        await move_to_dlq(event)
    else:
        # Re-enqueue with same priority
        from agent1.queue.publisher import publish_event

        await publish_event(event)

    await release_lock(redis, f"event:{event.id}")
    log.warning(
        "event_nacked",
        event_id=str(event.id),
        retry_count=event.retry_count,
        error=error,
    )


async def run_consumer(process_fn) -> None:
    """Main consumer loop: dequeue and process events."""
    log.info("consumer_started")

    while True:
        event = await consume_one()
        if event is None:
            await asyncio.sleep(1)
            continue

        try:
            await process_fn(event)
            await ack_event(event)
        except Exception as exc:
            await nack_event(event, str(exc))
