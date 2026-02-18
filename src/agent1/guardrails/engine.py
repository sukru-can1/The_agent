"""Programmatic guardrails engine — checks before any action execution."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event
from agent1.guardrails.rules import check_business_rules
from agent1.guardrails.rate_limits import check_rate_limits

log = get_logger(__name__)


async def check_guardrails(event: Event, classification: ClassificationResult) -> bool:
    """Run all guardrail checks before allowing an action.

    Returns True if the event is safe to process, False if blocked.
    """
    # Check business rules
    rule_result = await check_business_rules(event, classification)
    if not rule_result["allowed"]:
        log.warning(
            "guardrails_rule_blocked",
            event_id=str(event.id),
            rule=rule_result["rule"],
            reason=rule_result["reason"],
        )
        return False

    # Check rate limits
    rate_result = await check_rate_limits(event)
    if not rate_result["allowed"]:
        log.warning(
            "guardrails_rate_limited",
            event_id=str(event.id),
            limit=rate_result["limit"],
        )
        return False

    return True
