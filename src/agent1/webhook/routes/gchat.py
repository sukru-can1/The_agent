"""Google Chat webhook endpoint with interactive approval flow."""

from __future__ import annotations

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

        # Determine event type: check chat.type, then top-level type.
        # ADDED_TO_SPACE / REMOVED_FROM_SPACE have no messagePayload.
        event_type = (
            chat.get("type")
            or body.get("type")
            or ("MESSAGE" if payload else "ADDED_TO_SPACE")
        )

        normalized = {
            "type": event_type,
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
    log.info("gchat_raw_body", keys=list(raw_body.keys()),
             chat_keys=list(raw_body["chat"].keys()) if "chat" in raw_body else None)

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

    if not text:
        return _chat_response("Hi! Send me a message and I'll help.", is_addon)

    # Check if this is a teachable rule
    teach_indicators = ["from now on", "remember that", "always ", "never ", "stop doing"]
    is_teach = any(indicator in text.lower() for indicator in teach_indicators) if text else False

    event = Event(
        source=EventSource.GCHAT,
        event_type="teachable_rule" if is_teach else "chat_message",
        priority=Priority.HIGH,
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


def _extract_form_inputs(body: dict) -> dict:
    """Extract form input values from a CARD_CLICKED event."""
    form_inputs = (
        body.get("commonEventObject", {}).get("formInputs", {})
        or body.get("common", {}).get("formInputs", {})
    )
    result: dict = {}
    for name, data in form_inputs.items():
        if "stringInputs" in data:
            values = data["stringInputs"]["value"]
            result[name] = values[0] if len(values) == 1 else values
        elif "dateInput" in data:
            result[name] = data["dateInput"]["msSinceEpoch"]
    return result


async def _handle_card_action(body: dict, is_addon: bool) -> dict:
    """Handle a Chat Card button click — approve/reject drafts, ack alerts."""
    # Support both legacy and Workspace Add-on event formats
    action = body.get("action", {}) or body.get("common", {}).get("invokedFunction", "")
    function_name = action.get("function", "") if isinstance(action, dict) else action

    # Workspace Add-on format: function name in commonEventObject
    if not function_name:
        ceo = body.get("commonEventObject", {})
        function_name = ceo.get("invokedFunction", "")

    parameters = {}

    # Parse parameters from action dict
    if isinstance(action, dict):
        for p in action.get("parameters", []):
            parameters[p.get("key", "")] = p.get("value", "")

    # Also parse from commonEventObject.parameters
    if not parameters:
        ceo = body.get("commonEventObject", {})
        ceo_params = ceo.get("parameters", {})
        if isinstance(ceo_params, dict):
            parameters = ceo_params

    user = body.get("user", {}).get("displayName", "Unknown")
    log.info("card_action", function=function_name, params=parameters, user=user)

    if function_name == "approve_draft":
        return await _approve_draft(parameters, user, is_addon)

    if function_name == "reject_draft":
        return await _reject_draft(parameters, user, is_addon)

    if function_name == "edit_draft":
        return _edit_draft_redirect(parameters, is_addon)

    if function_name == "revise_draft":
        return await _revise_draft_from_chat(body, parameters, user, is_addon)

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


async def _revise_draft_from_chat(
    body: dict, params: dict, user: str, is_addon: bool
) -> dict:
    """Revise a draft using AI based on the text input from the Chat card."""
    draft_id = params.get("draft_id")
    if not draft_id:
        return _chat_response("Error: No draft_id provided.", is_addon)

    form_inputs = _extract_form_inputs(body)
    instruction = form_inputs.get("revision_instruction", "").strip()
    if not instruction:
        return _chat_response("Please type a revision instruction first.", is_addon)

    try:
        from agent1.drafts.refiner import revise_draft

        draft_id_int = int(draft_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            draft = await conn.fetchrow(
                """SELECT id, original_body, draft_body, edited_body, subject,
                          from_address, status FROM email_drafts WHERE id = $1""",
                draft_id_int,
            )
        if not draft:
            return _chat_response(f"Draft #{draft_id} not found.", is_addon)
        if draft["status"] not in ("pending", "approved"):
            return _chat_response(f"Draft #{draft_id} is {draft['status']}.", is_addon)

        current_body = draft["edited_body"] or draft["draft_body"]
        result = await revise_draft(
            original_body=draft["original_body"],
            current_body=current_body,
            subject=draft["subject"] or "",
            from_address=draft["from_address"] or "",
            instruction=instruction,
        )

        # Store revised body
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE email_drafts SET edited_body = $2 WHERE id = $1",
                draft_id_int,
                result["revised_body"],
            )

        # Return updated card with new draft body
        from agent1.tools.chat_cards import build_draft_approval_card
        card = build_draft_approval_card(
            draft_id=draft_id_int,
            subject=draft["subject"] or "",
            from_address=draft["from_address"] or "",
            to_address="",
            draft_body=result["revised_body"],
            classification=draft["classification"] or "needs_response",
        )

        log.info("draft_revised_via_chat", draft_id=draft_id_int, user=user)

        # Update the original message with the revised card
        if is_addon:
            return {
                "hostAppDataAction": {
                    "chatDataAction": {
                        "updateMessageAction": {
                            "message": {
                                "text": f"Draft #{draft_id} revised by {user}: \"{instruction}\"",
                                "cardsV2": [card],
                            }
                        }
                    }
                }
            }
        return {
            "actionResponse": {"type": "UPDATE_MESSAGE"},
            "text": f"Draft #{draft_id} revised by {user}: \"{instruction}\"",
            "cardsV2": [card],
        }

    except Exception as exc:
        log.warning("draft_revise_chat_error", error=str(exc))
        return _chat_response(f"Error revising draft: {exc}", is_addon)


async def _approve_draft(params: dict, user: str, is_addon: bool) -> dict:
    """Approve and send a draft directly from Chat card button."""
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
            if draft["status"] not in ("pending", "approved"):
                return _chat_response(f"Draft #{draft_id} is already {draft['status']}.", is_addon)

            # Approve first
            await conn.execute(
                "UPDATE email_drafts SET status = 'approved', approved_at = NOW() WHERE id = $1",
                draft_id_int,
            )

        # Send the email
        try:
            from agent1.tools.gmail import GmailSendApprovedTool
            send_tool = GmailSendApprovedTool()
            result = await send_tool.execute(draft_id=draft_id_int)
            if "error" in result:
                log.warning("draft_send_after_approve_failed", error=result["error"])
                return _chat_response(
                    f"Draft #{draft_id} approved by {user}, but send failed: {result['error']}",
                    is_addon,
                )
        except Exception as send_exc:
            log.warning("draft_send_after_approve_error", error=str(send_exc))
            return _chat_response(
                f"Draft #{draft_id} approved by {user}, but send failed: {send_exc}",
                is_addon,
            )

        log.info("draft_approved_and_sent_via_chat", draft_id=draft_id_int, user=user)
        return _chat_response(
            f"Draft #{draft_id} approved by {user} and email sent successfully.", is_addon
        )
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
