"""Google Chat poller — reads DMs sent to Sukru using OAuth credentials.

Strategy:
- Maintains a small "active" set of DM spaces where messages were recently seen.
- Polls active spaces every scheduler tick (~5 min) with low concurrency.
- Slowly rotates through all DM spaces in the background to discover new activity.
- Only processes messages arriving AFTER monitoring starts (no historical backfill).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.common.settings import get_settings
from agent1.google_auth.auth import get_chat_user_service
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)

# ----- State -----
_dm_spaces_cache: list[str] = []
_dm_spaces_cache_ts: float = 0
_DM_CACHE_TTL = 3600  # rediscover all DM spaces every hour

_active_spaces: set[str] = set()  # spaces with recent messages → poll every tick
_scan_offset: int = 0  # rotating pointer into _dm_spaces_cache for background scan
_SCAN_BATCH = 20  # how many cold spaces to probe per tick

_monitoring_start: datetime | None = None

_POLL_CONCURRENCY = 1  # sequential — httplib2 is NOT thread-safe


async def _discover_dm_spaces(service) -> list[str]:
    """List all DM spaces. Cached for 1 hour."""
    global _dm_spaces_cache, _dm_spaces_cache_ts

    now = time.monotonic()
    if _dm_spaces_cache and (now - _dm_spaces_cache_ts) < _DM_CACHE_TTL:
        return _dm_spaces_cache

    dm_spaces: list[str] = []
    page_token = None

    while True:
        kwargs: dict = {"pageSize": 200}
        if page_token:
            kwargs["pageToken"] = page_token

        response = await asyncio.to_thread(
            lambda kw=kwargs: service.spaces().list(**kw).execute(),
        )

        for space in response.get("spaces", []):
            name = space.get("name", "")
            if name and space.get("spaceType") == "DIRECT_MESSAGE":
                dm_spaces.append(name)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    _dm_spaces_cache = dm_spaces
    _dm_spaces_cache_ts = now
    log.info("gchat_dm_spaces_discovered", count=len(dm_spaces))
    return dm_spaces


async def _poll_space(service, space_name: str, since_rfc3339: str, settings) -> int:
    """Poll one space. Returns number of new events published."""
    published = 0
    try:
        response = await asyncio.to_thread(
            lambda sn=space_name: (
                service.spaces()
                .messages()
                .list(parent=sn, pageSize=20, filter=f'createTime > "{since_rfc3339}"')
                .execute()
            ),
        )

        for msg in response.get("messages", []):
            msg_name = msg.get("name", "")
            msg_id = msg_name.split("/")[-1] if msg_name else ""
            if not msg_id:
                continue
            if await is_duplicate("gchat_user", msg_id):
                continue

            sender = msg.get("sender", {})
            if sender.get("type") == "BOT":
                await mark_processed("gchat_user", msg_id)
                continue

            email_prefix = settings.gchat_user_email.split("@")[0].lower()
            if sender.get("displayName", "").lower().startswith(email_prefix):
                await mark_processed("gchat_user", msg_id)
                continue

            text = msg.get("text", "").strip()
            if not text:
                await mark_processed("gchat_user", msg_id)
                continue

            event = Event(
                source=EventSource.GCHAT,
                event_type="chat_user_message",
                priority=Priority.MEDIUM,
                payload={
                    "space_id": space_name,
                    "message_id": msg_name,
                    "sender_name": sender.get("displayName", ""),
                    "sender_resource": sender.get("name", ""),
                    "text": text,
                    "thread_id": msg.get("thread", {}).get("name", ""),
                    "create_time": msg.get("createTime", ""),
                },
                idempotency_key=f"gchat_user:{msg_id}",
            )

            await publish_event(event)
            await mark_processed("gchat_user", msg_id)
            published += 1

            # Promote this space to active set
            _active_spaces.add(space_name)

            log.info(
                "gchat_user_new_message",
                space=space_name,
                message_id=msg_id,
                sender=sender.get("displayName", ""),
            )

    except Exception as exc:
        log.warning("gchat_poll_space_error", space=space_name, error=str(exc))

    return published


async def _poll_batch(service, spaces: list[str], since_rfc3339: str, settings) -> int:
    """Poll a list of spaces with bounded concurrency."""
    sem = asyncio.Semaphore(_POLL_CONCURRENCY)
    total = 0

    async def _limited(sp: str) -> int:
        async with sem:
            return await _poll_space(service, sp, since_rfc3339, settings)

    results = await asyncio.gather(
        *[_limited(sp) for sp in spaces], return_exceptions=True,
    )
    for r in results:
        if isinstance(r, int):
            total += r
    return total


async def poll_gchat() -> None:
    """Poll Google Chat DMs for new messages.

    1. Always polls "active" spaces (where messages were previously seen).
    2. Rotates through remaining spaces in small batches to discover new activity.
    3. Only captures messages arriving AFTER monitoring starts.
    """
    global _monitoring_start, _scan_offset

    settings = get_settings()

    if not settings.gchat_poll_all_dms and not settings.gchat_poll_spaces:
        log.debug("gchat_poll_skipped", reason="no spaces configured")
        return

    service = get_chat_user_service()
    if service is None:
        log.warning("gchat_poll_skipped", reason="Chat user service not configured")
        return

    # Discover DM spaces (cached)
    all_dm = (
        await _discover_dm_spaces(service)
        if settings.gchat_poll_all_dms
        else [
            s if s.startswith("spaces/") else f"spaces/{s}"
            for s in settings.gchat_poll_spaces
        ]
    )

    # On first run, set monitoring start to NOW
    if _monitoring_start is None:
        _monitoring_start = datetime.now(UTC)
        log.info(
            "gchat_monitoring_started",
            total_dm_spaces=len(all_dm),
            since=_monitoring_start.isoformat(),
        )

    # Time window: 10min back or from monitoring start
    ten_min_ago = datetime.now(UTC) - timedelta(minutes=10)
    since = max(ten_min_ago, _monitoring_start)
    since_rfc3339 = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    total_published = 0

    # 1. Poll active spaces (always, every tick)
    active_list = [s for s in _active_spaces if s in set(all_dm)]
    if active_list:
        count = await _poll_batch(service, active_list, since_rfc3339, settings)
        total_published += count

    # 2. Rotate through cold spaces (small batch per tick)
    cold = [s for s in all_dm if s not in _active_spaces]
    if cold:
        start = _scan_offset % len(cold)
        batch = cold[start : start + _SCAN_BATCH]
        if len(batch) < _SCAN_BATCH and start > 0:
            batch += cold[: _SCAN_BATCH - len(batch)]
        _scan_offset = (start + _SCAN_BATCH) % max(len(cold), 1)

        count = await _poll_batch(service, batch, since_rfc3339, settings)
        total_published += count

    if total_published > 0:
        log.info(
            "gchat_poll_completed",
            new_messages=total_published,
            active=len(active_list),
            scanned=min(_SCAN_BATCH, len(cold)) if cold else 0,
        )
    else:
        log.debug(
            "gchat_poll_completed",
            new_messages=0,
            active=len(active_list),
            scanned=min(_SCAN_BATCH, len(cold)) if cold else 0,
        )
