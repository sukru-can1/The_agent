"""Event processing pipeline: classify → plan → guardrails → reason+tools → store."""

from __future__ import annotations

import json
import time

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.models import ActionLog, Event
from agent1.common.observability import trace_operation
from agent1.common.redis_client import get_redis

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
