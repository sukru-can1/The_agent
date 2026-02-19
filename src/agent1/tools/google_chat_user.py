"""Google Chat user-mode tools — respond as Sukru (OAuth, not service account)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from agent1.common.logging import get_logger
from agent1.google_auth.auth import get_chat_user_service
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "Google Chat user mode not configured — set OAuth credentials with Chat scopes"}


class GChatReplyAsUserTool(BaseTool):
    name = "gchat_reply_as_user"
    description = (
        "Send a message in a Google Chat space as Sukru (the user's own account). "
        "Use this for responding to conversations where people are talking to Sukru directly. "
        "Messages appear as normal messages from Sukru, not from a bot."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "space_id": {
                "type": "string",
                "description": "The Chat space ID (e.g. 'spaces/AAAA...' or just the ID part).",
            },
            "text": {"type": "string", "description": "Message text to send."},
            "thread_id": {
                "type": "string",
                "description": "Thread name/ID to reply in (optional — omit for new thread).",
            },
        },
        "required": ["space_id", "text"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_chat_user_service()
        if service is None:
            return _NOT_CONFIGURED

        space_id = kwargs["space_id"]
        text = kwargs["text"]
        thread_id = kwargs.get("thread_id")

        if not space_id.startswith("spaces/"):
            space_id = f"spaces/{space_id}"

        request_id = uuid.uuid4().hex
        body: dict[str, Any] = {"text": text}

        if thread_id:
            # Thread name format: spaces/SPACE_ID/threads/THREAD_ID
            thread_name = thread_id if "/" in thread_id else f"{space_id}/threads/{thread_id}"
            body["thread"] = {"name": thread_name}

        try:
            result = await asyncio.to_thread(
                lambda: (
                    service.spaces()
                    .messages()
                    .create(
                        parent=space_id,
                        body=body,
                        requestId=request_id,
                        messageReplyOption="REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD",
                    )
                    .execute()
                ),
            )

            response_thread = result.get("thread", {})
            thread_name = response_thread.get("name", "")

            log.info(
                "gchat_user_message_sent",
                space=space_id,
                message_id=result.get("name"),
                thread=thread_name,
            )

            return {
                "message_id": result.get("name"),
                "space": space_id,
                "thread": thread_name,
            }
        except Exception as exc:
            log.error("gchat_user_reply_error", space=space_id, error=str(exc))
            return {"error": f"Failed to send message as user: {exc}"}


class GChatListMySpacesTool(BaseTool):
    name = "gchat_list_my_spaces"
    description = (
        "List all Google Chat spaces that Sukru is a member of. "
        "Returns space names, display names, and types."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_chat_user_service()
        if service is None:
            return _NOT_CONFIGURED

        try:
            result = await asyncio.to_thread(
                lambda: service.spaces().list(pageSize=100).execute(),
            )

            spaces = []
            for space in result.get("spaces", []):
                spaces.append({
                    "name": space.get("name"),
                    "display_name": space.get("displayName", ""),
                    "type": space.get("type", ""),
                    "space_type": space.get("spaceType", ""),
                    "single_user_bot_dm": space.get("singleUserBotDm", False),
                })

            log.info("gchat_user_spaces_listed", count=len(spaces))
            return {"spaces": spaces, "count": len(spaces)}

        except Exception as exc:
            log.error("gchat_list_spaces_error", error=str(exc))
            return {"error": f"Failed to list spaces: {exc}"}
