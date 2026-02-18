"""Freshdesk poller — checks for new/updated tickets."""

from __future__ import annotations

from agent1.common.logging import get_logger

log = get_logger(__name__)


async def poll_freshdesk() -> None:
    """Check Freshdesk for new or updated tickets.

    Full implementation in Phase 2 — will use Freshdesk API.
    """
    log.debug("freshdesk_poll_started")
    # TODO: Phase 2 — fetch tickets updated since last check
    log.debug("freshdesk_poll_completed")
