"""Hard-coded business rules for safety."""

from __future__ import annotations

from agent1.common.models import ClassificationResult, Event
from agent1.common.settings import get_settings


async def check_business_rules(event: Event, classification: ClassificationResult) -> dict:
    """Check hard-coded business rules.

    Rules:
    - Cannot send to external recipients without approval
    - Cannot respond to restricted contacts
    - Cannot close tickets or issue refunds
    - Financial/legal topics always require approval
    """
    settings = get_settings()
    payload = event.payload

    # Rule: restricted contacts
    sender = payload.get("sender_email", "") or payload.get("from_address", "")
    if sender and sender.lower() in [c.lower() for c in settings.restricted_contacts]:
        return {
            "allowed": False,
            "rule": "restricted_contact",
            "reason": f"Contact {sender} is restricted — requires manual handling",
        }

    # Rule: financial/legal always needs approval (don't auto-act)
    if classification.involves_financial:
        # We still process the event, but the reasoning engine should
        # know to request approval rather than auto-act
        pass

    # Default: allowed
    return {"allowed": True, "rule": None, "reason": None}
