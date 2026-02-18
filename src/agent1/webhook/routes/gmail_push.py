"""Gmail push notification endpoint (via Google Cloud Pub/Sub)."""

from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Request

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.queue.publisher import publish_event

log = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/gmail")
async def gmail_push(request: Request):
    """Handle Gmail push notifications via Pub/Sub.

    Google sends a Pub/Sub message with base64-encoded data containing
    the email address and history ID.
    """
    body = await request.json()

    message = body.get("message", {})
    data = message.get("data", "")

    if data:
        decoded = json.loads(base64.b64decode(data))
        email_address = decoded.get("emailAddress", "")
        history_id = decoded.get("historyId", "")

        log.info(
            "gmail_push_received",
            email=email_address,
            history_id=history_id,
        )

        event = Event(
            source=EventSource.GMAIL,
            event_type="gmail_notification",
            priority=Priority.HIGH,
            payload={
                "email_address": email_address,
                "history_id": history_id,
            },
            idempotency_key=f"gmail:history:{history_id}",
        )
        await publish_event(event)

    return {"status": "ok"}
