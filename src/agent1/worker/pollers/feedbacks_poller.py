"""Feedbacks API poller — checks for new complaints and Trustpilot reviews."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from agent1.common.logging import get_logger
from agent1.common.models import Event, EventSource, Priority
from agent1.integrations import FeedbacksClient, IntegrationError
from agent1.queue.dedup import is_duplicate, mark_processed
from agent1.queue.publisher import publish_event

log = get_logger(__name__)


async def poll_feedbacks() -> None:
    """Check feedbacks API for new complaints and low-star reviews.

    - New complaints (tasks with new count > 0) -> HIGH priority
    - Low-star Trustpilot reviews (stars <= 2, status = new) -> HIGH priority
    - Trustpilot review spikes (3+ new reviews) -> CRITICAL
    """
    client = FeedbacksClient()
    if not client.available:
        log.debug("feedbacks_poll_skipped", reason="no feedbacks API key configured")
        return

    log.debug("feedbacks_poll_started")

    try:
        async with client:
            await _poll_new_complaints(client)
            await _poll_trustpilot_reviews(client)
            await _check_trustpilot_spikes(client)
    except IntegrationError as exc:
        log.warning("feedbacks_poll_error", error=str(exc))
    except Exception as exc:
        log.warning("feedbacks_poll_error", error=str(exc))

    log.debug("feedbacks_poll_completed")


async def _poll_new_complaints(client: FeedbacksClient) -> None:
    """Check for new complaint tasks via GET /tasks."""
    data = await client.get_tasks()

    complaints = data.get("complaints", {})
    new_count = complaints.get("new", 0)

    if new_count <= 0:
        return

    # Dedup by hour to avoid repeat alerts for the same batch
    hour_key = datetime.now(UTC).strftime("%Y%m%d%H")
    dedup_id = f"complaint_batch:{hour_key}"

    if await is_duplicate("feedbacks", dedup_id):
        return

    event = Event(
        id=uuid.uuid4(),
        source=EventSource.FEEDBACKS,
        event_type="new_complaints",
        priority=Priority.HIGH,
        payload={
            "new_count": new_count,
            "message": f"{new_count} new complaint(s) awaiting review",
        },
        idempotency_key=f"feedbacks:complaint_batch:{hour_key}",
    )
    await publish_event(event)
    await mark_processed("feedbacks", dedup_id)
    log.info("feedbacks_complaints_event", new_count=new_count)


async def _poll_trustpilot_reviews(client: FeedbacksClient) -> None:
    """Check for new low-star Trustpilot reviews via GET /trustpilot/reviews."""
    data = await client.get_trustpilot_reviews(status="new", limit=50)

    reviews = data.get("reviews", [])

    for review in reviews:
        stars = review.get("stars", 5)
        if stars > 2:
            continue

        review_id = str(review.get("id", ""))
        dedup_id = f"trustpilot:{review_id}"

        if await is_duplicate("feedbacks", dedup_id):
            continue

        event = Event(
            id=uuid.uuid4(),
            source=EventSource.FEEDBACKS,
            event_type="trustpilot_review",
            priority=Priority.HIGH,
            payload={
                "review_id": review.get("id"),
                "trustpilot_id": review.get("trustpilotId"),
                "title": review.get("title"),
                "stars": stars,
                "reviewer_name": review.get("reviewerName"),
                "reviewer_country": review.get("reviewerCountry"),
                "is_defendable": review.get("isDefendable"),
            },
            idempotency_key=f"feedbacks:trustpilot:{review_id}",
        )
        await publish_event(event)
        await mark_processed("feedbacks", dedup_id)
        log.info("feedbacks_trustpilot_event", review_id=review_id, stars=stars)


async def _check_trustpilot_spikes(client: FeedbacksClient) -> None:
    """Detect Trustpilot review spikes: 3+ new reviews -> CRITICAL."""
    data = await client.get_trustpilot_summary()

    by_status = data.get("byStatus", {})
    new_count = by_status.get("new", 0)

    if new_count < 3:
        return

    hour_key = datetime.now(UTC).strftime("%Y%m%d%H")
    dedup_id = f"trustpilot_spike:{hour_key}"

    if await is_duplicate("feedbacks", dedup_id):
        return

    event = Event(
        id=uuid.uuid4(),
        source=EventSource.FEEDBACKS,
        event_type="trustpilot_spike",
        priority=Priority.CRITICAL,
        payload={
            "negative_review_count": new_count,
            "window": "recent",
            "message": f"{new_count} new Trustpilot reviews pending — possible spike",
        },
        idempotency_key=f"feedbacks:trustpilot_spike:{hour_key}",
    )
    await publish_event(event)
    await mark_processed("feedbacks", dedup_id)
    log.warning("trustpilot_spike_detected", count=new_count)
