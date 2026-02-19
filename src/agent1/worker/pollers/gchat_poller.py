"""Google Chat poller — reads messages from Sukru's spaces using OAuth credentials."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.common.settings import get_settings
from agent1.google_auth.auth import get_chat_user_service
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def poll_gchat() -> None:
    """Check Google Chat spaces for new messages directed at Sukru.

    Uses OAuth credentials (user mode) to read messages from configured spaces.
    Skips messages sent by Sukru himself — only processes messages from others.
    """
    settings = get_settings()

    if not settings.gchat_poll_spaces:
        log.debug("gchat_poll_skipped", reason="no spaces configured")
        return

    service = get_chat_user_service()
    if service is None:
        log.warning("gchat_poll_skipped", reason="Chat user service not configured")
        return

    log.debug("gchat_poll_started", spaces=len(settings.gchat_poll_spaces))

    # Look back 10 minutes for recent messages
    since = datetime.now(timezone.utc) - timedelta(minutes=10)
    since_rfc3339 = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    published_count = 0

    for space_id in settings.gchat_poll_spaces:
        space_name = space_id if space_id.startswith("spaces/") else f"spaces/{space_id}"

        try:
            # List recent messages in this space
            response = await asyncio.to_thread(
                lambda sn=space_name: (
                    service.spaces()
                    .messages()
                    .list(
                        parent=sn,
                        pageSize=20,
                        filter=f'createTime > "{since_rfc3339}"',
                    )
                    .execute()
                ),
            )

            messages = response.get("messages", [])
            if not messages:
                continue

            for msg in messages:
                msg_name = msg.get("name", "")
                # Extract a stable message ID from the full name
                msg_id = msg_name.split("/")[-1] if msg_name else ""

                if not msg_id:
                    continue

                # Skip if already processed
                if await is_duplicate("gchat_user", msg_id):
                    continue

                # Skip messages sent by Sukru
                sender = msg.get("sender", {})
                sender_type = sender.get("type", "")
                sender_email = sender.get("name", "")  # user resource name

                # The sender display name or email check
                # In Chat API v1, sender has 'name' (resource name like users/123)
                # and 'displayName'. We check if it's our own user.
                sender_display = sender.get("displayName", "")

                # Check if this is a bot message (skip bot messages too)
                if sender_type == "BOT":
                    await mark_processed("gchat_user", msg_id)
                    continue

                # We can't easily check email from the sender object, so we rely on
                # the message text and the sender resource name. If the message was
                # sent by the authorized user, the Chat API typically marks it.
                # We'll use a heuristic: if sender.name matches, skip it.
                # For now, skip messages where sender display name matches our email prefix.
                email_prefix = settings.gchat_user_email.split("@")[0].lower()
                if sender_display.lower().startswith(email_prefix):
                    await mark_processed("gchat_user", msg_id)
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    await mark_processed("gchat_user", msg_id)
                    continue

                thread = msg.get("thread", {})
                thread_name = thread.get("name", "")

                event = Event(
                    source=EventSource.GCHAT,
                    event_type="chat_user_message",
                    priority=Priority.MEDIUM,
                    payload={
                        "space_id": space_name,
                        "message_id": msg_name,
                        "sender_name": sender_display,
                        "sender_resource": sender.get("name", ""),
                        "text": text,
                        "thread_id": thread_name,
                        "create_time": msg.get("createTime", ""),
                    },
                    idempotency_key=f"gchat_user:{msg_id}",
                )

                await publish_event(event)
                await mark_processed("gchat_user", msg_id)
                published_count += 1

                log.info(
                    "gchat_user_new_message",
                    space=space_name,
                    message_id=msg_id,
                    sender=sender_display,
                )

        except Exception as exc:
            log.error(
                "gchat_poll_space_error",
                space=space_name,
                error=str(exc),
            )
            continue

    log.debug("gchat_poll_completed", new_messages=published_count)
