"""Gmail tools — read, draft, send, label emails."""

from __future__ import annotations

import asyncio
import base64
import json
from email.mime.text import MIMEText
from typing import Any

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.google_auth.auth import get_gmail_service
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "Gmail not configured — set Google OAuth credentials"}


def _header_value(headers: list[dict], name: str) -> str:
    """Extract a header value by name from Gmail API headers list."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(payload: dict) -> str:
    """Recursively extract text body from a Gmail message payload.

    Prefers text/plain; falls back to text/html.
    """
    # Single-part message
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    # Multipart — recurse through parts
    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")

        if part_mime == "text/plain" and part_data:
            plain_text += base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
        elif part_mime == "text/html" and part_data:
            html_text += base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
        elif part_mime.startswith("multipart/"):
            # Nested multipart — recurse
            nested = _decode_body(part)
            if nested:
                plain_text += nested

    return plain_text if plain_text else html_text


def _extract_attachments(payload: dict) -> list[dict]:
    """Extract attachment metadata (filename, size) from a message payload."""
    attachments: list[dict] = []
    parts = payload.get("parts", [])

    for part in parts:
        filename = part.get("filename", "")
        if filename:
            attachments.append({
                "filename": filename,
                "size": part.get("body", {}).get("size", 0),
            })
        # Recurse into nested multipart
        if part.get("mimeType", "").startswith("multipart/"):
            attachments.extend(_extract_attachments(part))

    return attachments


class GmailGetNewEmailsTool(BaseTool):
    name = "gmail_get_new_emails"
    description = "Fetch new unread emails from Gmail inbox. Returns sender, subject, body, timestamp, thread_id, message_id."
    input_schema = {
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "default": 20},
            "label": {"type": "string", "default": "INBOX"},
            "query": {"type": "string", "description": "Gmail search query (optional)"},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_gmail_service()
        if service is None:
            return _NOT_CONFIGURED

        max_results = kwargs.get("max_results", 20)
        label = kwargs.get("label", "INBOX")
        query = kwargs.get("query", "is:unread")

        try:
            # List messages matching query
            response = await asyncio.to_thread(
                service.users()
                .messages()
                .list(userId="me", q=query, labelIds=[label], maxResults=max_results)
                .execute,
            )

            messages = response.get("messages", [])
            if not messages:
                return {"emails": [], "count": 0}

            emails: list[dict] = []
            for msg_stub in messages:
                msg_id = msg_stub["id"]
                # Fetch metadata for each message
                msg = await asyncio.to_thread(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date", "Message-Id"],
                    )
                    .execute,
                )
                headers = msg.get("payload", {}).get("headers", [])
                emails.append({
                    "message_id": msg["id"],
                    "thread_id": msg.get("threadId", ""),
                    "from": _header_value(headers, "From"),
                    "subject": _header_value(headers, "Subject"),
                    "date": _header_value(headers, "Date"),
                    "snippet": msg.get("snippet", ""),
                })

            log.info("gmail_get_new_emails", count=len(emails))
            return {"emails": emails, "count": len(emails)}

        except Exception as exc:
            log.error("gmail_get_new_emails_error", error=str(exc))
            return {"error": f"Failed to fetch emails: {exc}"}


class GmailGetEmailTool(BaseTool):
    name = "gmail_get_email"
    description = "Get full details of a specific email by message ID, including full body and attachments list."
    input_schema = {
        "type": "object",
        "properties": {
            "message_id": {"type": "string"},
        },
        "required": ["message_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_gmail_service()
        if service is None:
            return _NOT_CONFIGURED

        message_id = kwargs["message_id"]

        try:
            msg = await asyncio.to_thread(
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute,
            )

            payload = msg.get("payload", {})
            headers = payload.get("headers", [])

            body = _decode_body(payload)
            attachments = _extract_attachments(payload)

            result = {
                "message_id": msg["id"],
                "thread_id": msg.get("threadId", ""),
                "from": _header_value(headers, "From"),
                "to": _header_value(headers, "To"),
                "subject": _header_value(headers, "Subject"),
                "date": _header_value(headers, "Date"),
                "body": body,
                "labels": msg.get("labelIds", []),
                "attachments": attachments,
            }

            log.info("gmail_get_email", message_id=message_id)
            return result

        except Exception as exc:
            log.error("gmail_get_email_error", message_id=message_id, error=str(exc))
            return {"error": f"Failed to get email {message_id}: {exc}"}


class GmailDraftReplyTool(BaseTool):
    name = "gmail_draft_reply"
    description = "Create a draft reply to an email. Does NOT send it — stores it for approval. Posts the draft to Google Chat for Sukru to approve/edit/reject."
    input_schema = {
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "ID of email to reply to"},
            "draft_body": {"type": "string", "description": "The drafted reply text"},
            "classification": {"type": "string", "enum": ["urgent", "needs_response", "fyi"]},
            "context_notes": {"type": "string", "description": "Why you drafted this response"},
        },
        "required": ["message_id", "draft_body", "classification"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_gmail_service()
        if service is None:
            return _NOT_CONFIGURED

        message_id = kwargs["message_id"]
        draft_body = kwargs["draft_body"]
        classification = kwargs["classification"]
        context_notes = kwargs.get("context_notes", "")

        try:
            # Fetch the original email (full format to capture body for revision context)
            msg = await asyncio.to_thread(
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute,
            )

            payload = msg.get("payload", {})
            headers = payload.get("headers", [])
            from_address = _header_value(headers, "From")
            to_address = _header_value(headers, "To")
            subject = _header_value(headers, "Subject")
            thread_id = msg.get("threadId", "")
            original_body = _decode_body(payload)

            # Store draft in database (NOT in Gmail — pending approval)
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO email_drafts
                        (gmail_message_id, gmail_thread_id, from_address, to_address,
                         subject, original_body, draft_body, classification, context_used, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')
                    RETURNING id
                    """,
                    message_id,
                    thread_id,
                    from_address,
                    to_address,
                    subject,
                    original_body or None,
                    draft_body,
                    classification,
                    json.dumps({"context_notes": context_notes}),
                )
                draft_id = row["id"]

            log.info(
                "gmail_draft_created",
                draft_id=draft_id,
                message_id=message_id,
                classification=classification,
            )

            # Post approval card to Google Chat
            try:
                from agent1.tools.chat_cards import build_draft_approval_card
                from agent1.tools.google_chat import GChatPostMessageTool

                card = build_draft_approval_card(
                    draft_id=draft_id,
                    subject=subject,
                    from_address=from_address,
                    to_address=to_address,
                    draft_body=draft_body,
                    classification=classification,
                )
                chat_tool = GChatPostMessageTool()
                await chat_tool.execute(
                    space="alerts",
                    message=f"New email draft #{draft_id} needs approval",
                    thread_key=f"draft-{draft_id}",
                    cards=card,
                )
            except Exception as chat_exc:
                log.warning("draft_chat_notification_failed", error=str(chat_exc))

            return {
                "draft_id": draft_id,
                "status": "pending_approval",
                "message": "Draft stored for approval and posted to Chat",
            }

        except Exception as exc:
            log.error("gmail_draft_reply_error", message_id=message_id, error=str(exc))
            return {"error": f"Failed to create draft: {exc}"}


class GmailSendApprovedTool(BaseTool):
    name = "gmail_send_approved"
    description = "Send a previously approved email draft. Only call this after explicit approval from Sukru."
    input_schema = {
        "type": "object",
        "properties": {
            "draft_id": {"type": "integer", "description": "ID from email_drafts table"},
        },
        "required": ["draft_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_gmail_service()
        if service is None:
            return _NOT_CONFIGURED

        draft_id = kwargs["draft_id"]

        try:
            # Fetch the approved draft from database
            pool = await get_pool()
            async with pool.acquire() as conn:
                draft = await conn.fetchrow(
                    """
                    SELECT id, gmail_message_id, gmail_thread_id, from_address,
                           to_address, subject, draft_body, edited_body, status
                    FROM email_drafts
                    WHERE id = $1
                    """,
                    draft_id,
                )

            if draft is None:
                return {"error": f"Draft {draft_id} not found"}

            if draft["status"] != "approved":
                return {
                    "error": f"Draft {draft_id} is not approved (current status: {draft['status']})"
                }

            # Use edited_body if available, otherwise draft_body
            body_text = draft["edited_body"] or draft["draft_body"]

            # Build MIME message
            message = MIMEText(body_text, "plain", "utf-8")
            message["to"] = draft["from_address"]  # Reply to sender
            message["from"] = draft["to_address"]  # Send from our address
            subject = draft["subject"]
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
            message["subject"] = subject
            message["In-Reply-To"] = draft["gmail_message_id"]
            message["References"] = draft["gmail_message_id"]

            # Encode to base64url
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

            # Send via Gmail API
            send_body: dict[str, Any] = {"raw": raw}
            if draft["gmail_thread_id"]:
                send_body["threadId"] = draft["gmail_thread_id"]

            sent = await asyncio.to_thread(
                service.users()
                .messages()
                .send(userId="me", body=send_body)
                .execute,
            )

            sent_msg_id = sent.get("id", "")

            # Update draft status to sent
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE email_drafts
                    SET status = 'sent', sent_at = NOW()
                    WHERE id = $1
                    """,
                    draft_id,
                )

            log.info(
                "gmail_send_approved",
                draft_id=draft_id,
                sent_message_id=sent_msg_id,
            )

            return {"status": "sent", "message_id": sent_msg_id}

        except Exception as exc:
            log.error("gmail_send_approved_error", draft_id=draft_id, error=str(exc))
            return {"error": f"Failed to send draft {draft_id}: {exc}"}


class GmailLabelEmailTool(BaseTool):
    name = "gmail_label_email"
    description = "Apply a label to an email or archive it."
    input_schema = {
        "type": "object",
        "properties": {
            "message_id": {"type": "string"},
            "add_labels": {"type": "array", "items": {"type": "string"}},
            "remove_labels": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["message_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_gmail_service()
        if service is None:
            return _NOT_CONFIGURED

        message_id = kwargs["message_id"]
        add_labels = kwargs.get("add_labels", [])
        remove_labels = kwargs.get("remove_labels", [])

        if not add_labels and not remove_labels:
            return {"error": "Must specify at least one of add_labels or remove_labels"}

        try:
            modify_body: dict[str, list[str]] = {}
            if add_labels:
                modify_body["addLabelIds"] = add_labels
            if remove_labels:
                modify_body["removeLabelIds"] = remove_labels

            await asyncio.to_thread(
                service.users()
                .messages()
                .modify(userId="me", id=message_id, body=modify_body)
                .execute,
            )

            log.info(
                "gmail_label_email",
                message_id=message_id,
                add=add_labels,
                remove=remove_labels,
            )

            return {"status": "updated"}

        except Exception as exc:
            log.error("gmail_label_email_error", message_id=message_id, error=str(exc))
            return {"error": f"Failed to modify labels for {message_id}: {exc}"}
