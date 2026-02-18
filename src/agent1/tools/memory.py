"""Memory tools — search and store incidents/knowledge via pgvector."""

from __future__ import annotations

from typing import Any

from agent1.tools.base import BaseTool


class MemorySearchTool(BaseTool):
    name = "memory_search"
    description = "Search the agent's memory for relevant past incidents, resolutions, or learned knowledge. ALWAYS search memory before making decisions about recurring issues."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language search query"},
            "category": {
                "type": "string",
                "enum": ["incidents", "knowledge", "actions", "all"],
                "default": "all",
            },
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.memory.manager import search_memory

        return await search_memory(
            query=kwargs["query"],
            category=kwargs.get("category", "all"),
            limit=kwargs.get("limit", 5),
        )


class MemoryStoreIncidentTool(BaseTool):
    name = "memory_store_incident"
    description = "Store a new incident and its resolution in memory for future reference."
    input_schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "description": {"type": "string"},
            "resolution": {"type": "string"},
            "market": {"type": "string", "description": "Market code (e.g., DE, TR, EN)"},
            "systems_involved": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["category", "description"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.memory.manager import store_incident

        return await store_incident(**kwargs)


class MemoryStoreKnowledgeTool(BaseTool):
    name = "memory_store_knowledge"
    description = "Store a new piece of knowledge or rule. Use when taught something by the user or when discovering a pattern."
    input_schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "content": {"type": "string"},
            "source": {
                "type": "string",
                "enum": ["taught_by_user", "learned_from_incident", "configured", "feedback_learning"],
            },
        },
        "required": ["category", "content", "source"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.memory.manager import store_knowledge

        return await store_knowledge(**kwargs)
