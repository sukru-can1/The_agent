"""Redis-based rate limiting for tools and actions."""

from __future__ import annotations

from agent1.common.models import Event
from agent1.common.redis_client import get_redis
from agent1.common.settings import get_settings
from agent1.queue.events import RATELIMIT_PREFIX


async def check_rate_limits(event: Event) -> dict:
    """Check if processing this event would exceed rate limits.

    Returns {"allowed": True/False, "limit": "description"}.
    """
    # For now, rate limits are checked at the tool execution level,
    # not at the event level. This is a placeholder for event-level limits.
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
        "gchat_post_message": (settings.rate_limit_chat_messages_per_minute, 60),
        "gchat_reply_as_agent": (settings.rate_limit_chat_messages_per_minute, 60),
    }

    if tool_name not in limits:
        return True

    max_count, window_seconds = limits[tool_name]
    key = f"{RATELIMIT_PREFIX}{tool_name}:{window_seconds}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)

    return count <= max_count
