"""Freshdesk tools — tickets, notes, updates."""

from __future__ import annotations

from typing import Any

from agent1.tools.base import BaseTool


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
        # TODO: Phase 2 — implement with Freshdesk API
        return {"tickets": [], "message": "Freshdesk integration not yet configured"}


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
        # TODO: Phase 2
        return {"error": "Freshdesk integration not yet configured"}


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
        # TODO: Phase 2
        return {"error": "Freshdesk integration not yet configured"}


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
        # TODO: Phase 2
        return {"error": "Freshdesk integration not yet configured"}
