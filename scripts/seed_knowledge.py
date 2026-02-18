"""Seed initial knowledge into the agent's memory.

Run after database is set up to populate baseline knowledge:
- Escalation rules
- VIP thresholds
- Contact directory
- Market-specific knowledge
- Common issue patterns
"""

from __future__ import annotations

import asyncio
import os

from agent1.common.db import get_pool, close_pools
from agent1.common.embeddings import embed_text
from agent1.common.settings import get_settings


SEED_KNOWLEDGE = [
    {
        "category": "escalation_rule",
        "content": "VIP customers are those with lifetime value >€5,000. Always escalate VIP issues to Sukru with HIGH priority.",
        "source": "configured",
    },
    {
        "category": "escalation_rule",
        "content": "Payment and financial issues must be flagged immediately with CRITICAL priority. Never auto-respond to financial matters.",
        "source": "configured",
    },
    {
        "category": "escalation_rule",
        "content": "If 3 or more Freshdesk tickets arrive about the same topic within 1 hour, this is likely a systemic issue. Create a CRITICAL alert.",
        "source": "configured",
    },
    {
        "category": "escalation_rule",
        "content": "SLA breaches should be alerted to the assigned agent and posted to ops-agent-alerts space.",
        "source": "configured",
    },
    {
        "category": "communication_style",
        "content": "For German market (DE): formal tone, use Sie form, detailed and thorough responses.",
        "source": "configured",
    },
    {
        "category": "communication_style",
        "content": "For Turkish market (TR): professional but warm, slightly more relationship-oriented than DE.",
        "source": "configured",
    },
    {
        "category": "communication_style",
        "content": "For English markets (US/UK): direct and concise, professional but friendly.",
        "source": "configured",
    },
    {
        "category": "contact_directory",
        "content": "Sukru Can — COO, GLAMIRA Group. Primary user of the agent. Available via Google Chat DM.",
        "source": "configured",
    },
    {
        "category": "business_rule",
        "content": "GLAMIRA operates in 76+ international markets. Key markets: Germany (DE), Turkey (TR), United States (US), United Kingdom (UK).",
        "source": "configured",
    },
    {
        "category": "business_rule",
        "content": "GLAMIRA is a luxury jewelry e-commerce company. All customer communications should reflect premium brand positioning.",
        "source": "configured",
    },
    {
        "category": "pattern",
        "content": "DHL delivery issues tend to spike on Mondays and after holidays. Check DHL status page when multiple delivery complaints arrive.",
        "source": "configured",
    },
    {
        "category": "autonomy_rule",
        "content": "Never auto-send emails to: customers, legal counsel, investors, banks, government agencies. Always wait for approval.",
        "source": "configured",
    },
    {
        "category": "autonomy_rule",
        "content": "Can auto-respond to internal team members for routine acknowledgments only. Prefix with '[via AGENT1]'.",
        "source": "configured",
    },
]


async def seed() -> None:
    pool = await get_pool()

    for item in SEED_KNOWLEDGE:
        embedding = await embed_text(item["content"])
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM knowledge WHERE content = $1 AND active = true",
                item["content"],
            )
            if existing:
                print(f"  [skip] {item['category']}: already exists")
                continue

            await conn.execute(
                """
                INSERT INTO knowledge (category, content, source, embedding)
                VALUES ($1, $2, $3, $4::vector)
                """,
                item["category"],
                item["content"],
                item["source"],
                embedding_str,
            )
            print(f"  [seed] {item['category']}: {item['content'][:60]}...")

    await close_pools()
    print("\nSeeding complete.")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
