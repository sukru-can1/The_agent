"""Freshdesk poller — checks for new/updated tickets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.integrations import FreshdeskClient, IntegrationError
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Freshdesk priority -> internal Priority mapping
# ---------------------------------------------------------------------------

_FRESHDESK_PRIORITY_MAP: dict[int, Priority] = {
    4: Priority.CRITICAL,  # urgent
    3: Priority.HIGH,      # high
    2: Priority.MEDIUM,    # medium
    1: Priority.LOW,       # low
}


async def poll_freshdesk() -> None:
    """Check Freshdesk for new or updated tickets and publish events."""
    log.debug("freshdesk_poll_started")

    client = FreshdeskClient()
    if not client.available:
        log.debug("freshdesk_poll_skipped", reason="api_key_not_configured")
        return

    # Fetch tickets updated in the last 10 minutes
    since = datetime.now(UTC) - timedelta(minutes=10)
    updated_since = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        async with client:
            tickets = await client.get_tickets(
                updated_since=updated_since,
                order_by="updated_at",
                order_type="desc",
            )
    except IntegrationError as exc:
        log.warning("freshdesk_poll_error", detail=str(exc))
        return

    published = 0

    for ticket in tickets:
        ticket_id = ticket["id"]
        updated_at = ticket.get("updated_at", "")
        dedup_identifier = f"{ticket_id}:{updated_at}"

        # Skip already-processed ticket updates
        if await is_duplicate("freshdesk", dedup_identifier):
            continue

        # Map Freshdesk priority to internal Priority
        fd_priority = ticket.get("priority", 1)
        priority = _FRESHDESK_PRIORITY_MAP.get(fd_priority, Priority.MEDIUM)

        idempotency_key = f"freshdesk:{ticket_id}:{updated_at}"

        event = Event(
            source=EventSource.FRESHDESK,
            event_type="ticket_updated",
            priority=priority,
            payload={
                "ticket_id": ticket_id,
                "subject": ticket.get("subject"),
                "status": ticket.get("status"),
                "priority": fd_priority,
                "requester_email": ticket.get("requester", {}).get("email")
                if isinstance(ticket.get("requester"), dict)
                else None,
                "tags": ticket.get("tags", []),
            },
            idempotency_key=idempotency_key,
        )

        await publish_event(event)
        await mark_processed("freshdesk", dedup_identifier)
        published += 1

        log.info(
            "freshdesk_ticket_event_published",
            ticket_id=ticket_id,
            priority=priority.name,
            subject=ticket.get("subject", "")[:80],
        )

    log.debug("freshdesk_poll_completed", tickets_found=len(tickets), events_published=published)
