"""Google Chat tools — post messages, reply, read."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings
from agent1.google_auth.auth import get_chat_service
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "Google Chat not configured \u2014 set service account credentials"}


def _resolve_space(space: str) -> str:
    """Resolve friendly space name to full Chat API space name.

    Accepts short aliases ('alerts', 'log', 'summary', 'dm') that map to
    settings values, or a raw space ID / full ``spaces/…`` path.
    """
    settings = get_settings()
    mapping = {
        "alerts": settings.gchat_space_alerts,
        "log": settings.gchat_space_log,
        "summary": settings.gchat_space_summary,
        "dm": settings.gchat_dm_sukru,
    }
    resolved = mapping.get(space, space)
    # If it doesn't start with "spaces/", prepend it
    if resolved and not resolved.startswith("spaces/"):
        resolved = f"spaces/{resolved}"
    return resolved


class GChatPostMessageTool(BaseTool):
    name = "gchat_post_message"
    description = "Post a message to a Google Chat space. Use for alerts, updates, and presenting email drafts for approval."
    input_schema = {
        "type": "object",
        "properties": {
            "space": {
                "type": "string",
                "description": "Space name/ID. Key spaces: 'alerts', 'log', 'summary', 'dm', or a full space ID.",
            },
            "message": {"type": "string"},
            "thread_key": {"type": "string", "description": "Thread key for threading related messages"},
            "cards": {"type": "object", "description": "Card message with buttons (for approval flows)"},
        },
        "required": ["space", "message"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_chat_service()
        if service is None:
            return _NOT_CONFIGURED

        space = kwargs["space"]
        message_text = kwargs["message"]
        thread_key = kwargs.get("thread_key")
        cards = kwargs.get("cards")

        space_name = _resolve_space(space)
        request_id = uuid.uuid4().hex

        body: dict[str, Any] = {"text": message_text}

        if thread_key:
            body["thread"] = {"threadKey": thread_key}

        if cards:
            body["cardsV2"] = cards if isinstance(cards, list) else [cards]

        try:
            result = await asyncio.to_thread(
                lambda: (
                    service.spaces()
                    .messages()
                    .create(
                        parent=space_name,
                        body=body,
                        requestId=request_id,
                        messageReplyOption="REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD",
                    )
                    .execute()
                ),
            )

            # Extract thread key from the response thread name
            response_thread = result.get("thread", {})
            response_thread_key = response_thread.get("name", "").split("/")[-1] if response_thread.get("name") else thread_key

            log.info(
                "gchat_message_posted",
                space=space_name,
                message_id=result.get("name"),
                thread_key=response_thread_key,
            )

            return {
                "message_id": result.get("name"),
                "space": space_name,
                "thread_key": response_thread_key,
            }
        except Exception as exc:
            log.error("gchat_post_message_error", space=space_name, error=str(exc))
            return {"error": f"Failed to post message: {exc}"}


class GChatReplyAsAgentTool(BaseTool):
    name = "gchat_reply_as_agent"
    description = "Reply to a Google Chat message on behalf of the agent."
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
        service = get_chat_service()
        if service is None:
            return _NOT_CONFIGURED

        space = kwargs["space"]
        raw_message = kwargs["message"]
        thread_key = kwargs.get("thread_key")

        space_name = _resolve_space(space)
        request_id = uuid.uuid4().hex

        body: dict[str, Any] = {"text": raw_message}

        if thread_key:
            body["thread"] = {"threadKey": thread_key}

        try:
            result = await asyncio.to_thread(
                lambda: (
                    service.spaces()
                    .messages()
                    .create(
                        parent=space_name,
                        body=body,
                        requestId=request_id,
                        messageReplyOption="REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD",
                    )
                    .execute()
                ),
            )

            response_thread = result.get("thread", {})
            response_thread_key = response_thread.get("name", "").split("/")[-1] if response_thread.get("name") else thread_key

            log.info(
                "gchat_reply_posted",
                space=space_name,
                message_id=result.get("name"),
                thread_key=response_thread_key,
            )

            return {
                "message_id": result.get("name"),
                "thread_key": response_thread_key,
            }
        except Exception as exc:
            log.error("gchat_reply_error", space=space_name, error=str(exc))
            return {"error": f"Failed to reply: {exc}"}


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
        service = get_chat_service()
        if service is None:
            return _NOT_CONFIGURED

        space = kwargs["space"]
        max_results = kwargs.get("max_results", 20)

        space_name = _resolve_space(space)

        try:
            result = await asyncio.to_thread(
                lambda: (
                    service.spaces()
                    .messages()
                    .list(parent=space_name, pageSize=max_results)
                    .execute()
                ),
            )

            messages = []
            for msg in result.get("messages", []):
                sender = msg.get("sender", {})
                thread = msg.get("thread", {})
                thread_name = thread.get("name", "")

                messages.append({
                    "message_id": msg.get("name"),
                    "sender": sender.get("displayName", sender.get("name", "unknown")),
                    "text": msg.get("text", ""),
                    "create_time": msg.get("createTime"),
                    "thread_key": thread_name.split("/")[-1] if thread_name else None,
                })

            log.info(
                "gchat_messages_fetched",
                space=space_name,
                count=len(messages),
            )

            return {"messages": messages}
        except Exception as exc:
            log.error("gchat_get_messages_error", space=space_name, error=str(exc))
            return {"error": f"Failed to get messages: {exc}"}
