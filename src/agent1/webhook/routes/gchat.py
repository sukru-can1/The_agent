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

# Module-level flag set per request to track event format
_is_addon_format = False


def _normalize_body(body: dict) -> tuple[dict, bool]:
    """Normalize Google Chat event payload.

    Google Chat sends two formats:
    - Legacy: {type, message, user, space, ...} at top level
    - Workspace Add-on: {commonEventObject, chat: {user, eventTime, messagePayload: {message, space}}}

    Returns (normalized_body, is_addon_format).
    """
    if "chat" in body and isinstance(body["chat"], dict):
        chat = body["chat"]
        # Workspace Add-on format — unwrap messagePayload
        payload = chat.get("messagePayload", {})
        normalized = {
            "type": chat.get("type", "MESSAGE"),
            "eventTime": chat.get("eventTime"),
            "message": payload.get("message", {}),
            "space": payload.get("space", chat.get("space", {})),
            "user": chat.get("user", {}),
        }
        return normalized, True
    # Legacy format — data is at top level
    return body, False


def _chat_response(text: str, is_addon: bool) -> dict:
    """Wrap a text response in the correct format for Google Chat.

    Add-on format requires hostAppDataAction wrapper.
    Legacy format just uses {"text": "..."}.
    """
    if is_addon:
        return {
            "hostAppDataAction": {
                "chatDataAction": {
                    "createMessageAction": {
                        "message": {"text": text}
                    }
                }
            }
        }
    return {"text": text}


@router.post("/gchat", dependencies=[Depends(verify_google_chat_token)])
async def gchat_webhook(request: Request):
    """Handle incoming Google Chat events (messages, button clicks, etc.)."""
    raw_body = await request.json()

    # Normalize to handle both legacy and Workspace Add-on event formats
    body, is_addon = _normalize_body(raw_body)
    event_type = body.get("type", "MESSAGE")

    log.info("gchat_webhook_received", event_type=event_type,
             format="addon" if is_addon else "legacy",
             body_keys=list(body.keys()))

    if event_type == "ADDED_TO_SPACE":
        settings = get_settings()
        return _chat_response(
            f"Hello! I'm {settings.agent_name}, your GLAMIRA Ops Agent. "
            "I monitor emails, tickets, feedback, and tasks 24/7.",
            is_addon,
        )

    if event_type == "MESSAGE":
        return await _handle_message(body, is_addon)

    if event_type == "CARD_CLICKED":
        return await _handle_card_action(body, is_addon)

    return _chat_response("OK", is_addon)


async def _handle_message(body: dict, is_addon: bool) -> dict:
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
             sender=sender, sender_email=sender_email)

    # Check if this is a teachable rule
    teach_indicators = ["from now on", "remember that", "always ", "never ", "stop doing"]
    is_teach = any(indicator in text.lower() for indicator in teach_indicators) if text else False

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
    return _chat_response("Processing...", is_addon)


async def _handle_card_action(body: dict, is_addon: bool) -> dict:
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
        return await _approve_draft(parameters, user, is_addon)

    if function_name == "reject_draft":
        return await _reject_draft(parameters, user, is_addon)

    if function_name == "edit_draft":
        return _edit_draft_redirect(parameters, is_addon)

    if function_name == "ack_alert":
        return _chat_response(f"Alert acknowledged by {user}.", is_addon)

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
    return _chat_response("Action received.", is_addon)


async def _approve_draft(params: dict, user: str, is_addon: bool) -> dict:
    """Approve a draft directly from Chat card button."""
    draft_id = params.get("draft_id")
    if not draft_id:
        return _chat_response("Error: No draft_id provided.", is_addon)

    try:
        draft_id_int = int(draft_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            draft = await conn.fetchrow(
                "SELECT id, subject, status FROM email_drafts WHERE id = $1",
                draft_id_int,
            )
            if not draft:
                return _chat_response(f"Draft #{draft_id} not found.", is_addon)
            if draft["status"] != "pending":
                return _chat_response(f"Draft #{draft_id} is already {draft['status']}.", is_addon)

            await conn.execute(
                "UPDATE email_drafts SET status = 'approved', approved_at = NOW() WHERE id = $1",
                draft_id_int,
            )

        log.info("draft_approved_via_chat", draft_id=draft_id_int, user=user)
        return _chat_response(f"Draft #{draft_id} approved by {user}. Sending email...", is_addon)
    except Exception as exc:
        log.warning("draft_approve_error", error=str(exc))
        return _chat_response(f"Error approving draft: {exc}", is_addon)


async def _reject_draft(params: dict, user: str, is_addon: bool) -> dict:
    """Reject a draft from Chat card button."""
    draft_id = params.get("draft_id")
    if not draft_id:
        return _chat_response("Error: No draft_id provided.", is_addon)

    try:
        draft_id_int = int(draft_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE email_drafts SET status = 'rejected' WHERE id = $1 AND status = 'pending'",
                draft_id_int,
            )

        log.info("draft_rejected_via_chat", draft_id=draft_id_int, user=user)
        return _chat_response(f"Draft #{draft_id} rejected by {user}.", is_addon)
    except Exception as exc:
        log.warning("draft_reject_error", error=str(exc))
        return _chat_response(f"Error rejecting draft: {exc}", is_addon)


def _edit_draft_redirect(params: dict, is_addon: bool) -> dict:
    """Redirect user to the dashboard to edit a draft."""
    draft_id = params.get("draft_id", "")
    return _chat_response(
        f"Open the dashboard to edit draft #{draft_id}: https://dashboard-alpha-lovat-14.vercel.app",
        is_addon,
    )
