"""Event models and priority scoring for the queue."""

from __future__ import annotations

import time

from agent1.common.models import Event, Priority


# Redis key constants
QUEUE_KEY = "agent1:queue:events"
EVENT_HASH_PREFIX = "agent1:event:"
DEDUP_PREFIX = "agent1:dedup:"
LOCK_PREFIX = "agent1:lock:"
RATELIMIT_PREFIX = "agent1:ratelimit:"


def compute_score(priority: Priority, timestamp_ms: int | None = None) -> float:
    """Compute Redis sorted set score: priority * 1e12 + timestamp_ms.

    Lower score = higher priority + earlier timestamp = processed first.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    return float(priority.value) * 1e12 + timestamp_ms


def event_hash_key(event_id: str) -> str:
    """Redis hash key for an event payload."""
    return f"{EVENT_HASH_PREFIX}{event_id}"


def dedup_key(source: str, identifier: str) -> str:
    """Redis key for dedup checking."""
    return f"{DEDUP_PREFIX}{source}:{identifier}"


def lock_key(resource: str) -> str:
    """Redis key for distributed lock."""
    return f"{LOCK_PREFIX}{resource}"
