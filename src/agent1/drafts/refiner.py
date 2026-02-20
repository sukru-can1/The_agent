"""Draft refiner — uses AI to revise email drafts based on operator instructions."""

from __future__ import annotations

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.reasoning.providers import get_provider
from agent1.reasoning.router import get_fast_model

log = get_logger(__name__)

REVISE_SYSTEM = """You are an email writing assistant for GLAMIRA (luxury jewelry e-commerce).
You refine customer service email drafts based on operator instructions.

Rules:
- Write ONLY the revised email body — no subject line, no metadata, no commentary.
- Preserve the original meaning unless the instruction says otherwise.
- Keep professional tone appropriate for a luxury brand.
- If the instruction mentions adding specific info (tracking numbers, order details),
  include a placeholder like [TRACKING_NUMBER] if not provided.
- Respect the detected language of the original draft.
"""


async def revise_draft(
    original_body: str | None,
    current_body: str,
    subject: str,
    from_address: str,
    instruction: str,
) -> dict:
    """Revise an email draft based on an operator instruction.

    Returns: {revised_body, model_used, input_tokens, output_tokens}
    """
    # Fetch relevant learned rules for this sender's domain
    rules_context = ""
    if from_address and "@" in from_address:
        domain = from_address.split("@")[1].lower()
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rules = await conn.fetch(
                    """
                    SELECT content FROM knowledge
                    WHERE active = true
                      AND (content ILIKE $1 OR category = 'operator_instruction')
                    ORDER BY created_at DESC
                    LIMIT 5
                    """,
                    f"%{domain}%",
                )
            if rules:
                rules_context = "\n\nRelevant rules for this sender:\n" + "\n".join(
                    f"- {r['content']}" for r in rules
                )
        except Exception as exc:
            log.warning("revise_draft_rules_fetch_failed", error=str(exc))

    # Build the prompt
    parts = []
    if original_body:
        parts.append(f"## Original customer email\n{original_body}")
    parts.append(f"## Subject\n{subject}")
    parts.append(f"## Current draft reply\n{current_body}")
    parts.append(f"## Operator instruction\n{instruction}")
    if rules_context:
        parts.append(rules_context)
    parts.append("\nWrite ONLY the revised email body:")

    user_message = "\n\n".join(parts)

    provider = await get_provider()
    model = await get_fast_model()

    response = await provider.generate(
        model=model,
        messages=[{"role": "user", "content": user_message}],
        system=REVISE_SYSTEM,
        max_tokens=2048,
    )

    revised = (response.text or "").strip()
    if not revised:
        revised = current_body  # Fallback to current if AI returns empty

    log.info(
        "draft_revised",
        model=model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        instruction=instruction[:100],
    )

    return {
        "revised_body": revised,
        "model_used": model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }
