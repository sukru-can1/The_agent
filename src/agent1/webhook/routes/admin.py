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


# --- Analytics ---


@router.get("/analytics/daily-costs")
async def analytics_daily_costs(days: int = 30):
    """Daily model cost breakdown from actions_log token counts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DATE(timestamp) AS day,
                   model_used,
                   COUNT(*) AS calls,
                   SUM(input_tokens) AS input_tokens,
                   SUM(output_tokens) AS output_tokens
            FROM actions_log
            WHERE timestamp >= NOW() - make_interval(days => $1)
              AND model_used IS NOT NULL AND model_used != ''
            GROUP BY DATE(timestamp), model_used
            ORDER BY day DESC, model_used
            """,
            days,
        )

    # Compute estimated costs per model
    cost_map = {
        "claude-3-5-haiku-20241022": {"input": 1.0, "output": 5.0},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    }

    results = []
    for r in rows:
        model = r["model_used"]
        rates = cost_map.get(model, {"input": 3.0, "output": 15.0})
        cost = (r["input_tokens"] * rates["input"] + r["output_tokens"] * rates["output"]) / 1_000_000
        results.append({
            "day": str(r["day"]),
            "model": model,
            "calls": r["calls"],
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "estimated_cost_usd": round(cost, 4),
        })
    return results


@router.get("/analytics/approval-rate")
async def analytics_approval_rate(days: int = 30):
    """Draft approval, rejection, and edit rates."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DATE(created_at) AS day,
                   status,
                   COUNT(*) AS count
            FROM email_drafts
            WHERE created_at >= NOW() - make_interval(days => $1)
            GROUP BY DATE(created_at), status
            ORDER BY day DESC
            """,
            days,
        )

        # Edits ratio (drafts that were edited before approval)
        edit_stats = await conn.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE edited_body IS NOT NULL) AS edited,
                   COUNT(*) AS total
            FROM email_drafts
            WHERE created_at >= NOW() - make_interval(days => $1)
              AND status IN ('approved', 'sent')
            """,
            days,
        )

    by_day: dict[str, dict] = {}
    for r in rows:
        day = str(r["day"])
        if day not in by_day:
            by_day[day] = {"day": day, "approved": 0, "rejected": 0, "pending": 0, "sent": 0}
        by_day[day][r["status"]] = r["count"]

    return {
        "daily": list(by_day.values()),
        "edit_rate": {
            "edited": edit_stats["edited"] if edit_stats else 0,
            "total": edit_stats["total"] if edit_stats else 0,
            "ratio": round(edit_stats["edited"] / max(edit_stats["total"], 1), 3) if edit_stats else 0,
        },
    }


@router.get("/analytics/response-time")
async def analytics_response_time(days: int = 30):
    """Average response/processing time from actions_log."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DATE(timestamp) AS day,
                   system,
                   COUNT(*) AS count,
                   AVG(latency_ms) AS avg_latency_ms,
                   MAX(latency_ms) AS max_latency_ms,
                   PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms
            FROM actions_log
            WHERE timestamp >= NOW() - make_interval(days => $1)
              AND latency_ms > 0
            GROUP BY DATE(timestamp), system
            ORDER BY day DESC
            """,
            days,
        )
    return [
        {
            "day": str(r["day"]),
            "system": r["system"],
            "count": r["count"],
            "avg_latency_ms": round(float(r["avg_latency_ms"]), 1),
            "max_latency_ms": r["max_latency_ms"],
            "p95_latency_ms": round(float(r["p95_latency_ms"]), 1) if r["p95_latency_ms"] else None,
        }
        for r in rows
    ]


@router.get("/analytics/summary")
async def analytics_summary():
    """Overall analytics summary — events processed, costs, drafts, errors."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Events today
        events_today = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE created_at >= CURRENT_DATE"
        )
        events_week = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'"
        )

        # Drafts
        drafts_pending = await conn.fetchval(
            "SELECT COUNT(*) FROM email_drafts WHERE status = 'pending'"
        )
        drafts_sent = await conn.fetchval(
            "SELECT COUNT(*) FROM email_drafts WHERE status = 'sent' AND created_at >= CURRENT_DATE - INTERVAL '7 days'"
        )

        # Errors
        failed_today = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE status = 'failed' AND created_at >= CURRENT_DATE"
        )
        dlq_unresolved = await conn.fetchval(
            "SELECT COUNT(*) FROM dead_letter_events WHERE resolved_at IS NULL"
        )

        # Token usage today
        tokens = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens
            FROM actions_log
            WHERE timestamp >= CURRENT_DATE
            """
        )

        # Top event types this week
        top_types = await conn.fetch(
            """
            SELECT event_type, source, COUNT(*) AS count
            FROM events
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY event_type, source
            ORDER BY count DESC
            LIMIT 10
            """
        )

    return {
        "events": {
            "today": events_today,
            "this_week": events_week,
        },
        "drafts": {
            "pending": drafts_pending,
            "sent_this_week": drafts_sent,
        },
        "errors": {
            "failed_today": failed_today,
            "dlq_unresolved": dlq_unresolved,
        },
        "tokens_today": {
            "input": tokens["input_tokens"] if tokens else 0,
            "output": tokens["output_tokens"] if tokens else 0,
        },
        "top_event_types": [dict(r) for r in top_types],
    }


@router.get("/knowledge")
async def list_knowledge(limit: int = 50):
    """List knowledge base entries."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, category, content, source, created_at, active,
                   confidence, supersedes_id
            FROM knowledge
            WHERE active = true
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/actions")
async def list_actions(limit: int = 50):
    """List recent agent actions (audit log)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, timestamp, system, action_type, outcome,
                   model_used, input_tokens, output_tokens, latency_ms
            FROM actions_log
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/diag/pgvector")
async def diag_pgvector():
    """Check pgvector extension and vector columns."""
    results: dict = {}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            ext = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            results["extension"] = ext or "NOT INSTALLED"

            cols = await conn.fetch(
                """
                SELECT table_name, column_name, udt_name
                FROM information_schema.columns
                WHERE udt_name = 'vector'
                ORDER BY table_name
                """
            )
            results["vector_columns"] = [dict(r) for r in cols]

            tables = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
            results["tables"] = [r["tablename"] for r in tables]

            try:
                await conn.execute("SELECT '[1,2,3]'::vector(3)")
                results["vector_cast_test"] = "OK"
            except Exception as e:
                results["vector_cast_test"] = f"FAILED: {e}"
    except Exception as exc:
        results["error"] = str(exc)
    return results
