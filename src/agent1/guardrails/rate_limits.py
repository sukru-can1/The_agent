"""Redis-based rate limiting for tools and actions."""

from __future__ import annotations

from agent1.common.models import Event
from agent1.common.redis_client import get_redis
from agent1.common.settings import get_settings
from agent1.queue.events import RATELIMIT_PREFIX


async def check_rate_limits(event: Event) -> dict:
    """Check if processing this event would exceed rate limits.

    Limits per source per hour to prevent runaway processing.
    """
    redis = await get_redis()

    # Per-source event processing limits (events per hour)
    source_limits = {
        "gmail": 100,
        "freshdesk": 200,
        "gchat": 300,
        "feedbacks": 100,
        "starinfinity": 50,
        "scheduler": 20,
    }

    source = event.source.value
    max_events = source_limits.get(source, 200)
    key = f"{RATELIMIT_PREFIX}source:{source}:3600"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3600)

    if count > max_events:
        return {
            "allowed": False,
            "limit": f"Source {source} exceeded {max_events} events/hour (current: {count})",
        }

    # Global events per hour limit
    global_key = f"{RATELIMIT_PREFIX}global:3600"
    global_count = await redis.incr(global_key)
    if global_count == 1:
        await redis.expire(global_key, 3600)

    if global_count > 500:
        return {
            "allowed": False,
            "limit": f"Global rate limit exceeded: {global_count}/500 events per hour",
        }

    return {"allowed": True, "limit": None}


async def check_tool_rate_limit(tool_name: str) -> bool:
    """Check if a specific tool call is within rate limits.

    Returns True if allowed, False if rate limited.
    """
    redis = await get_redis()
    settings = get_settings()

    # Per-tool rate limit windows
    limits = {
        "gmail_send_approved": (settings.rate_limit_emails_per_hour, 3600),
        "gmail_draft_reply": (30, 3600),  # max 30 drafts per hour
        "gchat_post_message": (settings.rate_limit_chat_messages_per_minute, 60),
        "gchat_reply_as_agent": (settings.rate_limit_chat_messages_per_minute, 60),
        "freshdesk_update_ticket": (60, 3600),  # max 60 ticket updates per hour
        "freshdesk_add_note": (60, 3600),
    }

    if tool_name not in limits:
        return True

    max_count, window_seconds = limits[tool_name]
    key = f"{RATELIMIT_PREFIX}{tool_name}:{window_seconds}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)

    return count <= max_count
