"""Google Drive tools — search and read documents."""

from __future__ import annotations

import asyncio
import io
from typing import Any

from agent1.common.logging import get_logger
from agent1.google_auth.auth import get_drive_service
from agent1.tools.base import BaseTool

log = get_logger(__name__)

_NOT_CONFIGURED = {"error": "Google Drive not configured — set Google OAuth credentials"}


class DriveSearchTool(BaseTool):
    name = "drive_search"
    description = "Search Google Drive for documents. Use to find contracts, SOPs, reports, price lists — anything that provides context for decisions."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query (supports Google Drive search syntax)"},
            "file_type": {
                "type": "string",
                "enum": ["document", "spreadsheet", "presentation", "pdf", "any"],
                "default": "any",
            },
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_drive_service()
        if service is None:
            return _NOT_CONFIGURED

        query = kwargs["query"]
        file_type = kwargs.get("file_type", "any")
        max_results = kwargs.get("max_results", 10)

        # Build the Drive query
        drive_query = f"fullText contains '{query}'"

        mime_type_map = {
            "document": "application/vnd.google-apps.document",
            "spreadsheet": "application/vnd.google-apps.spreadsheet",
            "presentation": "application/vnd.google-apps.presentation",
            "pdf": "application/pdf",
        }

        if file_type in mime_type_map:
            drive_query += f" and mimeType = '{mime_type_map[file_type]}'"

        try:
            response = await asyncio.to_thread(
                service.files()
                .list(
                    q=drive_query,
                    pageSize=max_results,
                    fields="files(id,name,mimeType,modifiedTime,webViewLink)",
                )
                .execute,
            )

            files = response.get("files", [])

            log.info("drive_search", query=query, file_type=file_type, results=len(files))
            return {"files": files}

        except Exception as exc:
            log.error("drive_search_error", query=query, error=str(exc))
            return {"error": f"Drive search failed: {exc}"}


class DriveReadDocumentTool(BaseTool):
    name = "drive_read_document"
    description = "Read the content of a Google Drive document. Returns the text content."
    input_schema = {
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "max_length": {"type": "integer", "default": 5000, "description": "Max characters to return"},
        },
        "required": ["file_id"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        service = get_drive_service()
        if service is None:
            return _NOT_CONFIGURED

        file_id = kwargs["file_id"]
        max_length = kwargs.get("max_length", 5000)

        try:
            # First, get the file metadata to determine the mimeType
            metadata = await asyncio.to_thread(
                service.files()
                .get(fileId=file_id, fields="id,name,mimeType")
                .execute,
            )
            mime_type = metadata.get("mimeType", "")

            if mime_type.startswith("application/vnd.google-apps.document"):
                # Google Docs: export as plain text
                content_bytes = await asyncio.to_thread(
                    service.files()
                    .export(fileId=file_id, mimeType="text/plain")
                    .execute,
                )
                # export() returns bytes
                if isinstance(content_bytes, bytes):
                    content = content_bytes.decode("utf-8", errors="replace")
                else:
                    content = str(content_bytes)
            else:
                # Other files (PDFs, etc.): download binary content
                request = service.files().get_media(fileId=file_id)

                buffer = io.BytesIO()

                # Use the googleapiclient MediaIoBaseDownload for streaming,
                # but for simplicity we can also just execute and read
                raw_bytes = await asyncio.to_thread(request.execute)

                if isinstance(raw_bytes, bytes):
                    buffer.write(raw_bytes)
                else:
                    buffer.write(str(raw_bytes).encode("utf-8"))

                content = buffer.getvalue().decode("utf-8", errors="replace")

            # Truncate to max_length
            truncated = len(content) > max_length
            if truncated:
                content = content[:max_length]

            log.info(
                "drive_read_document",
                file_id=file_id,
                mime_type=mime_type,
                length=len(content),
                truncated=truncated,
            )
            return {
                "file_id": file_id,
                "content": content,
                "truncated": truncated,
            }

        except Exception as exc:
            log.error("drive_read_document_error", file_id=file_id, error=str(exc))
            return {"error": f"Failed to read document {file_id}: {exc}"}
