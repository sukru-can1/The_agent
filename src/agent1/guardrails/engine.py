"""Programmatic guardrails engine -- checks before any action execution."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event
from agent1.guardrails.rate_limits import check_rate_limits
from agent1.guardrails.rules import check_business_rules

log = get_logger(__name__)


async def check_guardrails(event: Event, classification: ClassificationResult) -> bool:
    """Run all guardrail checks before allowing an action.

    Returns True if the event is safe to process, False if blocked.
    When blocked, creates a proposal and notifies the operator.
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
        await _notify_block(event, rule_result)
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


async def _notify_block(event: Event, rule_result: dict) -> None:
    """Create a guardrail_override proposal and notify via Chat."""
    from agent1.worker.loop import _extract_event_summary

    summary = _extract_event_summary(event)
    rule_name = rule_result.get("rule", "unknown")
    reason = rule_result.get("reason", "")

    # Create override proposal
    try:
        from agent1.intelligence.proposals import ProposalType, create_proposal
        await create_proposal(
            type=ProposalType.GUARDRAIL_OVERRIDE,
            title=f"Blocked: {event.source.value} — {rule_name}",
            description=(
                f"Event {event.id} was blocked by guardrail rule '{rule_name}'.\n"
                f"Reason: {reason}\n\n"
                f"Event: {summary}"
            ),
            config={"event_id": str(event.id), "rule_name": rule_name},
            confidence=0.0,
            related_event_ids=[event.id],
        )
    except Exception:
        log.exception("guardrail_proposal_creation_failed")

    # Notify via Chat (best effort)
    try:
        from agent1.tools.google_chat import GChatPostMessageTool
        chat = GChatPostMessageTool()
        await chat.execute(
            space="alerts",
            message=(
                f"**Event blocked by guardrails**\n"
                f"**Rule:** {rule_name}\n"
                f"**Reason:** {reason}\n"
                f"**Event:** {summary}\n\n"
                f"Reply `override {str(event.id)[:8]}` or approve in Dashboard."
            ),
        )
    except Exception:
        log.warning("guardrail_chat_notification_failed")
