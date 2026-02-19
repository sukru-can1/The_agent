"""StarInfinity project management tools."""

from __future__ import annotations

from typing import Any

import httpx

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "StarInfinity not configured — set starinfinity_base_url and starinfinity_api_key"}


async def _get_client() -> httpx.AsyncClient | None:
    """Create an httpx client for the StarInfinity API.

    Returns None if StarInfinity is not configured.
    """
    settings = get_settings()
    if not settings.starinfinity_base_url or not settings.starinfinity_api_key:
        return None
    return httpx.AsyncClient(
        base_url=settings.starinfinity_base_url,
        headers={"Authorization": f"Bearer {settings.starinfinity_api_key}"},
        timeout=30.0,
    )


class StarInfinityListBoardsTool(BaseTool):
    name = "starinfinity_list_boards"
    description = "List all boards in the StarInfinity workspace."
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = await _get_client()
        if client is None:
            return _NOT_CONFIGURED

        try:
            async with client:
                resp = await client.get("/boards")
                resp.raise_for_status()
                data = resp.json()

            boards = data if isinstance(data, list) else data.get("data", [])
            log.info("starinfinity_list_boards", count=len(boards))
            return {"boards": [{"id": b.get("id"), "name": b.get("name")} for b in boards]}

        except httpx.HTTPStatusError as exc:
            log.warning("starinfinity_list_boards_error", status_code=exc.response.status_code, detail=exc.response.text[:500])
            return {"error": f"StarInfinity API error: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            log.warning("starinfinity_list_boards_network_error", error=str(exc))
            return {"error": f"StarInfinity network error: {exc}"}


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
        client = await _get_client()
        if client is None:
            return _NOT_CONFIGURED

        board_id = kwargs["board_id"]
        params: dict[str, Any] = {}
        if kwargs.get("limit"):
            params["limit"] = kwargs["limit"]
        if kwargs.get("after"):
            params["after"] = kwargs["after"]

        try:
            async with client:
                resp = await client.get(f"/boards/{board_id}/items", params=params)
                resp.raise_for_status()
                data = resp.json()

            items = data if isinstance(data, list) else data.get("data", [])
            log.info("starinfinity_get_tasks", board_id=board_id, count=len(items))
            return {"items": items}

        except httpx.HTTPStatusError as exc:
            log.warning("starinfinity_get_tasks_api_error", status_code=exc.response.status_code, detail=exc.response.text[:500])
            return {"error": f"StarInfinity API error: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            log.warning("starinfinity_get_tasks_network_error", error=str(exc))
            return {"error": f"StarInfinity network error: {exc}"}


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
        client = await _get_client()
        if client is None:
            return _NOT_CONFIGURED

        board_id = kwargs["board_id"]
        body: dict[str, Any] = {}
        if kwargs.get("folder_id"):
            body["folder_id"] = kwargs["folder_id"]
        if kwargs.get("values"):
            body["values"] = kwargs["values"]

        try:
            async with client:
                resp = await client.post(f"/boards/{board_id}/items", json=body)
                resp.raise_for_status()
                data = resp.json()

            item_id = data.get("id", "")
            log.info("starinfinity_create_task", item_id=item_id, board_id=board_id)
            return {"item_id": item_id, "status": "created", "data": data}

        except httpx.HTTPStatusError as exc:
            log.warning("starinfinity_create_task_api_error", status_code=exc.response.status_code, detail=exc.response.text[:500])
            return {"error": f"StarInfinity API error: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            log.warning("starinfinity_create_task_network_error", error=str(exc))
            return {"error": f"StarInfinity network error: {exc}"}


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
        client = await _get_client()
        if client is None:
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
                resp = await client.put(f"/boards/{board_id}/items/{item_id}", json=body)
                resp.raise_for_status()

            log.info("starinfinity_update_task", item_id=item_id, board_id=board_id)
            return {"status": "updated"}

        except httpx.HTTPStatusError as exc:
            log.warning("starinfinity_update_task_api_error", item_id=item_id, status_code=exc.response.status_code, detail=exc.response.text[:500])
            return {"error": f"StarInfinity API error: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            log.warning("starinfinity_update_task_network_error", item_id=item_id, error=str(exc))
            return {"error": f"StarInfinity network error: {exc}"}
