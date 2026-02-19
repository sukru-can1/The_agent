"""Event processing pipeline: classify → plan → guardrails → reason+tools → store."""

from __future__ import annotations

import json
import time

import anthropic

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import ActionLog, ClassificationResult, Event, EventSource
from agent1.common.observability import trace_operation
from agent1.common.redis_client import get_redis
from agent1.common.settings import get_settings

log = get_logger(__name__)


async def _is_paused() -> bool:
    """Check if the queue is paused."""
    redis = await get_redis()
    return await redis.exists("agent1:queue:paused") == 1


async def _log_action(action: ActionLog, event_id: str | None = None) -> None:
    """Store an action in the audit log."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO actions_log (system, action_type, details, outcome,
                                     model_used, input_tokens, output_tokens, latency_ms, event_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            action.system,
            action.action_type,
            json.dumps(action.details),
            action.outcome,
            action.model_used,
            action.input_tokens,
            action.output_tokens,
            action.latency_ms,
            event_id,
        )


@trace_operation("process_event")
async def process_event(event: Event) -> None:
    """Process a single event through the full pipeline."""
    if await _is_paused():
        log.info("queue_paused_skipping", event_id=str(event.id))
        # Re-enqueue by raising so consumer will nack
        raise RuntimeError("Queue is paused")

    start = time.monotonic()

    log.info(
        "processing_event",
        event_id=str(event.id),
        source=event.source.value,
        event_type=event.event_type,
        priority=event.priority.value,
    )

    # Step 1: Classify the event
    from agent1.reasoning.classifier import classify_event

    classification = await classify_event(event)

    log.info(
        "event_classified",
        event_id=str(event.id),
        category=classification.category,
        urgency=classification.urgency.value,
        complexity=classification.complexity.value,
    )

    # Step 1b: Handle teachable rules immediately
    if classification.is_teachable_rule and event.source == EventSource.GCHAT:
        await _handle_teachable_rule(event, start)
        return

    # Step 1c: Handle scheduled summaries
    if event.event_type in ("morning_brief", "daily_summary"):
        await _handle_summary_event(event, start)
        return

    # Step 1c: Auto-respond to simple Chat questions
    if (
        event.source == EventSource.GCHAT
        and event.event_type == "chat_message"
        and classification.complexity == "simple"
        and classification.needs_response
    ):
        handled = await _handle_chat_auto_response(event, classification, start)
        if handled:
            return

    # Step 2: Plan (skip for simple events)
    plan = None
    if classification.complexity != "simple":
        from agent1.worker.planner import create_plan

        plan = await create_plan(event, classification)

    # Step 3: Guardrails check
    from agent1.guardrails.engine import check_guardrails

    guardrails_ok = await check_guardrails(event, classification)
    if not guardrails_ok:
        log.warning("guardrails_blocked", event_id=str(event.id))
        await _log_action(
            ActionLog(
                system=event.source.value,
                action_type="guardrails_blocked",
                details={"event_type": event.event_type, "classification": classification.model_dump()},
                outcome="blocked",
            ),
            event_id=str(event.id),
        )
        return

    # Step 4: Reason and execute tools
    from agent1.reasoning.engine import reason_and_act

    result = await reason_and_act(event, classification, plan)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Step 5: Log the action
    await _log_action(
        ActionLog(
            system=event.source.value,
            action_type=f"processed_{event.event_type}",
            details={
                "event_type": event.event_type,
                "classification": classification.model_dump(),
                "result_summary": str(result)[:500] if result else None,
            },
            outcome="success",
            model_used=result.get("model_used", "") if isinstance(result, dict) else "",
            input_tokens=result.get("input_tokens", 0) if isinstance(result, dict) else 0,
            output_tokens=result.get("output_tokens", 0) if isinstance(result, dict) else 0,
            latency_ms=elapsed_ms,
        ),
        event_id=str(event.id),
    )

    # Update event status in Postgres
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET status = 'completed', processed_at = NOW() WHERE id = $1",
            event.id,
        )

    log.info(
        "event_processed",
        event_id=str(event.id),
        latency_ms=elapsed_ms,
    )


async def _handle_teachable_rule(event: Event, start: float) -> None:
    """Handle a teachable rule from Google Chat — store as knowledge."""
    text = event.payload.get("text", "")
    sender = event.payload.get("sender", "")
    space = event.payload.get("space", "")

    # Store in knowledge table
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO knowledge (category, content, source, active)
            VALUES ('taught_rule', $1, $2, true)
            """,
            text,
            f"taught_by:{sender}",
        )

    # Acknowledge via Chat
    try:
        from agent1.tools.google_chat import GChatReplyAsAgentTool

        chat = GChatReplyAsAgentTool()
        await chat.execute(
            space=space,
            thread_key=event.payload.get("thread", ""),
            message=f"Got it. I've learned this rule and will follow it going forward:\n> {text}",
        )
    except Exception as exc:
        log.warning("teach_ack_failed", error=str(exc))

    elapsed_ms = int((time.monotonic() - start) * 1000)
    await _log_action(
        ActionLog(
            system="gchat",
            action_type="teachable_rule_stored",
            details={"text": text, "sender": sender},
            outcome="success",
            latency_ms=elapsed_ms,
        ),
        event_id=str(event.id),
    )

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET status = 'completed', processed_at = NOW() WHERE id = $1",
            event.id,
        )

    log.info("teachable_rule_stored", event_id=str(event.id), sender=sender)


async def _handle_chat_auto_response(
    event: Event, classification: ClassificationResult, start: float
) -> bool:
    """Auto-respond to simple Chat questions using Haiku.

    Returns True if handled, False to fall through to full reasoning.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return False

    text = event.payload.get("text", "").strip()
    space = event.payload.get("space", "")
    thread = event.payload.get("thread", "")

    if not text:
        log.warning("auto_response_empty_text", event_id=str(event.id))
        return False

    # Search knowledge for context (plain text search — no pgvector needed)
    context_str = ""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Simple keyword search in knowledge base
            words = [w for w in text.lower().split() if len(w) > 3][:5]
            if words:
                like_clauses = " OR ".join(f"LOWER(content) LIKE '%' || ${i+1} || '%'" for i in range(len(words)))
                rows = await conn.fetch(
                    f"""
                    SELECT content FROM knowledge
                    WHERE active = true AND ({like_clauses})
                    LIMIT 3
                    """,
                    *words,
                )
                if rows:
                    context_str = "\n\nRelevant knowledge:\n" + "\n".join(
                        f"- {r['content']}" for r in rows
                    )
    except Exception:
        pass

    # Quick Haiku response
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.claude_model_haiku,
            max_tokens=500,
            system=(
                "You are The Agent1, GLAMIRA's operations assistant. "
                "Answer the question briefly and helpfully. "
                "If you're not confident in the answer, say so."
                + context_str
            ),
            messages=[{"role": "user", "content": text}],
        )

        answer = response.content[0].text.strip()
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # Post reply via Chat
        from agent1.tools.google_chat import GChatReplyAsAgentTool

        chat = GChatReplyAsAgentTool()
        await chat.execute(space=space, thread_key=thread, message=answer)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        await _log_action(
            ActionLog(
                system="gchat",
                action_type="auto_response",
                details={"question": text[:200], "answer": answer[:200]},
                outcome="success",
                model_used=settings.claude_model_haiku,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed_ms,
            ),
            event_id=str(event.id),
        )

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE events SET status = 'completed', processed_at = NOW() WHERE id = $1",
                event.id,
            )

        log.info("chat_auto_response_sent", event_id=str(event.id))
        return True

    except Exception:
        log.exception("auto_response_failed", event_id=str(event.id))
        return False


async def _handle_summary_event(event: Event, start: float) -> None:
    """Handle morning_brief and daily_summary events by aggregating stats and posting to Chat."""
    settings = get_settings()
    is_morning = event.event_type == "morning_brief"
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Events in last 24h
        events_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )
        failed_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE status = 'failed' AND created_at >= NOW() - INTERVAL '24 hours'"
        )

        # Pending drafts
        pending_drafts = await conn.fetchval(
            "SELECT COUNT(*) FROM email_drafts WHERE status = 'pending'"
        )

        # Drafts sent in last 24h
        sent_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM email_drafts WHERE status = 'sent' AND sent_at >= NOW() - INTERVAL '24 hours'"
        )

        # DLQ unresolved
        dlq_count = await conn.fetchval(
            "SELECT COUNT(*) FROM dead_letter_events WHERE resolved_at IS NULL"
        )

        # Top event sources
        top_sources = await conn.fetch(
            """
            SELECT source, COUNT(*) AS count
            FROM events
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY source
            ORDER BY count DESC
            LIMIT 5
            """
        )

    # Check feedbacks if available
    complaints_24h = 0
    try:
        if settings.feedbacks_database_url:
            import asyncpg

            fconn = await asyncpg.connect(settings.feedbacks_database_url)
            try:
                complaints_24h = await fconn.fetchval(
                    """
                    SELECT COUNT(*) FROM "SurveyResponse"
                    WHERE sentiment = 'negative'
                      AND "createdAt" >= NOW() - INTERVAL '24 hours'
                    """
                ) or 0
            finally:
                await fconn.close()
    except Exception:
        pass

    # Build summary message
    title = "Morning Brief" if is_morning else "Daily Summary"
    sources_str = ", ".join(f"{r['source']}: {r['count']}" for r in top_sources) if top_sources else "none"

    summary = (
        f"**{title}** ({event.payload.get('date', 'today')})\n\n"
        f"**Events (24h):** {events_24h} processed, {failed_24h} failed\n"
        f"**Email Drafts:** {pending_drafts} pending, {sent_24h} sent\n"
        f"**DLQ:** {dlq_count} unresolved\n"
        f"**Customer Complaints (24h):** {complaints_24h}\n"
        f"**Top Sources:** {sources_str}"
    )

    if dlq_count > 0:
        summary += f"\n\n:warning: {dlq_count} events in dead-letter queue need attention."
    if pending_drafts > 3:
        summary += f"\n\n:warning: {pending_drafts} drafts awaiting approval."

    # Post to Chat
    try:
        from agent1.tools.google_chat import GChatPostMessageTool

        chat = GChatPostMessageTool()
        space = "summary" if not is_morning else "alerts"
        await chat.execute(space=space, message=summary)
    except Exception as exc:
        log.warning("summary_chat_post_failed", error=str(exc))

    elapsed_ms = int((time.monotonic() - start) * 1000)
    await _log_action(
        ActionLog(
            system="scheduler",
            action_type=event.event_type,
            details={"events_24h": events_24h, "pending_drafts": pending_drafts, "complaints": complaints_24h},
            outcome="success",
            latency_ms=elapsed_ms,
        ),
        event_id=str(event.id),
    )

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET status = 'completed', processed_at = NOW() WHERE id = $1",
            event.id,
        )

    log.info("summary_event_processed", event_type=event.event_type)
