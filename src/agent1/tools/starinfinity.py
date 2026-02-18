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


class StarInfinityGetTasksTool(BaseTool):
    name = "starinfinity_get_tasks"
    description = "Get tasks from StarInfinity project management."
    input_schema = {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "status": {"type": "string"},
            "assignee": {"type": "string"},
            "due_before": {"type": "string", "description": "ISO date — find overdue tasks"},
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = await _get_client()
        if client is None:
            return _NOT_CONFIGURED

        # Build query params from provided kwargs, skipping None values
        params: dict[str, str] = {}
        for key in ("project_id", "status", "assignee", "due_before"):
            value = kwargs.get(key)
            if value is not None:
                params[key] = value

        try:
            async with client:
                resp = await client.get("/api/tasks", params=params)
                resp.raise_for_status()
                data = resp.json()

            tasks = data if isinstance(data, list) else data.get("tasks", data.get("data", []))

            log.info("starinfinity_get_tasks", params=params, count=len(tasks))
            return {"tasks": tasks}

        except httpx.HTTPStatusError as exc:
            log.warning(
                "starinfinity_get_tasks_api_error",
                status_code=exc.response.status_code,
                detail=exc.response.text[:500],
            )
            return {"error": f"StarInfinity API error: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            log.warning("starinfinity_get_tasks_network_error", error=str(exc))
            return {"error": f"StarInfinity network error: {exc}"}


class StarInfinityCreateTaskTool(BaseTool):
    name = "starinfinity_create_task"
    description = "Create a new task in StarInfinity."
    input_schema = {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "assignee": {"type": "string"},
            "due_date": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        },
        "required": ["project_id", "title"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = await _get_client()
        if client is None:
            return _NOT_CONFIGURED

        # Build request body from provided kwargs, skipping None values
        body: dict[str, Any] = {}
        for key in ("project_id", "title", "description", "assignee", "due_date", "priority"):
            value = kwargs.get(key)
            if value is not None:
                body[key] = value

        try:
            async with client:
                resp = await client.post("/api/tasks", json=body)
                resp.raise_for_status()
                data = resp.json()

            task_id = data.get("id") or data.get("task_id", "")

            log.info(
                "starinfinity_create_task",
                task_id=task_id,
                project_id=kwargs.get("project_id"),
                title=kwargs.get("title", "")[:80],
            )
            return {"task_id": task_id, "status": "created"}

        except httpx.HTTPStatusError as exc:
            log.warning(
                "starinfinity_create_task_api_error",
                status_code=exc.response.status_code,
                detail=exc.response.text[:500],
            )
            return {"error": f"StarInfinity API error: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            log.warning("starinfinity_create_task_network_error", error=str(exc))
            return {"error": f"StarInfinity network error: {exc}"}


class StarInfinityUpdateTaskTool(BaseTool):
    name = "starinfinity_update_task"
    description = "Update an existing task in StarInfinity."
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "status": {"type": "string"},
            "notes": {"type": "string"},
            "assignee": {"type": "string"},
        },
        "required": ["task_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        client = await _get_client()
        if client is None:
            return _NOT_CONFIGURED

        task_id = kwargs["task_id"]

        # Build request body from provided kwargs (excluding task_id)
        body: dict[str, Any] = {}
        for key in ("status", "notes", "assignee"):
            value = kwargs.get(key)
            if value is not None:
                body[key] = value

        try:
            async with client:
                resp = await client.put(f"/api/tasks/{task_id}", json=body)
                resp.raise_for_status()

            log.info("starinfinity_update_task", task_id=task_id, fields=list(body.keys()))
            return {"status": "updated"}

        except httpx.HTTPStatusError as exc:
            log.warning(
                "starinfinity_update_task_api_error",
                task_id=task_id,
                status_code=exc.response.status_code,
                detail=exc.response.text[:500],
            )
            return {"error": f"StarInfinity API error: {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            log.warning("starinfinity_update_task_network_error", task_id=task_id, error=str(exc))
            return {"error": f"StarInfinity network error: {exc}"}
