"""Freshdesk webhook endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.queue.publisher import publish_event
from agent1.webhook.guards import verify_freshdesk_webhook

log = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/freshdesk", dependencies=[Depends(verify_freshdesk_webhook)])
async def freshdesk_webhook(request: Request):
    """Handle incoming Freshdesk ticket events."""
    body = await request.json()

    ticket_id = body.get("ticket_id") or body.get("freshdesk_webhook", {}).get("ticket_id")
    action = body.get("triggered_event", "ticket_updated")

    log.info("freshdesk_webhook_received", ticket_id=ticket_id, action=action)

    # Determine priority based on ticket urgency
    ticket_priority = body.get("ticket_priority", 2)
    event_priority = Priority.HIGH if ticket_priority >= 3 else Priority.MEDIUM

    event = Event(
        source=EventSource.FRESHDESK,
        event_type=f"ticket_{action}",
        priority=event_priority,
        payload=body,
        idempotency_key=f"freshdesk:{ticket_id}:{body.get('updated_at', '')}",
    )
    await publish_event(event)

    return {"status": "accepted"}
