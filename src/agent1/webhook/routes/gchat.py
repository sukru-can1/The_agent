"""Google Chat webhook endpoint with interactive approval flow."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.common.settings import get_settings
from agent1.queue.publisher import publish_event
from agent1.webhook.guards import verify_google_chat_token

log = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/gchat", dependencies=[Depends(verify_google_chat_token)])
async def gchat_webhook(request: Request):
    """Handle incoming Google Chat events (messages, button clicks, etc.)."""
    body = await request.json()
    event_type = body.get("type", "MESSAGE")

    log.info("gchat_webhook_received", event_type=event_type)

    if event_type == "ADDED_TO_SPACE":
        settings = get_settings()
        return {"text": f"Hello! I'm {settings.agent_name}, your GLAMIRA Ops Agent. I monitor emails, tickets, feedback, and tasks 24/7."}

    if event_type == "MESSAGE":
        return await _handle_message(body)

    if event_type == "CARD_CLICKED":
        return await _handle_card_action(body)

    return {"text": "OK"}


async def _handle_message(body: dict) -> dict:
    """Handle a Chat message — enqueue for processing."""
    message = body.get("message", {})
    # Google Chat uses 'argumentText' (without @mention) for bot messages,
    # 'text' includes the @mention. Fall back through both fields.
    text = (
        message.get("argumentText", "").strip()
        or message.get("text", "").strip()
        or message.get("formattedText", "").strip()
    )
    sender = body.get("user", {}).get("displayName", "")
    sender_email = body.get("user", {}).get("email", "")

    log.info("gchat_message_text", text=text[:200] if text else "(empty)",
             has_argument_text=bool(message.get("argumentText")),
             has_text=bool(message.get("text")),
             sender=sender)

    # Check if this is a teachable rule
    teach_indicators = ["from now on", "remember that", "always ", "never ", "stop doing"]
    is_teach = any(indicator in text.lower() for indicator in teach_indicators)

    event = Event(
        source=EventSource.GCHAT,
        event_type="teachable_rule" if is_teach else "chat_message",
        priority=Priority.HIGH if is_teach else Priority.MEDIUM,
        payload={
            "space": body.get("space", {}).get("name", ""),
            "thread": message.get("thread", {}).get("name", ""),
            "sender": sender,
            "sender_email": sender_email,
            "text": text,
        },
        idempotency_key=f"gchat:{message.get('name', '')}",
    )
    await publish_event(event)
    return {"text": "Processing..."}


async def _handle_card_action(body: dict) -> dict:
    """Handle a Chat Card button click — approve/reject drafts, ack alerts."""
    action = body.get("action", {}) or body.get("common", {}).get("invokedFunction", "")
    function_name = action.get("function", "") if isinstance(action, dict) else action
    parameters = {}

    # Parse parameters from action
    if isinstance(action, dict):
        for p in action.get("parameters", []):
            parameters[p.get("key", "")] = p.get("value", "")

    user = body.get("user", {}).get("displayName", "Unknown")
    log.info("card_action", function=function_name, params=parameters, user=user)

    if function_name == "approve_draft":
        return await _approve_draft(parameters, user)

    if function_name == "reject_draft":
        return await _reject_draft(parameters, user)

    if function_name == "edit_draft":
        return await _edit_draft_redirect(parameters)

    if function_name == "ack_alert":
        return {"text": f"Alert acknowledged by {user}."}

    # Unknown action — publish as event for worker to handle
    event = Event(
        source=EventSource.GCHAT,
        event_type="card_action",
        priority=Priority.HIGH,
        payload={
            "function": function_name,
            "parameters": parameters,
            "space": body.get("space", {}).get("name", ""),
            "user": user,
        },
    )
    await publish_event(event)
    return {"text": "Action received."}


async def _approve_draft(params: dict, user: str) -> dict:
    """Approve a draft directly from Chat card button."""
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"text": "Error: No draft_id provided."}

    try:
        draft_id_int = int(draft_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            draft = await conn.fetchrow(
                "SELECT id, subject, status FROM email_drafts WHERE id = $1",
                draft_id_int,
            )
            if not draft:
                return {"text": f"Draft #{draft_id} not found."}
            if draft["status"] != "pending":
                return {"text": f"Draft #{draft_id} is already {draft['status']}."}

            await conn.execute(
                "UPDATE email_drafts SET status = 'approved', approved_at = NOW() WHERE id = $1",
                draft_id_int,
            )

        log.info("draft_approved_via_chat", draft_id=draft_id_int, user=user)
        return {"text": f"Draft #{draft_id} approved by {user}. Sending email..."}
    except Exception as exc:
        log.warning("draft_approve_error", error=str(exc))
        return {"text": f"Error approving draft: {exc}"}


async def _reject_draft(params: dict, user: str) -> dict:
    """Reject a draft from Chat card button."""
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"text": "Error: No draft_id provided."}

    try:
        draft_id_int = int(draft_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE email_drafts SET status = 'rejected' WHERE id = $1 AND status = 'pending'",
                draft_id_int,
            )

        log.info("draft_rejected_via_chat", draft_id=draft_id_int, user=user)
        return {"text": f"Draft #{draft_id} rejected by {user}."}
    except Exception as exc:
        log.warning("draft_reject_error", error=str(exc))
        return {"text": f"Error rejecting draft: {exc}"}


async def _edit_draft_redirect(params: dict) -> dict:
    """Redirect user to the dashboard to edit a draft."""
    draft_id = params.get("draft_id", "")
    return {"text": f"Open the dashboard to edit draft #{draft_id}: https://dashboard-alpha-lovat-14.vercel.app"}
