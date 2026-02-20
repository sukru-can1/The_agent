"""Freshdesk tools — tickets, notes, updates."""

from __future__ import annotations

from typing import Any

from agent1.common.logging import get_logger
from agent1.integrations import FreshdeskClient, IntegrationError
from agent1.integrations.freshdesk import PRIORITY_MAP, STATUS_MAP
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "Freshdesk integration not yet configured"}


def _error(exc: IntegrationError) -> dict[str, str]:
    """Convert an IntegrationError to a tool-friendly error dict."""
    return {"error": f"Freshdesk API error {exc.status_code}" if exc.status_code else str(exc)}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class FreshdeskGetTicketsTool(BaseTool):
    name = "freshdesk_get_tickets"
    description = "Fetch tickets from Freshdesk with optional filters."
    input_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["new", "open", "pending", "resolved", "closed"]},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
            "updated_since": {"type": "string", "description": "ISO datetime"},
            "per_page": {"type": "integer", "default": 30},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = FreshdeskClient()
        if not client.available:
            return {"tickets": [], "message": "Freshdesk integration not yet configured"}

        per_page = kwargs.get("per_page", 30)
        params: dict[str, Any] = {
            "per_page": per_page,
            "order_by": "updated_at",
            "order_type": "desc",
        }

        status = kwargs.get("status")
        if status and status in STATUS_MAP:
            params["status"] = STATUS_MAP[status]

        priority = kwargs.get("priority")
        if priority and priority in PRIORITY_MAP:
            params["priority"] = PRIORITY_MAP[priority]

        updated_since = kwargs.get("updated_since")
        if updated_since:
            params["updated_since"] = updated_since

        try:
            async with client:
                raw_tickets = await client.get_tickets(**params)

            tickets = [
                {
                    "id": t["id"],
                    "subject": t.get("subject"),
                    "description_text": t.get("description_text"),
                    "status": t.get("status"),
                    "priority": t.get("priority"),
                    "requester_id": t.get("requester_id"),
                    "created_at": t.get("created_at"),
                    "updated_at": t.get("updated_at"),
                    "tags": t.get("tags", []),
                }
                for t in raw_tickets
            ]
            return {"tickets": tickets}

        except IntegrationError as exc:
            log.warning("freshdesk_get_tickets_error", detail=str(exc))
            return {**_error(exc), "tickets": []}


class FreshdeskGetTicketTool(BaseTool):
    name = "freshdesk_get_ticket"
    description = "Get full details of a specific ticket including conversations."
    input_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "integer"},
        },
        "required": ["ticket_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = FreshdeskClient()
        if not client.available:
            return _NOT_CONFIGURED

        ticket_id = kwargs["ticket_id"]

        try:
            async with client:
                raw = await client.get_ticket(ticket_id)

            ticket = {
                "id": raw["id"],
                "subject": raw.get("subject"),
                "description_text": raw.get("description_text"),
                "status": raw.get("status"),
                "priority": raw.get("priority"),
                "tags": raw.get("tags", []),
                "conversations": raw.get("conversations", []),
            }
            return {"ticket": ticket}

        except IntegrationError as exc:
            log.warning("freshdesk_get_ticket_error", ticket_id=ticket_id, detail=str(exc))
            return _error(exc)


class FreshdeskAddNoteTool(BaseTool):
    name = "freshdesk_add_note"
    description = "Add an internal note to a ticket. Use for agent observations and context."
    input_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "integer"},
            "body": {"type": "string"},
            "private": {"type": "boolean", "default": True},
        },
        "required": ["ticket_id", "body"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = FreshdeskClient()
        if not client.available:
            return _NOT_CONFIGURED

        ticket_id = kwargs["ticket_id"]
        body = kwargs["body"]
        private = kwargs.get("private", True)

        try:
            async with client:
                raw = await client.add_note(ticket_id, body, private=private)

            return {"note_id": raw.get("id"), "status": "created"}

        except IntegrationError as exc:
            log.warning("freshdesk_add_note_error", ticket_id=ticket_id, detail=str(exc))
            return _error(exc)


class FreshdeskUpdateTicketTool(BaseTool):
    name = "freshdesk_update_ticket"
    description = "Update ticket properties like priority, status, or assignee."
    input_schema = {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "integer"},
            "priority": {"type": "integer", "description": "1=low, 2=medium, 3=high, 4=urgent"},
            "status": {"type": "integer", "description": "2=open, 3=pending, 4=resolved, 5=closed"},
            "responder_id": {"type": "integer", "description": "Agent ID to assign to"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["ticket_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = FreshdeskClient()
        if not client.available:
            return _NOT_CONFIGURED

        ticket_id = kwargs["ticket_id"]

        # Build update body from non-None fields (excluding ticket_id)
        update_fields = {}
        for field in ("priority", "status", "responder_id", "tags"):
            value = kwargs.get(field)
            if value is not None:
                update_fields[field] = value

        if not update_fields:
            return {"error": "No update fields provided"}

        try:
            async with client:
                await client.update_ticket(ticket_id, **update_fields)

            return {"status": "updated"}

        except IntegrationError as exc:
            log.warning("freshdesk_update_ticket_error", ticket_id=ticket_id, detail=str(exc))
            return _error(exc)
