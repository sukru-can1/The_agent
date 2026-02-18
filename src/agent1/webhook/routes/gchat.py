"""Google Chat webhook endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.common.settings import get_settings
from agent1.queue.publisher import publish_event

log = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/gchat")
async def gchat_webhook(request: Request):
    """Handle incoming Google Chat events (messages, button clicks, etc.)."""
    body = await request.json()
    event_type = body.get("type", "MESSAGE")

    log.info("gchat_webhook_received", event_type=event_type)

    if event_type == "ADDED_TO_SPACE":
        settings = get_settings()
        return {"text": f"Hello! I'm {settings.agent_name}, your GLAMIRA Ops Agent."}

    if event_type == "MESSAGE":
        message = body.get("message", {})
        event = Event(
            source=EventSource.GCHAT,
            event_type="chat_message",
            priority=Priority.MEDIUM,
            payload={
                "space": body.get("space", {}).get("name", ""),
                "thread": message.get("thread", {}).get("name", ""),
                "sender": body.get("user", {}).get("displayName", ""),
                "sender_email": body.get("user", {}).get("email", ""),
                "text": message.get("text", ""),
            },
            idempotency_key=f"gchat:{message.get('name', '')}",
        )
        await publish_event(event)
        return {"text": "Processing..."}

    if event_type == "CARD_CLICKED":
        action = body.get("action", {})
        event = Event(
            source=EventSource.GCHAT,
            event_type="card_action",
            priority=Priority.HIGH,
            payload={
                "action_method": action.get("actionMethodName", ""),
                "parameters": action.get("parameters", []),
                "space": body.get("space", {}).get("name", ""),
                "user": body.get("user", {}).get("displayName", ""),
            },
        )
        await publish_event(event)
        return {"text": "Action received."}

    return {"text": "OK"}
