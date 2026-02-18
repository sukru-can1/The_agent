"""Gmail tools — read, draft, send, label emails."""

from __future__ import annotations

from typing import Any

from agent1.tools.base import BaseTool


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
        # TODO: Phase 1 — implement with Google Gmail API
        return {"emails": [], "message": "Gmail integration not yet configured"}


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
        # TODO: Phase 1
        return {"error": "Gmail integration not yet configured"}


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
        # TODO: Phase 1 — create draft in DB, post to Chat
        return {"draft_id": None, "message": "Gmail integration not yet configured"}


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
        # TODO: Phase 1
        return {"error": "Gmail integration not yet configured"}


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
        # TODO: Phase 1
        return {"error": "Gmail integration not yet configured"}
