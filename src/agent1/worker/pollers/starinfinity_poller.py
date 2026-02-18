"""StarInfinity poller — checks for overdue tasks."""

from __future__ import annotations

from agent1.common.logging import get_logger

log = get_logger(__name__)


async def poll_starinfinity() -> None:
    """Check StarInfinity for overdue tasks.

    Full implementation in Phase 3 — API details TBD.
    """
    log.debug("starinfinity_poll_started")
    # TODO: Phase 3 — investigate StarInfinity API
    log.debug("starinfinity_poll_completed")
