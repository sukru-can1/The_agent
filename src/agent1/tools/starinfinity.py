"""StarInfinity project management tools."""

from __future__ import annotations

from typing import Any

from agent1.common.logging import get_logger
from agent1.integrations import IntegrationError, StarInfinityClient
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "StarInfinity not configured — set starinfinity_base_url and starinfinity_api_key"}


def _error(exc: IntegrationError) -> dict[str, str]:
    """Convert an IntegrationError to a tool-friendly error dict."""
    return {"error": f"StarInfinity API error: {exc.status_code}" if exc.status_code else f"StarInfinity network error: {exc.detail}"}


class StarInfinityListBoardsTool(BaseTool):
    name = "starinfinity_list_boards"
    description = "List all boards in the StarInfinity workspace."
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = StarInfinityClient()
        if not client.available:
            return _NOT_CONFIGURED

        try:
            async with client:
                boards = await client.list_boards()

            if not isinstance(boards, list):
                boards = []
            log.info("starinfinity_list_boards", count=len(boards))
            return {"boards": [{"id": b.get("id"), "name": b.get("name")} for b in boards]}

        except IntegrationError as exc:
            return _error(exc)


class StarInfinityGetTasksTool(BaseTool):
    name = "starinfinity_get_tasks"
    description = "Get items (tasks) from a StarInfinity board. Must provide board_id."
    input_schema = {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "Board ID to list items from"},
            "limit": {"type": "integer", "description": "Max items to return (default 50)"},
            "after": {"type": "integer", "description": "Cursor for pagination"},
        },
        "required": ["board_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = StarInfinityClient()
        if not client.available:
            return _NOT_CONFIGURED

        board_id = kwargs["board_id"]
        params: dict[str, Any] = {}
        if kwargs.get("limit"):
            params["limit"] = kwargs["limit"]
        if kwargs.get("after"):
            params["after"] = kwargs["after"]

        try:
            async with client:
                items = await client.get_items(board_id, **params)

            if not isinstance(items, list):
                items = []
            log.info("starinfinity_get_tasks", board_id=board_id, count=len(items))
            return {"items": items}

        except IntegrationError as exc:
            return _error(exc)


class StarInfinityCreateTaskTool(BaseTool):
    name = "starinfinity_create_task"
    description = "Create a new item (task) in a StarInfinity board."
    input_schema = {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "Board to create the item in"},
            "folder_id": {"type": "string", "description": "Folder within the board"},
            "values": {"type": "object", "description": "Attribute values for the item (keys are attribute IDs)"},
        },
        "required": ["board_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = StarInfinityClient()
        if not client.available:
            return _NOT_CONFIGURED

        board_id = kwargs["board_id"]
        body: dict[str, Any] = {}
        if kwargs.get("folder_id"):
            body["folder_id"] = kwargs["folder_id"]
        if kwargs.get("values"):
            body["values"] = kwargs["values"]

        try:
            async with client:
                data = await client.create_item(board_id, **body)

            item_id = data.get("id", "")
            log.info("starinfinity_create_task", item_id=item_id, board_id=board_id)
            return {"item_id": item_id, "status": "created", "data": data}

        except IntegrationError as exc:
            return _error(exc)


class StarInfinityUpdateTaskTool(BaseTool):
    name = "starinfinity_update_task"
    description = "Update an existing item (task) in StarInfinity."
    input_schema = {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "Board the item belongs to"},
            "item_id": {"type": "string", "description": "Item ID to update"},
            "values": {"type": "object", "description": "Attribute values to update"},
            "folder_id": {"type": "string", "description": "Move to a different folder"},
        },
        "required": ["board_id", "item_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = StarInfinityClient()
        if not client.available:
            return _NOT_CONFIGURED

        board_id = kwargs["board_id"]
        item_id = kwargs["item_id"]
        body: dict[str, Any] = {}
        if kwargs.get("values"):
            body["values"] = kwargs["values"]
        if kwargs.get("folder_id"):
            body["folder_id"] = kwargs["folder_id"]

        try:
            async with client:
                await client.update_item(board_id, item_id, **body)

            log.info("starinfinity_update_task", item_id=item_id, board_id=board_id)
            return {"status": "updated"}

        except IntegrationError as exc:
            return _error(exc)
