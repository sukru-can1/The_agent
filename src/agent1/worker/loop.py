"""Event processing pipeline: classify → plan → guardrails → reason+tools → store."""

from __future__ import annotations

import json
import time

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import ActionLog, ClassificationResult, Event, EventSource
from agent1.common.observability import trace_generation, trace_operation
from agent1.common.settings import get_settings

log = get_logger(__name__)


def _extract_event_summary(event: Event) -> str:
    """Build a short human-readable summary from event payload."""
    p = event.payload
    src = event.source.value
    if src == "freshdesk":
        tid = p.get("ticket_id", "")
        subj = p.get("subject", "")
        return f"Freshdesk Ticket #{tid} — {subj}" if tid else subj or event.event_type
    if src == "gmail":
        sender = p.get("from_address") or p.get("sender", "")
        subj = p.get("subject", "")
        return f"Email from {sender}: {subj}" if sender else subj or event.event_type
    if src == "gchat":
        sender = p.get("sender", "")
        text = str(p.get("text", ""))[:80]
        return f'{sender}: "{text}"' if sender else text or event.event_type
    if src == "starinfinity":
        board = p.get("board_name", "")
        task = p.get("task_title", "")
        return f"Board: {board} — {task}" if board else task or event.event_type
    if src == "feedbacks":
        email = p.get("customer_email", "")
        rating = p.get("rating", "")
        return f"{email} — Rating: {rating}" if email else event.event_type
    if src == "dashboard":
        text = str(p.get("text", ""))[:120]
        return f"Dashboard: {text}" if text else event.event_type
    if src == "gdrive":
        fname = p.get("file_name", "")
        change = p.get("change_type", "changed")
        who = p.get("modified_by", "")
        return f"Drive: {fname} {change} by {who}" if fname else event.event_type
    return event.event_type


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

    # Step 1.5: Context enrichment (NEW)
    enriched_context = None
    try:
        from agent1.intelligence.context_engine import enrich

        enriched_context = await enrich(event, classification)
        if enriched_context and enriched_context.token_estimate > 0:
            log.info(
                "context_enriched",
                event_id=str(event.id),
                tokens=enriched_context.token_estimate,
                incidents=len(enriched_context.similar_incidents),
                knowledge=len(enriched_context.relevant_knowledge),
            )
    except Exception:
        log.warning("context_enrichment_failed", event_id=str(event.id))

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
                details={
                    "event_type": event.event_type,
                    "classification": classification.model_dump(),
                },
                outcome="blocked",
            ),
            event_id=str(event.id),
        )
        return

    # Step 4: Session handling + Reason and execute tools
    from agent1.reasoning.engine import reason_and_act
    from agent1.sessions import (
        acquire_session_lock,
        get_or_create_session,
        load_session_history,
        release_session_lock,
        resolve_session_key,
        store_session_messages,
    )

    session_key = resolve_session_key(event)
    session_id = None
    session_locked = False
    conversation_history: list[dict] | None = None

    try:
        if session_key:
            session_locked = await acquire_session_lock(session_key)
            if session_locked:
                platform = event.source.value
                user_id = event.payload.get("sender_email", "") or event.payload.get("sender", "")
                user_name = event.payload.get("sender", "")
                session_id, is_new = await get_or_create_session(
                    session_key, platform, user_id, user_name,
                )
                if not is_new:
                    conversation_history = await load_session_history(session_id)
                    if conversation_history:
                        log.info(
                            "session_history_loaded",
                            event_id=str(event.id),
                            session_id=str(session_id),
                            history_messages=len(conversation_history),
                        )
            else:
                log.warning("session_lock_failed_proceeding_without", event_id=str(event.id))

        result = await reason_and_act(
            event, classification, plan, enriched_context, conversation_history,
        )

        # Store messages in session after successful reasoning
        if session_id and isinstance(result, dict):
            try:
                user_text = event.payload.get("text", "")
                assistant_text = result.get("result", "")
                await store_session_messages(session_id, user_text, assistant_text, event.id)
            except Exception:
                log.exception("session_store_failed", event_id=str(event.id))
    finally:
        if session_locked and session_key:
            await release_session_lock(session_key)

    # Step 4b: Safety net — if Chat event and LLM didn't post a reply via tools,
    # post the reasoning result as a Chat message.
    # Skip for: dashboard events, polled DMs (agent should notify Sukru, not reply in
    # someone else's DM space), and events where the LLM already replied via tools.
    is_polled_dm = event.payload.get("polled_dm", False)
    already_replied = isinstance(result, dict) and any(
        t in result.get("tools_called", [])
        for t in ("gchat_reply_as_agent", "gchat_post_message")
    )
    if (
        event.source == EventSource.GCHAT
        and classification.needs_response
        and isinstance(result, dict)
        and result.get("result")
        and not already_replied
        and not is_polled_dm
    ):
        try:
            from agent1.tools.google_chat import GChatReplyAsAgentTool

            space = event.payload.get("space", "")
            thread = event.payload.get("thread", "")
            if space:
                chat = GChatReplyAsAgentTool()
                await chat.execute(space=space, thread_key=thread, message=result["result"])
                log.info("chat_fallback_reply_sent", event_id=str(event.id))
        except Exception as exc:
            log.warning("chat_fallback_reply_failed", error=str(exc))

    # Step 4c: For dashboard-sourced events, store conversation
    if event.source == EventSource.DASHBOARD and isinstance(result, dict):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO conversations (platform, user_id, user_name, message_in, message_out, context)
                    VALUES ('dashboard', $1, $2, $3, $4, $5)
                    """,
                    event.payload.get("sender_email", "admin"),
                    event.payload.get("sender", "Dashboard"),
                    event.payload.get("text", ""),
                    result.get("result", "")[:5000],
                    json.dumps(
                        {"event_id": str(event.id), "tools_called": result.get("tools_called", [])}
                    ),
                )
        except Exception as exc:
            log.warning("dashboard_conversation_store_failed", error=str(exc))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Step 5: Log the action (enriched details)
    agent_response = ""
    tools_called: list[str] = []
    if isinstance(result, dict):
        agent_response = str(result.get("result", ""))[:300]
        tools_called = result.get("tools_called", [])

    await _log_action(
        ActionLog(
            system=event.source.value,
            action_type=f"processed_{event.event_type}",
            details={
                "event_type": event.event_type,
                "classification": classification.model_dump(),
                "result_summary": str(result)[:500] if result else None,
                "event_summary": _extract_event_summary(event),
                "tools_called": tools_called,
                "agent_response": agent_response,
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

    # Step 5.5: Post-action intelligence (NEW)
    try:
        from agent1.intelligence.analytics_engine import check_correlations, track_event

        await track_event(event.source.value, event.event_type, classification.category)

        correlations = await check_correlations(event.source.value, event.event_type)
        if correlations:
            try:
                from agent1.tools.google_chat import GChatPostMessageTool

                chat = GChatPostMessageTool()
                for c in correlations:
                    await chat.execute(
                        space="alerts",
                        message=f"**Cross-system pattern:** {c['summary']}",
                    )
            except Exception:
                log.warning("correlation_alert_failed")
    except Exception:
        log.warning("post_action_intel_failed", event_id=str(event.id))

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
    """Auto-respond to simple Chat questions using flash-tier model.

    Returns True if handled, False to fall through to full reasoning.
    """
    from agent1.reasoning.providers import get_provider, provider_available
    from agent1.reasoning.router import get_flash_model

    if not await provider_available():
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
                like_clauses = " OR ".join(
                    f"LOWER(content) LIKE '%' || ${i + 1} || '%'" for i in range(len(words))
                )
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

    # Quick flash-tier response (fastest/cheapest)
    try:
        flash_model = await get_flash_model()
        provider = await get_provider()
        response = await provider.generate(
            model=flash_model,
            messages=[{"role": "user", "content": text}],
            max_tokens=500,
            system=(
                "You are The Agent1, GLAMIRA's operations assistant. "
                "You were built by the GLAMIRA tech team to help with operations. "
                "Stay in character at all times — you ARE The Agent1. "
                "Answer questions briefly and helpfully. "
                "If you don't know something specific about GLAMIRA operations, say so."
                + context_str
            ),
        )

        answer = (response.text or "").strip()
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens

        trace_generation(
            name="auto_response",
            model=flash_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

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
                model_used=flash_model,
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

    # Check feedbacks via API if available
    complaints_24h = 0
    try:
        from agent1.integrations import FeedbacksClient

        fb = FeedbacksClient()
        if fb.available:
            async with fb:
                tasks_data = await fb.get_tasks()
            complaints_24h = tasks_data.get("complaints", {}).get("new", 0)
    except Exception:
        pass

    # Build summary message
    title = "Morning Brief" if is_morning else "Daily Summary"
    sources_str = (
        ", ".join(f"{r['source']}: {r['count']}" for r in top_sources) if top_sources else "none"
    )

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
            details={
                "events_24h": events_24h,
                "pending_drafts": pending_drafts,
                "complaints": complaints_24h,
            },
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
