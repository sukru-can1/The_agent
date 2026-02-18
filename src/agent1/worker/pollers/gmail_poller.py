"""Gmail poller — checks for new unread emails."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def poll_gmail() -> None:
    """Check Gmail for new unread emails and publish events.

    Full implementation in Phase 1 — will use Gmail API via tools/gmail.py.
    """
    log.debug("gmail_poll_started")

    # TODO: Phase 1 — use Gmail API to fetch unread emails
    # For each new email:
    #   1. Check dedup (gmail:{message_id})
    #   2. If new, publish event with email metadata
    #   3. Mark as processed

    log.debug("gmail_poll_completed")
