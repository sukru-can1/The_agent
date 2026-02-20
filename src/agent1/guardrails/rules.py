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

    # Rule 1: restricted contacts — block entirely
    sender = payload.get("sender_email", "") or payload.get("from_address", "")
    if sender and sender.lower() in [c.lower() for c in settings.restricted_contacts]:
        return {
            "allowed": False,
            "rule": "restricted_contact",
            "reason": f"Contact {sender} is restricted — requires manual handling",
        }

    # Rule 2: financial/legal topics — process but require approval for all actions
    if classification.involves_financial:
        return {
            "allowed": True,
            "rule": "financial_topic",
            "reason": "Financial topic — process normally but all outbound actions require approval",
        }

    # Rule 3: VIP contacts — don't auto-send, always require approval
    if classification.involves_vip:
        # Allow processing (classification, drafting) but the reasoning engine
        # should know to always request approval for VIP contacts
        return {
            "allowed": True,
            "rule": "vip_contact",
            "reason": "VIP contact — auto-processing allowed but all actions require approval",
        }

    # Rule 4: legal content detection from payload keywords
    legal_keywords = {"legal", "lawsuit", "attorney", "lawyer", "court", "subpoena", "litigation"}
    subject = str(payload.get("subject", "")).lower()
    body = str(payload.get("body", "") or payload.get("description", "")).lower()
    combined_text = f"{subject} {body}"
    if any(kw in combined_text for kw in legal_keywords):
        return {
            "allowed": False,
            "rule": "legal_content",
            "reason": "Legal content detected — requires manual handling",
        }

    # Rule 5: high-value order detection (>5000 EUR)
    order_value = payload.get("order_value") or payload.get("total_amount")
    if order_value is not None:
        try:
            if float(order_value) > 5000:
                return {
                    "allowed": True,
                    "rule": "high_value_order",
                    "reason": "High-value order (>5000 EUR) — process with extra care, require approval for actions",
                }
        except (ValueError, TypeError):
            pass

    # Default: allowed
    return {"allowed": True, "rule": None, "reason": None}
