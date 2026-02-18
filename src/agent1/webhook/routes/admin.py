"""Admin API routes for monitoring, config, and DLQ management."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.redis_client import get_redis
from agent1.queue.dlq import get_dlq_entries, resolve_dlq_entry, retry_dlq_entry
from agent1.queue.events import QUEUE_KEY

log = get_logger(__name__)

router = APIRouter(tags=["admin"])


@router.get("/status")
async def admin_status():
    """Agent status: queue depth, pending drafts, last event."""
    redis = await get_redis()
    pool = await get_pool()

    queue_depth = await redis.zcard(QUEUE_KEY)

    async with pool.acquire() as conn:
        pending_drafts = await conn.fetchval(
            "SELECT COUNT(*) FROM email_drafts WHERE status = 'pending'"
        )
        last_action = await conn.fetchrow(
            "SELECT timestamp, system, action_type FROM actions_log ORDER BY timestamp DESC LIMIT 1"
        )
        dlq_count = await conn.fetchval(
            "SELECT COUNT(*) FROM dead_letter_events WHERE resolved_at IS NULL"
        )

    return {
        "queue_depth": queue_depth,
        "pending_drafts": pending_drafts,
        "dlq_count": dlq_count,
        "last_action": dict(last_action) if last_action else None,
    }


@router.get("/drafts")
async def list_drafts(status: str = "pending", limit: int = 20):
    """List email drafts by status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, gmail_message_id, from_address, to_address, subject,
                   draft_body, status, classification, created_at
            FROM email_drafts
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            status,
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/events")
async def list_events(status: str = "pending", limit: int = 50):
    """List recent events."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source, event_type, priority, status, created_at, error
            FROM events
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            status,
            limit,
        )
    return [dict(r) for r in rows]


class ConfigUpdate(BaseModel):
    value: dict | str | int | bool | list


@router.post("/config/{key}")
async def update_config(key: str, body: ConfigUpdate):
    """Update a runtime configuration value."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
            """,
            key,
            json.dumps(body.value),
        )
    log.info("config_updated", key=key)
    return {"key": key, "value": body.value}


@router.get("/config")
async def list_config():
    """List all configuration values."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value, updated_at, description FROM config ORDER BY key")
    return [dict(r) for r in rows]


@router.get("/dlq")
async def list_dlq(limit: int = 20):
    """List unresolved dead-letter queue entries."""
    return await get_dlq_entries(limit)


@router.post("/dlq/{dlq_id}/retry")
async def retry_dlq(dlq_id: str):
    """Retry a DLQ entry by re-publishing it."""
    success = await retry_dlq_entry(dlq_id)
    if not success:
        raise HTTPException(status_code=404, detail="DLQ entry not found or already resolved")
    return {"status": "retried"}


@router.post("/dlq/{dlq_id}/resolve")
async def resolve_dlq(dlq_id: str):
    """Mark a DLQ entry as resolved."""
    success = await resolve_dlq_entry(dlq_id)
    if not success:
        raise HTTPException(status_code=404, detail="DLQ entry not found or already resolved")
    return {"status": "resolved"}


@router.post("/queue/pause")
async def pause_queue():
    """Pause event processing (sets a Redis flag)."""
    redis = await get_redis()
    await redis.set("agent1:queue:paused", "1")
    log.info("queue_paused")
    return {"status": "paused"}


@router.post("/queue/resume")
async def resume_queue():
    """Resume event processing."""
    redis = await get_redis()
    await redis.delete("agent1:queue:paused")
    log.info("queue_resumed")
    return {"status": "resumed"}


# --- Draft approval / rejection ---


class DraftApproveBody(BaseModel):
    edited_body: Optional[str] = None


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: int, body: DraftApproveBody = DraftApproveBody()):
    """Approve a pending email draft, optionally with edits.

    If edited_body is provided, it replaces the draft body and triggers
    feedback learning (edit distance tracking).
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        draft = await conn.fetchrow(
            "SELECT * FROM email_drafts WHERE id = $1 AND status = 'pending'",
            draft_id,
        )
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found or not pending")

        if body.edited_body and body.edited_body != draft["draft_body"]:
            # Store the edited version and track feedback
            await conn.execute(
                """
                UPDATE email_drafts
                SET status = 'approved', edited_body = $2, approved_at = NOW()
                WHERE id = $1
                """,
                draft_id,
                body.edited_body,
            )

            # Track the edit for feedback learning
            try:
                from agent1.feedback.tracker import track_edit
                await track_edit(
                    draft_id=draft_id,
                    original=draft["draft_body"],
                    edited=body.edited_body,
                    sender_domain=_extract_domain(draft["from_address"]),
                    category=draft["classification"],
                )
            except Exception as exc:
                log.warning("feedback_tracking_failed", error=str(exc))
        else:
            await conn.execute(
                """
                UPDATE email_drafts
                SET status = 'approved', approved_at = NOW()
                WHERE id = $1
                """,
                draft_id,
            )

    log.info("draft_approved", draft_id=draft_id, edited=bool(body.edited_body))
    return {"status": "approved", "draft_id": draft_id}


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: int):
    """Reject and discard a pending email draft."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE email_drafts
            SET status = 'rejected'
            WHERE id = $1 AND status = 'pending'
            """,
            draft_id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Draft not found or not pending")

    log.info("draft_rejected", draft_id=draft_id)
    return {"status": "rejected", "draft_id": draft_id}


def _extract_domain(email: str | None) -> str | None:
    """Extract domain from email address."""
    if not email or "@" not in email:
        return None
    return email.split("@")[1].lower()
