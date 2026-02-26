"""Tool registry and dispatch."""

from __future__ import annotations

from typing import Any

from agent1.common.logging import get_logger
from agent1.common.models import EventSource
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_registry: dict[str, BaseTool] = {}


def register_tool(tool: BaseTool) -> None:
    """Register a tool in the global registry."""
    _registry[tool.name] = tool
    log.debug("tool_registered", tool=tool.name)


def get_tool(name: str) -> BaseTool | None:
    """Get a tool by name."""
    return _registry.get(name)


def get_tool_definitions() -> list[dict]:
    """Get all tool definitions for Claude API calls."""
    return [tool.to_tool_definition() for tool in _registry.values()]


def get_filtered_tool_definitions(source: EventSource) -> list[dict]:
    """Get tool definitions filtered by event source.

    MCP tools (containing '__') and dynamic tools ('dynamic__' prefix) always pass through.
    Native tools are filtered by source→group mapping with credential gating.
    """
    from agent1.tools.groups import get_tool_names_for_source

    allowed = get_tool_names_for_source(source)
    defs = []
    for tool in _registry.values():
        # MCP and dynamic tools always pass through
        if "__" in tool.name:
            defs.append(tool.to_tool_definition())
        elif tool.name in allowed:
            defs.append(tool.to_tool_definition())
    return defs


async def execute_tool(name: str, params: dict[str, Any]) -> Any:
    """Execute a tool by name with given parameters."""
    tool = _registry.get(name)
    if tool is None:
        raise ValueError(f"Unknown tool: {name}")

    log.info("tool_executing", tool=name)
    result = await tool.execute(**params)
    log.info("tool_executed", tool=name)
    return result


def register_all_tools() -> None:
    """Register all available tools."""
    from agent1.tools.feedbacks import (
        FeedbacksGetInsightsTool,
        FeedbacksGetOverviewTool,
        FeedbacksGetSurveyResponsesTool,
        FeedbacksGetTasksTool,
        FeedbacksGetTrustpilotReviewsTool,
        FeedbacksStartAutoReporterTool,
        FeedbacksTriggerTrustpilotSyncTool,
    )
    from agent1.tools.freshdesk import (
        FreshdeskAddNoteTool,
        FreshdeskGetTicketsTool,
        FreshdeskGetTicketTool,
        FreshdeskUpdateTicketTool,
    )
    from agent1.tools.gmail import (
        GmailDraftReplyTool,
        GmailGetEmailTool,
        GmailGetNewEmailsTool,
        GmailLabelEmailTool,
        GmailSendApprovedTool,
    )
    from agent1.tools.google_chat import (
        GChatGetMessagesTool,
        GChatPostMessageTool,
        GChatReplyAsAgentTool,
    )
    from agent1.tools.google_chat_user import (
        GChatListMySpacesTool,
        GChatReplyAsUserTool,
    )
    from agent1.tools.google_drive import (
        DriveReadDocumentTool,
        DriveSearchTool,
    )
    from agent1.tools.memory import (
        MemorySearchTool,
        MemoryStoreIncidentTool,
        MemoryStoreKnowledgeTool,
    )
    from agent1.tools.starinfinity import (
        StarInfinityCreateTaskTool,
        StarInfinityGetTasksTool,
        StarInfinityListBoardsTool,
        StarInfinityUpdateTaskTool,
    )

    all_tools = [
        # Gmail
        GmailGetNewEmailsTool(),
        GmailGetEmailTool(),
        GmailDraftReplyTool(),
        GmailSendApprovedTool(),
        GmailLabelEmailTool(),
        # Google Chat
        GChatPostMessageTool(),
        GChatReplyAsAgentTool(),
        GChatGetMessagesTool(),
        # Google Drive
        DriveSearchTool(),
        DriveReadDocumentTool(),
        # Freshdesk
        FreshdeskGetTicketsTool(),
        FreshdeskGetTicketTool(),
        FreshdeskAddNoteTool(),
        FreshdeskUpdateTicketTool(),
        # StarInfinity
        StarInfinityListBoardsTool(),
        StarInfinityGetTasksTool(),
        StarInfinityCreateTaskTool(),
        StarInfinityUpdateTaskTool(),
        # Feedbacks
        FeedbacksGetInsightsTool(),
        FeedbacksGetOverviewTool(),
        FeedbacksGetTrustpilotReviewsTool(),
        FeedbacksGetTasksTool(),
        FeedbacksGetSurveyResponsesTool(),
        FeedbacksStartAutoReporterTool(),
        FeedbacksTriggerTrustpilotSyncTool(),
        # Memory
        MemorySearchTool(),
        MemoryStoreIncidentTool(),
        MemoryStoreKnowledgeTool(),
        # Google Chat (user mode)
        GChatReplyAsUserTool(),
        GChatListMySpacesTool(),
    ]

    for tool in all_tools:
        register_tool(tool)

    log.info("all_tools_registered", count=len(all_tools))


async def register_mcp_tools() -> None:
    """Discover and register tools from configured MCP servers."""
    from agent1.tools.mcp import start_mcp_servers

    await start_mcp_servers()


async def register_dynamic_tools() -> None:
    """Load persisted dynamic tools from database."""
    from agent1.common.settings import get_settings

    settings = get_settings()
    if not settings.dynamic_tools_enabled:
        log.info("dynamic_tools_disabled")
        return

    from agent1.tools.mcp.builder import load_dynamic_tools

    await load_dynamic_tools()
