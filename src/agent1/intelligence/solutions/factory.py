"""Solution factory — orchestrates tool creation, script building, and automation proposals."""

from __future__ import annotations

import json

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.intelligence.proposals import ProposalType, create_proposal
from agent1.intelligence.solutions.script_runner import validate_code

log = get_logger(__name__)


async def propose_solution(
    *,
    name: str,
    description: str,
    solution_type: str,
    code: str | None = None,
    config: dict | None = None,
    trigger_pattern: str | None = None,
) -> None:
    """Create a solution proposal for operator review."""
    proposal_type = ProposalType.TOOL_CREATION
    if solution_type == "automation":
        proposal_type = ProposalType.AUTOMATION

    await create_proposal(
        type=proposal_type,
        title=f"Solution: {name}",
        description=description,
        code=code,
        config=config,
        evidence=f"Trigger: {trigger_pattern}" if trigger_pattern else None,
        confidence=0.5,
    )
    log.info("solution_proposed", name=name, type=solution_type)


async def activate_tool(proposal: dict) -> None:
    """Activate an approved tool_creation proposal."""
    code = proposal.get("code", "")
    if not code:
        log.warning("activate_tool_no_code", proposal_id=str(proposal["id"]))
        return

    # Validate code
    error = validate_code(code)
    if error:
        log.error("activate_tool_code_invalid", error=error)
        return

    # Store in solutions table
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO solutions (name, description, solution_type, code, status,
                                   approved_at, approved_by, active)
            VALUES ($1, $2, 'tool', $3, 'active', NOW(), $4, true)
            """,
            proposal.get("title", "unnamed_tool"),
            proposal.get("description", ""),
            code,
            proposal.get("reviewed_by", "operator"),
        )

    # Register as dynamic tool
    try:
        from agent1.tools.mcp.builder import DynamicTool
        from agent1.tools.registry import register_tool

        tool_name = f"solution__{proposal.get('title', 'tool').lower().replace(' ', '_')[:30]}"
        tool = DynamicTool(
            tool_name=tool_name,
            tool_description=proposal.get("description", ""),
            tool_input_schema=json.loads(proposal["config"]) if proposal.get("config") else {"type": "object", "properties": {}},
            tool_code=code,
        )
        register_tool(tool)
        log.info("solution_tool_activated", tool=tool_name)
    except Exception:
        log.exception("solution_tool_registration_failed")


async def activate_automation(proposal: dict) -> None:
    """Activate an approved automation proposal."""
    config = proposal.get("config")
    if isinstance(config, str):
        config = json.loads(config)
    if not config:
        log.warning("activate_automation_no_config", proposal_id=str(proposal["id"]))
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Store solution
        solution_id = await conn.fetchval(
            """
            INSERT INTO solutions (name, description, solution_type, code, config, status,
                                   approved_at, approved_by, active)
            VALUES ($1, $2, 'automation', $3, $4::jsonb, 'active', NOW(), $5, true)
            RETURNING id
            """,
            proposal.get("title", "unnamed_automation"),
            proposal.get("description", ""),
            proposal.get("code"),
            json.dumps(config),
            proposal.get("reviewed_by", "operator"),
        )

        # Create automation entry
        await conn.execute(
            """
            INSERT INTO automations (solution_id, name, trigger_type, trigger_config, active)
            VALUES ($1, $2, $3, $4::jsonb, true)
            """,
            solution_id,
            proposal.get("title", "unnamed"),
            config.get("trigger_type", "cron"),
            json.dumps(config.get("trigger_config", {})),
        )

    log.info("automation_activated", solution_id=str(solution_id))


async def get_active_solutions(solution_type: str | None = None) -> list[dict]:
    """Get all active solutions."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if solution_type:
            rows = await conn.fetch(
                "SELECT * FROM solutions WHERE active = true AND solution_type = $1 ORDER BY created_at DESC",
                solution_type,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM solutions WHERE active = true ORDER BY created_at DESC"
            )
    return [dict(r) for r in rows]
