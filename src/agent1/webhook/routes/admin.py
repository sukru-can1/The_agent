"""Admin API routes for monitoring, config, and DLQ management."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.redis_client import get_redis
from agent1.common.settings import get_settings
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

        pending_proposals = 0
        try:
            pending_proposals = await conn.fetchval(
                "SELECT COUNT(*) FROM proposals WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > NOW())"
            ) or 0
        except Exception:
            pass  # Table may not exist yet

    is_paused = await redis.exists("agent1:queue:paused") == 1

    return {
        "queue_depth": queue_depth,
        "pending_drafts": pending_drafts,
        "dlq_count": dlq_count,
        "pending_proposals": pending_proposals,
        "is_paused": is_paused,
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
            SELECT id, source, event_type, priority, status, created_at, error, payload
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
    edited_body: str | None = None


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

            # Qualitative analysis (async, best effort)
            try:
                import asyncio

                from agent1.intelligence.feedback_intel import analyze_edit
                asyncio.create_task(analyze_edit(
                    draft_id=draft_id,
                    original=draft["draft_body"],
                    edited=body.edited_body,
                    sender_domain=_extract_domain(draft["from_address"]),
                    category=draft["classification"],
                ))
            except Exception as exc:
                log.warning("feedback_intel_trigger_failed", error=str(exc))
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

    # Qualitative rejection analysis (async, best effort)
    try:
        pool2 = await get_pool()
        async with pool2.acquire() as conn2:
            draft_row = await conn2.fetchrow(
                "SELECT draft_body, classification FROM email_drafts WHERE id = $1",
                draft_id,
            )
        if draft_row:
            import asyncio

            from agent1.intelligence.feedback_intel import analyze_rejection
            asyncio.create_task(analyze_rejection(
                draft_id=draft_id,
                draft_body=draft_row["draft_body"],
                rejection_reason=None,
            ))
    except Exception as exc:
        log.warning("rejection_intel_trigger_failed", error=str(exc))

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

    # Compute estimated costs per model (per 1M tokens)
    cost_map = {
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
        "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
        "gemini-3-pro": {"input": 1.25, "output": 10.0},
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


class InjectEventBody(BaseModel):
    source: str = "gchat"
    event_type: str = "chat_message"
    text: str
    space: str = ""
    thread: str = ""


@router.post("/inject-event")
async def inject_event(body: InjectEventBody):
    """Inject an event into the queue. Use source='dashboard' for dashboard chat."""
    from agent1.common.models import Event, EventSource, Priority
    from agent1.common.settings import get_settings
    from agent1.queue.publisher import publish_event

    settings = get_settings()

    if body.source == "dashboard":
        event = Event(
            source=EventSource.DASHBOARD,
            event_type=body.event_type,
            priority=Priority.HIGH,
            payload={
                "text": body.text,
                "sender": "Dashboard",
                "sender_email": settings.gchat_user_email,
            },
        )
    else:
        space = body.space or settings.gchat_dm_sukru or ""
        event = Event(
            source=EventSource(body.source),
            event_type=body.event_type,
            priority=Priority.HIGH,
            payload={
                "text": body.text,
                "space": space,
                "thread": body.thread,
                "sender": "Admin (test)",
                "sender_email": settings.gchat_user_email,
            },
        )

    await publish_event(event)
    log.info("event_injected", event_id=str(event.id), source=body.source, text=body.text[:80])
    return {"status": "published", "event_id": str(event.id)}


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
async def list_actions(limit: int = 50, event_id: str | None = None):
    """List recent agent actions (audit log). Optionally filter by event_id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if event_id:
            rows = await conn.fetch(
                """
                SELECT id, timestamp, system, action_type, outcome,
                       model_used, input_tokens, output_tokens, latency_ms, details, event_id
                FROM actions_log
                WHERE event_id = $1
                ORDER BY timestamp DESC
                """,
                event_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, timestamp, system, action_type, outcome,
                       model_used, input_tokens, output_tokens, latency_ms, details, event_id
                FROM actions_log
                ORDER BY timestamp DESC
                LIMIT $1
                """,
                limit,
            )
    return [dict(r) for r in rows]


@router.get("/actions/{action_id}")
async def get_action(action_id: int):
    """Get a single action with full details and joined event data."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT a.id, a.timestamp, a.system, a.action_type, a.outcome,
                   a.model_used, a.input_tokens, a.output_tokens, a.latency_ms,
                   a.details, a.event_id,
                   e.source AS event_source, e.event_type AS event_event_type,
                   e.priority AS event_priority, e.payload AS event_payload,
                   e.status AS event_status, e.created_at AS event_created_at
            FROM actions_log a
            LEFT JOIN events e ON e.id::text = a.event_id
            WHERE a.id = $1
            """,
            action_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    return dict(row)


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    """Get a single event by UUID (for polling completion status)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, source, event_type, priority, status, created_at, processed_at, error, payload
            FROM events
            WHERE id = $1
            """,
            event_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return dict(row)


@router.get("/chat-history")
async def chat_history(limit: int = 20):
    """Recent dashboard conversations from the conversations table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, timestamp, user_name, message_in, message_out, context
            FROM conversations
            WHERE platform = 'dashboard'
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


class StoreKnowledgeBody(BaseModel):
    category: str = "operator_instruction"
    content: str
    source: str = "dashboard"


@router.post("/knowledge")
async def store_knowledge_entry(body: StoreKnowledgeBody):
    """Store an operator instruction or comment as knowledge."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO knowledge (category, content, source, confidence)
               VALUES ($1, $2, $3, 1.0) RETURNING id, created_at""",
            body.category,
            body.content,
            body.source,
        )
    log.info("knowledge_stored", id=row["id"], category=body.category)
    return {"id": row["id"], "created_at": str(row["created_at"])}


@router.get("/integrations")
async def list_integrations():
    """List configured integrations and their status."""
    from agent1.integrations import FeedbacksClient, FreshdeskClient, StarInfinityClient

    settings = get_settings()
    return [
        {"id": "gmail", "name": "Gmail", "active": bool(settings.google_refresh_token)},
        {"id": "gchat", "name": "Google Chat", "active": bool(settings.gchat_space_alerts)},
        {"id": "freshdesk", "name": "Freshdesk", "active": FreshdeskClient().available},
        {"id": "starinfinity", "name": "StarInfinity", "active": StarInfinityClient().available},
        {"id": "feedbacks", "name": "Feedbacks API", "active": FeedbacksClient().available},
        {"id": "voyage", "name": "Voyage AI", "active": bool(settings.voyage_api_key)},
        {"id": "langfuse", "name": "LangFuse", "active": bool(settings.langfuse_public_key)},
        {"id": "mcp", "name": "MCP Tools", "active": settings.dynamic_tools_enabled},
    ]


# --- Proposals ---


@router.get("/proposals")
async def list_proposals(status: str = "pending", type: str | None = None, limit: int = 20):
    """List proposals by status, optionally filtered by type."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if type:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at, reviewed_at, reviewed_by
                FROM proposals
                WHERE status = $1 AND type = $2
                ORDER BY confidence DESC, created_at DESC
                LIMIT $3
                """,
                status, type, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at, reviewed_at, reviewed_by
                FROM proposals
                WHERE status = $1
                ORDER BY confidence DESC, created_at DESC
                LIMIT $2
                """,
                status, limit,
            )
    return [dict(r) for r in rows]


@router.get("/proposals/stats")
async def proposal_stats():
    """Get proposal counts by type and status."""
    from agent1.intelligence.proposals import get_proposal_stats
    return await get_proposal_stats()


@router.get("/proposals/{proposal_id}")
async def get_proposal_detail(proposal_id: str):
    """Get a single proposal by UUID."""
    from agent1.intelligence.proposals import get_proposal
    proposal = await get_proposal(UUID(proposal_id))
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


class ProposalApproveBody(BaseModel):
    notes: str | None = None
    edited_description: str | None = None


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal_endpoint(proposal_id: str, body: ProposalApproveBody = ProposalApproveBody()):
    """Approve a pending proposal."""
    from agent1.intelligence.proposals import approve_proposal
    success = await approve_proposal(
        UUID(proposal_id),
        notes=body.notes,
        edited_description=body.edited_description,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found or not pending")
    return {"status": "approved", "proposal_id": proposal_id}


class ProposalRejectBody(BaseModel):
    reason: str | None = None


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal_endpoint(proposal_id: str, body: ProposalRejectBody = ProposalRejectBody()):
    """Reject a pending proposal."""
    from agent1.intelligence.proposals import reject_proposal
    success = await reject_proposal(UUID(proposal_id), reason=body.reason)
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found or not pending")
    return {"status": "rejected", "proposal_id": proposal_id}


# --- Solutions ---


@router.get("/solutions")
async def list_solutions(type: str | None = None):
    """List active solutions (tools, automations, scripts)."""
    from agent1.intelligence.solutions.factory import get_active_solutions
    return await get_active_solutions(type)

