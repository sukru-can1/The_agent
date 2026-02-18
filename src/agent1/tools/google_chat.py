"""Google Chat tools — post messages, reply, read."""

from __future__ import annotations

from typing import Any

from agent1.tools.base import BaseTool


class GChatPostMessageTool(BaseTool):
    name = "gchat_post_message"
    description = "Post a message to a Google Chat space. Use for alerts, updates, and presenting email drafts for approval."
    input_schema = {
        "type": "object",
        "properties": {
            "space": {
                "type": "string",
                "description": "Space name/ID. Key spaces: 'ops-agent-alerts', 'ops-agent-log', 'ops-daily-summary', or DM to Sukru",
            },
            "message": {"type": "string"},
            "thread_key": {"type": "string", "description": "Thread key for threading related messages"},
            "cards": {"type": "object", "description": "Card message with buttons (for approval flows)"},
        },
        "required": ["space", "message"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        # TODO: Phase 1 — implement with Google Chat API
        return {"message": "Google Chat integration not yet configured"}


class GChatReplyAsAgentTool(BaseTool):
    name = "gchat_reply_as_agent"
    description = "Reply to a Google Chat message on behalf of the agent. Always prefix with '[via AGENT1]'."
    input_schema = {
        "type": "object",
        "properties": {
            "space": {"type": "string"},
            "thread_key": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["space", "message"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        # TODO: Phase 1
        return {"message": "Google Chat integration not yet configured"}


class GChatGetMessagesTool(BaseTool):
    name = "gchat_get_messages"
    description = "Read recent messages from a Google Chat space or DM."
    input_schema = {
        "type": "object",
        "properties": {
            "space": {"type": "string"},
            "max_results": {"type": "integer", "default": 20},
        },
        "required": ["space"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        # TODO: Phase 1
        return {"messages": [], "message": "Google Chat integration not yet configured"}
