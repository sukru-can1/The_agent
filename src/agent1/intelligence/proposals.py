"""Proposals system -- universal approval workflow for all agent learning."""

from __future__ import annotations

import json
from enum import StrEnum
from uuid import UUID

from agent1.common.db import get_pool
from agent1.common.logging import get_logger

log = get_logger(__name__)


class ProposalType(StrEnum):
    LEARNED_RULE = "learned_rule"
    STRONG_RULE = "strong_rule"
    TOOL_CREATION = "tool_creation"
    AUTOMATION = "automation"
    MCP_SERVER = "mcp_server"
    GUARDRAIL_OVERRIDE = "guardrail_override"
    THRESHOLD_ADJUSTMENT = "threshold_adjustment"
    PLAYBOOK_SUGGESTION = "playbook_suggestion"


async def create_proposal(
    *,
    type: ProposalType,
    title: str,
    description: str,
    evidence: str | None = None,
    code: str | None = None,
    config: dict | None = None,
    confidence: float = 0.5,
    related_event_ids: list[UUID] | None = None,
) -> UUID:
    """Create a new proposal pending operator approval.

    Returns the proposal UUID.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        proposal_id = await conn.fetchval(
            """
            INSERT INTO proposals (type, title, description, evidence, code, config,
                                   confidence, related_event_ids)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            RETURNING id
            """,
            type.value,
            title,
            description,
            evidence,
            code,
            json.dumps(config) if config else None,
            confidence,
            related_event_ids,
        )

    log.info("proposal_created", id=str(proposal_id), type=type.value, title=title)
    return proposal_id


async def get_pending_proposals(
    type: ProposalType | None = None,
    limit: int = 20,
) -> list[dict]:
    """Get pending proposals, optionally filtered by type."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if type:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at
                FROM proposals
                WHERE status = 'pending' AND type = $1
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC, created_at DESC
                LIMIT $2
                """,
                type.value,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at
                FROM proposals
                WHERE status = 'pending'
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC, created_at DESC
                LIMIT $1
                """,
                limit,
            )
    return [dict(r) for r in rows]


async def get_proposal(proposal_id: UUID) -> dict | None:
    """Get a single proposal by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM proposals WHERE id = $1",
            proposal_id,
        )
    return dict(row) if row else None


async def approve_proposal(
    proposal_id: UUID,
    *,
    reviewed_by: str = "operator",
    notes: str | None = None,
    edited_description: str | None = None,
) -> bool:
    """Approve a proposal and execute its side effects.

    Returns True if approved, False if proposal not found or not pending.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM proposals WHERE id = $1 AND status = 'pending'",
            proposal_id,
        )
        if not row:
            return False

        final_description = edited_description or row["description"]

        await conn.execute(
            """
            UPDATE proposals
            SET status = 'approved', reviewed_at = NOW(), reviewed_by = $2,
                review_notes = $3, description = $4
            WHERE id = $1
            """,
            proposal_id,
            reviewed_by,
            notes,
            final_description,
        )

    proposal = dict(row)
    proposal["description"] = final_description
    await execute_approval(proposal)

    log.info("proposal_approved", id=str(proposal_id), type=row["type"])
    return True


async def reject_proposal(
    proposal_id: UUID,
    *,
    reason: str | None = None,
    reviewed_by: str = "operator",
) -> bool:
    """Reject a proposal. Returns True if rejected."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE proposals
            SET status = 'rejected', reviewed_at = NOW(), reviewed_by = $2, review_notes = $3
            WHERE id = $1 AND status = 'pending'
            """,
            proposal_id,
            reviewed_by,
            reason,
        )

    success = result != "UPDATE 0"
    if success:
        log.info("proposal_rejected", id=str(proposal_id), reason=reason)
    return success


async def get_proposal_stats() -> dict:
    """Get counts of proposals by type and status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT type, status, COUNT(*) as count
            FROM proposals
            GROUP BY type, status
            ORDER BY type, status
            """
        )
    stats: dict[str, dict[str, int]] = {}
    for r in rows:
        t = r["type"]
        if t not in stats:
            stats[t] = {}
        stats[t][r["status"]] = r["count"]
    return stats


async def execute_approval(proposal: dict) -> None:
    """Execute the side effect of an approved proposal."""
    ptype = proposal["type"]

    if ptype in (ProposalType.LEARNED_RULE, ProposalType.STRONG_RULE):
        from agent1.memory.manager import store_knowledge
        await store_knowledge(
            category="approved_rule",
            content=proposal["description"],
            source=f"proposal:{proposal['id']}",
        )
        log.info("approved_rule_stored", proposal_id=str(proposal["id"]))

    elif ptype == ProposalType.GUARDRAIL_OVERRIDE:
        config = proposal.get("config")
        if isinstance(config, str):
            config = json.loads(config)
        if config and config.get("event_id"):
            from agent1.common.models import Event, EventSource, Priority
            from agent1.queue.publisher import publish_event
            event = Event(
                source=EventSource.ADMIN,
                event_type="guardrail_override",
                priority=Priority.HIGH,
                payload={
                    "original_event_id": config["event_id"],
                    "rule_name": config.get("rule_name", ""),
                    "skip_guardrails": True,
                },
            )
            await publish_event(event)
            log.info("guardrail_override_published", event_id=config["event_id"])

    elif ptype == ProposalType.TOOL_CREATION:
        if proposal.get("code"):
            from agent1.intelligence.solutions.factory import activate_tool
            await activate_tool(proposal)

    elif ptype == ProposalType.AUTOMATION:
        if proposal.get("config"):
            from agent1.intelligence.solutions.factory import activate_automation
            await activate_automation(proposal)

    elif ptype == ProposalType.THRESHOLD_ADJUSTMENT:
        config = proposal.get("config")
        if isinstance(config, str):
            config = json.loads(config)
        if config:
            from agent1.intelligence.analytics_engine import update_threshold
            await update_threshold(config)

    # MCP_SERVER and PLAYBOOK_SUGGESTION are handled manually for now
