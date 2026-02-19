"""MCPToolAdapter — wraps an MCP tool as a BaseTool for the registry."""

from __future__ import annotations

from typing import Any

from agent1.common.logging import get_logger
from agent1.tools.base import BaseTool
from agent1.tools.mcp.client_manager import MCPClientManager

log = get_logger(__name__)


class MCPToolAdapter(BaseTool):
    """Adapts an MCP server tool to the BaseTool interface.

    Namespaces the tool name as ``{server_name}__{tool_name}`` to avoid
    collisions with native tools or other MCP servers.
    """

    def __init__(self, server_name: str, mcp_tool: Any, manager: MCPClientManager) -> None:
        self._server_name = server_name
        self._mcp_tool = mcp_tool
        self._manager = manager

    @property
    def name(self) -> str:
        return f"{self._server_name}__{self._mcp_tool.name}"

    @property
    def description(self) -> str:
        return self._mcp_tool.description or f"MCP tool from {self._server_name}"

    @property
    def input_schema(self) -> dict:
        schema = self._mcp_tool.inputSchema
        if isinstance(schema, dict):
            return schema
        # Pydantic model — convert to dict
        return schema.model_dump() if hasattr(schema, "model_dump") else dict(schema)

    async def execute(self, **kwargs: Any) -> Any:
        log.info(
            "mcp_tool_execute",
            server=self._server_name,
            tool=self._mcp_tool.name,
        )
        return await self._manager.call_tool(
            self._server_name,
            self._mcp_tool.name,
            kwargs,
        )
