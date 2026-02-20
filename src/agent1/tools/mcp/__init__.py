"""MCP client integration — plug-and-play tool architecture."""

from __future__ import annotations

from agent1.tools.mcp.client_manager import MCPClientManager

_manager: MCPClientManager | None = None


async def start_mcp_servers() -> MCPClientManager:
    """Start all configured MCP servers and register their tools."""
    global _manager

    from agent1.common.logging import get_logger
    from agent1.common.settings import get_settings
    from agent1.tools.mcp.adapter import MCPToolAdapter
    from agent1.tools.mcp.config import load_mcp_config
    from agent1.tools.registry import register_tool

    log = get_logger(__name__)
    settings = get_settings()

    configs = load_mcp_config(settings.mcp_config_path)
    enabled = [c for c in configs if c.enabled]

    if not enabled:
        log.info("mcp_no_servers_enabled", total=len(configs))
        _manager = MCPClientManager()
        return _manager

    _manager = MCPClientManager()
    await _manager.start(enabled)

    # Register each discovered MCP tool as a BaseTool in the registry
    for server_name, mcp_tool in _manager.get_all_tools():
        adapter = MCPToolAdapter(
            server_name=server_name,
            mcp_tool=mcp_tool,
            manager=_manager,
        )
        register_tool(adapter)

    tool_count = len(_manager.get_all_tools())
    log.info("mcp_tools_registered", servers=len(enabled), tools=tool_count)
    return _manager


async def stop_mcp_servers() -> None:
    """Shut down all running MCP server connections."""
    global _manager
    if _manager is not None:
        await _manager.stop()
        _manager = None
