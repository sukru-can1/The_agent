"""Feedbacks DB poller — checks for new complaints and Trustpilot reviews."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from agent1.common.db import get_feedbacks_pool
from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def poll_feedbacks() -> None:
    """Check feedbacks DB for new complaints and low-star reviews.

    - New complaints (taskStatus = 'new', taskType = 'complaint') -> HIGH priority
    - Low-star Trustpilot reviews (stars <= 2, status = 'new') -> HIGH priority
    - Trustpilot review spikes (3+ negative in 1 hour) -> CRITICAL
    """
    pool = await get_feedbacks_pool()
    if pool is None:
        log.debug("feedbacks_poll_skipped", reason="no feedbacks DB configured")
        return

    log.debug("feedbacks_poll_started")

    try:
        await _poll_new_complaints(pool)
        await _poll_trustpilot_reviews(pool)
        await _check_trustpilot_spikes(pool)
    except Exception as exc:
        log.warning("feedbacks_poll_error", error=str(exc))

    log.debug("feedbacks_poll_completed")


async def _poll_new_complaints(pool) -> None:
    """Check for new complaint survey responses."""
    since = datetime.now(UTC) - timedelta(minutes=15)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, "customerEmail", "customerName", "countryCode",
                   "freshdeskTicketId", "createdAt"
            FROM "SurveyResponse"
            WHERE "taskType" = 'complaint'
              AND "taskStatus" = 'new'
              AND "createdAt" > $1
            ORDER BY "createdAt" DESC
            LIMIT 50
            """,
            since,
        )

    for row in rows:
        dedup_key = f"feedbacks:complaint:{row['id']}"
        if await is_duplicate(dedup_key):
            continue

        event = Event(
            id=uuid.uuid4(),
            source=EventSource.FEEDBACKS,
            event_type="new_complaint",
            priority=Priority.HIGH,
            payload={
                "response_id": row["id"],
                "customer_email": row["customerEmail"],
                "customer_name": row["customerName"],
                "country_code": row["countryCode"],
                "freshdesk_ticket_id": row["freshdeskTicketId"],
            },
            idempotency_key=dedup_key,
        )
        await publish_event(event)
        await mark_processed(dedup_key)
        log.info("feedbacks_complaint_event", response_id=row["id"])


async def _poll_trustpilot_reviews(pool) -> None:
    """Check for new low-star Trustpilot reviews."""
    since = datetime.now(UTC) - timedelta(minutes=15)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, "trustpilotId", title, stars, "reviewerName",
                   "reviewerCountry", "isDefendable", "taskStatus",
                   "reviewCreatedAt"
            FROM "TrustpilotReview"
            WHERE stars <= 2
              AND "taskStatus" = 'new'
              AND "reviewCreatedAt" > $1
            ORDER BY "reviewCreatedAt" DESC
            LIMIT 50
            """,
            since,
        )

    for row in rows:
        dedup_key = f"feedbacks:trustpilot:{row['id']}"
        if await is_duplicate(dedup_key):
            continue

        event = Event(
            id=uuid.uuid4(),
            source=EventSource.FEEDBACKS,
            event_type="trustpilot_review",
            priority=Priority.HIGH,
            payload={
                "review_id": row["id"],
                "trustpilot_id": row["trustpilotId"],
                "title": row["title"],
                "stars": row["stars"],
                "reviewer_name": row["reviewerName"],
                "reviewer_country": row["reviewerCountry"],
                "is_defendable": row["isDefendable"],
            },
            idempotency_key=dedup_key,
        )
        await publish_event(event)
        await mark_processed(dedup_key)
        log.info("feedbacks_trustpilot_event", review_id=row["id"], stars=row["stars"])


async def _check_trustpilot_spikes(pool) -> None:
    """Detect Trustpilot review spikes: 3+ negative reviews in 1 hour."""
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM "TrustpilotReview"
            WHERE stars <= 2
              AND "reviewCreatedAt" > $1
            """,
            one_hour_ago,
        )

    if count is not None and count >= 3:
        dedup_key = f"feedbacks:trustpilot_spike:{one_hour_ago.strftime('%Y%m%d%H')}"
        if await is_duplicate(dedup_key):
            return

        event = Event(
            id=uuid.uuid4(),
            source=EventSource.FEEDBACKS,
            event_type="trustpilot_spike",
            priority=Priority.CRITICAL,
            payload={
                "negative_review_count": count,
                "window": "1 hour",
                "message": f"{count} negative Trustpilot reviews in the last hour",
            },
            idempotency_key=dedup_key,
        )
        await publish_event(event)
        await mark_processed(dedup_key)
        log.warning("trustpilot_spike_detected", count=count)
