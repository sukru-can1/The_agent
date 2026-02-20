"""Feedback intelligence -- qualitative analysis of operator corrections."""

from __future__ import annotations

import re

from agent1.common.logging import get_logger
from agent1.intelligence.proposals import ProposalType, create_proposal
from agent1.reasoning.providers import get_provider, provider_available
from agent1.reasoning.router import get_flash_model

log = get_logger(__name__)


def _parse_rules_from_response(response: str) -> list[str]:
    """Extract RULE: lines from Flash response."""
    rules = []
    for line in response.strip().splitlines():
        line = line.strip()
        match = re.match(r"^RULE:\s*(.+)$", line, re.IGNORECASE)
        if match:
            rules.append(match.group(1).strip())
    return rules


async def _call_flash(prompt: str) -> str:
    """Call flash-tier model for quick analysis. Returns response text."""
    if not await provider_available():
        return ""

    provider = await get_provider()
    response = await provider.generate(
        model=get_flash_model(),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
    )
    return (response.text or "").strip()


async def analyze_edit(
    draft_id: int,
    original: str,
    edited: str,
    sender_domain: str | None = None,
    category: str | None = None,
) -> None:
    """Analyze a draft edit qualitatively and create rule proposals."""
    prompt = f"""Compare these two email drafts and identify specific patterns the agent should learn.

ORIGINAL (agent wrote):
{original[:2000]}

EDITED (operator corrected to):
{edited[:2000]}

Sender domain: {sender_domain or 'unknown'}
Category: {category or 'unknown'}

List each specific change as a concrete, actionable rule.
Format each rule on its own line starting with "RULE: "
Examples:
RULE: Use first name instead of formal greeting for .de customers
RULE: Keep response under 3 paragraphs
RULE: Always reference the order number in the subject"""

    try:
        response = await _call_flash(prompt)
        rules = _parse_rules_from_response(response)

        for rule in rules:
            domain_label = f" for {sender_domain}" if sender_domain else ""
            await create_proposal(
                type=ProposalType.LEARNED_RULE,
                title=f"Draft style rule{domain_label}",
                description=rule,
                evidence=f"Learned from edit of draft #{draft_id}. Domain: {sender_domain}, Category: {category}",
                confidence=0.6,
            )
            log.info("edit_rule_proposed", draft_id=draft_id, rule=rule[:80])

    except Exception:
        log.exception("analyze_edit_failed", draft_id=draft_id)


async def analyze_rejection(
    draft_id: int,
    draft_body: str,
    event_payload: dict | None = None,
    rejection_reason: str | None = None,
) -> None:
    """Analyze a draft rejection and propose rules to prevent recurrence."""
    payload_summary = ""
    if event_payload:
        payload_summary = f"\nEvent context: subject={event_payload.get('subject', '')}, " \
                         f"sender={event_payload.get('from_address', event_payload.get('sender_email', ''))}"

    prompt = f"""An email draft was REJECTED by the operator. Analyze why and suggest rules.

DRAFT (rejected):
{draft_body[:2000]}
{payload_summary}

OPERATOR'S REASON: {rejection_reason or 'Not specified'}

What was wrong? What rule should the agent follow to avoid this mistake?
Format each rule on its own line starting with "RULE: " """

    try:
        response = await _call_flash(prompt)
        rules = _parse_rules_from_response(response)

        for rule in rules:
            await create_proposal(
                type=ProposalType.LEARNED_RULE,
                title=f"Rejection learning (draft #{draft_id})",
                description=rule,
                evidence=f"Learned from rejection of draft #{draft_id}. Reason: {rejection_reason or 'not specified'}",
                confidence=0.7,
            )

    except Exception:
        log.exception("analyze_rejection_failed", draft_id=draft_id)
