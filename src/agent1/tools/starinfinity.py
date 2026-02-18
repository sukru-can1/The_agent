"""StarInfinity project management tools."""

from __future__ import annotations

from typing import Any

from agent1.tools.base import BaseTool


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
        # TODO: Phase 3 — API details TBD
        return {"tasks": [], "message": "StarInfinity integration not yet configured"}


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
        # TODO: Phase 3
        return {"error": "StarInfinity integration not yet configured"}


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
        # TODO: Phase 3
        return {"error": "StarInfinity integration not yet configured"}
