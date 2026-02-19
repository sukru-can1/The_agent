"""MCP client manager — connects to MCP servers and manages sessions."""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from agent1.common.logging import get_logger
from agent1.tools.mcp.config import MCPServerConfig

log = get_logger(__name__)


class MCPClientManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}  # server_name -> ClientSession
        self._tools: dict[str, list[Any]] = {}  # server_name -> [Tool, ...]
        self._configs: dict[str, MCPServerConfig] = {}

    async def start(self, configs: list[MCPServerConfig]) -> None:
        """Connect to all configured MCP servers and discover their tools."""
        await self._exit_stack.__aenter__()

        for config in configs:
            try:
                await self._connect_server(config)
            except Exception as exc:
                log.error(
                    "mcp_server_connect_failed",
                    server=config.name,
                    error=str(exc),
                )
                # Continue with other servers — don't block startup

    async def _connect_server(self, config: MCPServerConfig) -> None:
        """Connect to a single MCP server based on its transport type."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client, StdioServerParameters
        from mcp.client.sse import sse_client

        if config.transport == "stdio":
            if not config.command:
                log.warning("mcp_stdio_no_command", server=config.name)
                return

            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env={**dict(__import__("os").environ), **config.env} if config.env else None,
            )

            transport = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )

        elif config.transport == "sse":
            if not config.url:
                log.warning("mcp_sse_no_url", server=config.name)
                return

            transport = await self._exit_stack.enter_async_context(
                sse_client(config.url, headers=config.env if config.env else None)
            )

        else:
            log.warning("mcp_unknown_transport", server=config.name, transport=config.transport)
            return

        read_stream, write_stream = transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        # Discover tools
        tools_result = await session.list_tools()
        tools = tools_result.tools

        # Apply tool filter if configured
        if config.tool_filter is not None:
            allowed = set(config.tool_filter)
            tools = [t for t in tools if t.name in allowed]

        self._sessions[config.name] = session
        self._tools[config.name] = tools
        self._configs[config.name] = config

        log.info(
            "mcp_server_connected",
            server=config.name,
            transport=config.transport,
            tools=len(tools),
            tool_names=[t.name for t in tools],
        )

    async def stop(self) -> None:
        """Shut down all MCP server connections."""
        try:
            await self._exit_stack.aclose()
        except Exception as exc:
            log.warning("mcp_shutdown_error", error=str(exc))
        finally:
            self._sessions.clear()
            self._tools.clear()
            self._configs.clear()
            log.info("mcp_servers_stopped")

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on a specific MCP server."""
        session = self._sessions.get(server_name)
        if session is None:
            raise ValueError(f"MCP server not connected: {server_name}")

        result = await session.call_tool(tool_name, arguments)

        # Extract text content from MCP CallToolResult
        texts = []
        for content in result.content:
            if hasattr(content, "text"):
                texts.append(content.text)
            elif hasattr(content, "data"):
                texts.append(str(content.data))
            else:
                texts.append(str(content))

        if result.isError:
            return {"error": "\n".join(texts)}

        return "\n".join(texts) if texts else {"result": "ok"}

    def get_all_tools(self) -> list[tuple[str, Any]]:
        """Return (server_name, mcp_tool) pairs for all discovered tools."""
        pairs = []
        for server_name, tools in self._tools.items():
            for tool in tools:
                pairs.append((server_name, tool))
        return pairs

    def get_server_names(self) -> list[str]:
        """Return names of all connected servers."""
        return list(self._sessions.keys())
