"""Google Drive poller — detects changes to watched files and folders."""

from __future__ import annotations

import asyncio
import json
import re

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.common.redis_client import get_redis
from agent1.google_auth.auth import get_drive_service
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)

# Redis key prefixes
_MTIME_PREFIX = "agent1:drive:mtime:"
_FOLDER_FILES_PREFIX = "agent1:drive:folder_files:"
_TTL = 7 * 24 * 3600  # 7 days

# URL parsing patterns
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)"), "folder"),
    (re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)"), "file"),
    (re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)"), "file"),
    (re.compile(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)"), "file"),
    (re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)"), "file"),
    (re.compile(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)"), "file"),
]


def parse_drive_url(url: str) -> tuple[str, str] | None:
    """Parse a Google Drive URL and return (resource_id, 'file'|'folder') or None."""
    for pattern, kind in _PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1), kind
    return None


async def _check_file(
    service: object, file_id: str, redis: object,
) -> dict | None:
    """Check a single file for modifications. Returns change dict or None."""
    try:
        meta = await asyncio.to_thread(
            service.files()  # type: ignore[union-attr]
            .get(
                fileId=file_id,
                fields="id,name,mimeType,modifiedTime,lastModifyingUser,webViewLink",
            )
            .execute,
        )
    except Exception as exc:
        log.warning("drive_file_check_failed", file_id=file_id, error=str(exc))
        return None

    modified_time = meta.get("modifiedTime", "")
    redis_key = f"{_MTIME_PREFIX}{file_id}"

    prev = await redis.get(redis_key)  # type: ignore[union-attr]
    await redis.set(redis_key, modified_time, ex=_TTL)  # type: ignore[union-attr]

    # First observation — store silently
    if prev is None:
        return None

    prev_str = prev.decode() if isinstance(prev, bytes) else prev
    if prev_str == modified_time:
        return None

    modifier = meta.get("lastModifyingUser", {})
    return {
        "file_id": file_id,
        "file_name": meta.get("name", ""),
        "mime_type": meta.get("mimeType", ""),
        "modified_time": modified_time,
        "modified_by": modifier.get("displayName", modifier.get("emailAddress", "")),
        "web_link": meta.get("webViewLink", ""),
        "change_type": "modified",
    }


async def _check_folder(
    service: object, folder_id: str, redis: object,
) -> list[dict]:
    """Check a folder for new/modified files. Returns list of change dicts."""
    try:
        response = await asyncio.to_thread(
            service.files()  # type: ignore[union-attr]
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="files(id,name,mimeType,modifiedTime,lastModifyingUser,webViewLink)",
                pageSize=100,
            )
            .execute,
        )
    except Exception as exc:
        log.warning("drive_folder_check_failed", folder_id=folder_id, error=str(exc))
        return []

    files = response.get("files", [])
    current_ids = {f["id"] for f in files}

    folder_key = f"{_FOLDER_FILES_PREFIX}{folder_id}"
    prev_raw = await redis.get(folder_key)  # type: ignore[union-attr]
    prev_ids: set[str] = set()
    if prev_raw is not None:
        raw = prev_raw.decode() if isinstance(prev_raw, bytes) else prev_raw
        prev_ids = set(json.loads(raw))

    # Store current file IDs
    await redis.set(folder_key, json.dumps(sorted(current_ids)), ex=_TTL)  # type: ignore[union-attr]

    # First observation — store all mtimes silently, no events
    is_first_scan = prev_raw is None

    changes: list[dict] = []
    new_file_ids = current_ids - prev_ids

    for f in files:
        fid = f["id"]
        modified_time = f.get("modifiedTime", "")
        redis_key = f"{_MTIME_PREFIX}{fid}"

        prev_mtime = await redis.get(redis_key)  # type: ignore[union-attr]
        await redis.set(redis_key, modified_time, ex=_TTL)  # type: ignore[union-attr]

        if is_first_scan:
            continue

        modifier = f.get("lastModifyingUser", {})
        info = {
            "file_id": fid,
            "file_name": f.get("name", ""),
            "mime_type": f.get("mimeType", ""),
            "modified_time": modified_time,
            "modified_by": modifier.get("displayName", modifier.get("emailAddress", "")),
            "web_link": f.get("webViewLink", ""),
        }

        if fid in new_file_ids:
            info["change_type"] = "new_file"
            changes.append(info)
        elif prev_mtime is not None:
            prev_str = prev_mtime.decode() if isinstance(prev_mtime, bytes) else prev_mtime
            if prev_str != modified_time:
                info["change_type"] = "modified"
                changes.append(info)

    return changes


async def get_file_name(service: object, file_id: str) -> str:
    """Fetch a file/folder name from Drive API."""
    try:
        meta = await asyncio.to_thread(
            service.files()  # type: ignore[union-attr]
            .get(fileId=file_id, fields="name")
            .execute,
        )
        return meta.get("name", "")
    except Exception:
        return ""


async def poll_drive() -> None:
    """Main poller: iterate watched URLs, detect changes, publish events."""
    log.debug("drive_poll_started")

    service = get_drive_service()
    if service is None:
        log.debug("drive_poll_skipped", reason="Drive service not configured")
        return

    # Load watch list from config table
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT value FROM config WHERE key = 'drive_watch_urls'"
        )

    if not row:
        log.debug("drive_poll_completed", watches=0, changes=0)
        return

    try:
        watches: list[dict] = json.loads(row)
    except (json.JSONDecodeError, TypeError):
        log.warning("drive_poll_bad_config")
        return

    if not watches:
        log.debug("drive_poll_completed", watches=0, changes=0)
        return

    redis = await get_redis()
    published_count = 0

    for watch in watches:
        url = watch.get("url", "")
        parsed = parse_drive_url(url)
        if not parsed:
            continue

        resource_id, kind = parsed

        try:
            if kind == "file":
                change = await _check_file(service, resource_id, redis)
                changes = [change] if change else []
            else:
                changes = await _check_folder(service, resource_id, redis)

            for c in changes:
                dedup_key = f"{c['file_id']}:{c['modified_time']}"
                if await is_duplicate("gdrive", dedup_key):
                    continue

                event_type = (
                    "drive_new_file" if c["change_type"] == "new_file"
                    else "drive_file_changed"
                )
                event = Event(
                    source=EventSource.GDRIVE,
                    event_type=event_type,
                    priority=Priority.LOW,
                    payload={
                        "file_id": c["file_id"],
                        "file_name": c["file_name"],
                        "mime_type": c["mime_type"],
                        "modified_time": c["modified_time"],
                        "modified_by": c["modified_by"],
                        "web_link": c["web_link"],
                        "change_type": c["change_type"],
                        "watch_url": url,
                    },
                    idempotency_key=f"gdrive:{c['file_id']}:{c['modified_time']}",
                )

                await publish_event(event)
                await mark_processed("gdrive", dedup_key)
                published_count += 1

                log.info(
                    "drive_change_detected",
                    file_id=c["file_id"],
                    file_name=c["file_name"],
                    change_type=c["change_type"],
                    modified_by=c["modified_by"],
                )

        except Exception as exc:
            log.error(
                "drive_poll_watch_error",
                url=url,
                error=str(exc),
            )
            continue

    log.debug("drive_poll_completed", watches=len(watches), changes=published_count)
