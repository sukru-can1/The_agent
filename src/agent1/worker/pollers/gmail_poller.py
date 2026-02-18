"""Gmail poller — checks for new unread emails."""

from __future__ import annotations

import asyncio

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.google_auth.auth import get_gmail_service
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


def _header_value(headers: list[dict], name: str) -> str:
    """Extract a header value by name from Gmail API headers list."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


async def poll_gmail() -> None:
    """Check Gmail for new unread emails and publish events.

    Fetches unread messages via the Gmail API, deduplicates them,
    and publishes an event for each new email.
    """
    log.debug("gmail_poll_started")

    service = get_gmail_service()
    if service is None:
        log.warning("gmail_poll_skipped", reason="Gmail service not configured")
        return

    try:
        # Fetch unread messages (synchronous API — run in thread)
        response = await asyncio.to_thread(
            service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=20)
            .execute,
        )

        messages = response.get("messages", [])
        if not messages:
            log.debug("gmail_poll_completed", new_emails=0)
            return

        published_count = 0

        for msg_stub in messages:
            msg_id = msg_stub["id"]
            thread_id = msg_stub.get("threadId", "")

            try:
                # Check dedup — skip if we already processed this message
                if await is_duplicate("gmail", msg_id):
                    continue

                # Fetch message metadata
                msg = await asyncio.to_thread(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject"],
                    )
                    .execute,
                )

                headers = msg.get("payload", {}).get("headers", [])
                sender = _header_value(headers, "From")
                subject = _header_value(headers, "Subject")
                snippet = msg.get("snippet", "")

                # Create and publish event
                event = Event(
                    source=EventSource.GMAIL,
                    event_type="new_email",
                    priority=Priority.MEDIUM,
                    payload={
                        "message_id": msg_id,
                        "thread_id": thread_id,
                        "sender": sender,
                        "subject": subject,
                        "snippet": snippet,
                    },
                    idempotency_key=f"gmail:{msg_id}",
                )

                await publish_event(event)
                await mark_processed("gmail", msg_id)
                published_count += 1

                log.info(
                    "gmail_new_email_event",
                    message_id=msg_id,
                    sender=sender,
                    subject=subject,
                )

            except Exception as exc:
                log.error(
                    "gmail_poll_message_error",
                    message_id=msg_id,
                    error=str(exc),
                )
                # Continue processing other messages
                continue

        log.debug("gmail_poll_completed", new_emails=published_count)

    except Exception as exc:
        log.error("gmail_poll_error", error=str(exc))
