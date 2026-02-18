"""Feedbacks DB poller — checks for new complaints and Trustpilot reviews."""

from __future__ import annotations

from agent1.common.logging import get_logger

log = get_logger(__name__)


async def poll_feedbacks() -> None:
    """Check feedbacks DB for new complaints and low-star reviews.

    Full implementation in Phase 2:
    - New complaints (taskStatus = 'new', taskType = 'complaint') → HIGH priority
    - Low-star Trustpilot reviews (stars <= 2, status = 'new') → HIGH priority
    - Trustpilot review spikes (3+ negative in 1 hour) → CRITICAL
    """
    log.debug("feedbacks_poll_started")
    # TODO: Phase 2 — query feedbacks DB read-only
    log.debug("feedbacks_poll_completed")
