"""Dynamic tool builder — lets Claude create new tools at runtime."""

from __future__ import annotations

import asyncio
import json
import re
import textwrap
from typing import Any

from agent1.common.logging import get_logger
from agent1.tools.base import BaseTool

log = get_logger(__name__)

# Imports that are allowed inside dynamic tool code
ALLOWED_IMPORTS = frozenset({
    "httpx", "json", "re", "datetime", "math", "asyncio",
    "collections", "itertools", "functools", "urllib.parse",
    "base64", "hashlib", "hmac", "uuid", "decimal", "statistics",
})

# Patterns that are blocked in dynamic tool code
BLOCKED_PATTERNS = [
    re.compile(r"\bimport\s+(os|subprocess|sys|importlib|shutil|pathlib)\b"),
    re.compile(r"\bfrom\s+(os|subprocess|sys|importlib|shutil|pathlib)\b"),
    re.compile(r"\b(eval|exec|compile|__import__)\s*\("),
    re.compile(r"\b(globals|locals|vars|dir)\s*\("),
    re.compile(r"\bopen\s*\("),
    re.compile(r"\b__\w+__"),  # dunder access
]

DYNAMIC_TOOL_TIMEOUT = 30  # seconds


def _validate_code(code: str) -> str | None:
    """Validate dynamic tool code. Returns error message or None if valid."""
    for pattern in BLOCKED_PATTERNS:
        match = pattern.search(code)
        if match:
            return f"Blocked pattern found: {match.group()}"

    # Check that code compiles
    try:
        compile(code, "<dynamic_tool>", "exec")
    except SyntaxError as e:
        return f"Syntax error: {e}"

    return None


class DynamicTool(BaseTool):
    """A tool created dynamically from code stored in the database."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_input_schema: dict,
        tool_code: str,
    ) -> None:
        self._name = tool_name
        self._description = tool_description
        self._input_schema = tool_input_schema
        self._code = tool_code

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_schema(self) -> dict:
        return self._input_schema

    async def execute(self, **kwargs: Any) -> Any:
        import httpx

        # Build restricted global scope
        scope: dict[str, Any] = {
            "httpx": httpx,
            "json": json,
            "re": re,
            "asyncio": asyncio,
            "math": __import__("math"),
            "datetime": __import__("datetime"),
            "params": kwargs,
            "result": None,
        }

        # Wrap code so it assigns to `result`
        wrapped = textwrap.dedent(self._code)

        try:
            exec(compile(wrapped, f"<dynamic:{self._name}>", "exec"), scope)

            # If the code defined an async function named 'run', call it
            if callable(scope.get("run")):
                coro = scope["run"](**kwargs)
                if asyncio.iscoroutine(coro):
                    return await asyncio.wait_for(coro, timeout=DYNAMIC_TOOL_TIMEOUT)
                return coro

            return scope.get("result", "Tool executed (no result returned)")

        except asyncio.TimeoutError:
            return {"error": f"Dynamic tool '{self._name}' timed out after {DYNAMIC_TOOL_TIMEOUT}s"}
        except Exception as exc:
            log.error("dynamic_tool_error", tool=self._name, error=str(exc))
            return {"error": str(exc)}


class DynamicToolBuilder(BaseTool):
    """Meta-tool that lets Claude create new tools at runtime."""

    name = "create_dynamic_tool"
    description = (
        "Create a new tool at runtime. The tool will be persisted and available on restart. "
        "Write the code as an async function named 'run' that takes keyword arguments matching "
        "the input_schema and returns a result. Available imports: httpx, json, re, datetime, "
        "math, asyncio. Example: async def run(*, city: str) -> str: ..."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Tool name (lowercase, underscores). Will be prefixed with 'dynamic__'.",
            },
            "description": {
                "type": "string",
                "description": "What the tool does — shown to Claude when selecting tools.",
            },
            "input_schema": {
                "type": "object",
                "description": "JSON Schema for the tool's input parameters.",
            },
            "code": {
                "type": "string",
                "description": "Python code defining an async function named 'run'.",
            },
        },
        "required": ["name", "description", "input_schema", "code"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.common.db import get_pool
        from agent1.tools.registry import get_tool, register_tool

        raw_name = kwargs["name"]
        tool_name = f"dynamic__{raw_name}" if not raw_name.startswith("dynamic__") else raw_name
        tool_description = kwargs["description"]
        tool_input_schema = kwargs["input_schema"]
        code = kwargs["code"]

        # Check for name collision
        if get_tool(tool_name) is not None:
            return {"error": f"Tool '{tool_name}' already exists"}

        # Validate code safety
        error = _validate_code(code)
        if error:
            return {"error": f"Code validation failed: {error}"}

        # Persist to database
        pool = await get_pool()
        await pool.execute(
            """
            INSERT INTO dynamic_tools (name, description, input_schema, code, created_by)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            ON CONFLICT (name) DO UPDATE SET
                description = EXCLUDED.description,
                input_schema = EXCLUDED.input_schema,
                code = EXCLUDED.code,
                active = true
            """,
            tool_name,
            tool_description,
            json.dumps(tool_input_schema),
            code,
            "agent",
        )

        # Register in memory
        tool = DynamicTool(tool_name, tool_description, tool_input_schema, code)
        register_tool(tool)

        log.info("dynamic_tool_created", tool=tool_name)
        return {
            "status": "created",
            "tool_name": tool_name,
            "message": f"Tool '{tool_name}' is now available.",
        }


class ListDynamicToolsTool(BaseTool):
    """Lists all active dynamic tools."""

    name = "list_dynamic_tools"
    description = "List all dynamically created tools that are currently active."
    input_schema = {
        "type": "object",
        "properties": {
            "include_code": {
                "type": "boolean",
                "description": "Whether to include the tool source code in results.",
                "default": False,
            },
        },
    }

    async def execute(self, **kwargs: Any) -> Any:
        from agent1.common.db import get_pool

        include_code = kwargs.get("include_code", False)
        pool = await get_pool()

        rows = await pool.fetch(
            "SELECT name, description, input_schema, code, created_at FROM dynamic_tools WHERE active = true ORDER BY created_at"
        )

        tools = []
        for row in rows:
            entry: dict[str, Any] = {
                "name": row["name"],
                "description": row["description"],
                "input_schema": json.loads(row["input_schema"]) if isinstance(row["input_schema"], str) else row["input_schema"],
                "created_at": row["created_at"].isoformat(),
            }
            if include_code:
                entry["code"] = row["code"]
            tools.append(entry)

        return {"tools": tools, "count": len(tools)}


async def load_dynamic_tools() -> None:
    """Load all active dynamic tools from the database and register them."""
    from agent1.common.db import get_pool
    from agent1.tools.registry import register_tool

    try:
        pool = await get_pool()

        # Check if the table exists
        exists = await pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dynamic_tools')"
        )
        if not exists:
            log.info("dynamic_tools_table_missing")
            return

        rows = await pool.fetch(
            "SELECT name, description, input_schema, code FROM dynamic_tools WHERE active = true"
        )

        for row in rows:
            schema = row["input_schema"]
            if isinstance(schema, str):
                schema = json.loads(schema)

            tool = DynamicTool(
                tool_name=row["name"],
                tool_description=row["description"],
                tool_input_schema=schema,
                tool_code=row["code"],
            )
            register_tool(tool)

        # Also register the builder and list tools
        register_tool(DynamicToolBuilder())
        register_tool(ListDynamicToolsTool())

        log.info("dynamic_tools_loaded", count=len(rows))

    except Exception as exc:
        log.warning("dynamic_tools_load_failed", error=str(exc))
        # Still register builder tools even if DB load fails
        register_tool(DynamicToolBuilder())
        register_tool(ListDynamicToolsTool())
