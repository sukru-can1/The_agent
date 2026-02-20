"""Tests for the proposals system."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from agent1.intelligence.proposals import (
    create_proposal,
    approve_proposal,
    reject_proposal,
    get_pending_proposals,
    execute_approval,
    ProposalType,
)


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool with proper async context manager for acquire()."""
    pool = MagicMock()
    conn = AsyncMock()
    # pool.acquire() must be synchronous (returns context manager, not coroutine)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


@pytest.mark.asyncio
async def test_create_proposal_returns_id(mock_pool):
    pool, conn = mock_pool
    proposal_id = uuid4()
    conn.fetchval.return_value = proposal_id

    with patch("agent1.intelligence.proposals.get_pool", new_callable=AsyncMock, return_value=pool):
        result = await create_proposal(
            type=ProposalType.LEARNED_RULE,
            title="Casual tone for .de",
            description="Use first name greeting for German customers",
            evidence="Learned from draft #45",
            confidence=0.6,
        )

    assert result == proposal_id
    conn.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_create_proposal_with_code(mock_pool):
    pool, conn = mock_pool
    conn.fetchval.return_value = uuid4()

    with patch("agent1.intelligence.proposals.get_pool", new_callable=AsyncMock, return_value=pool):
        result = await create_proposal(
            type=ProposalType.TOOL_CREATION,
            title="Carrier status checker",
            description="Check DHL tracking API",
            code="async def run(*, tracking_id: str): ...",
            confidence=0.5,
        )

    assert result is not None
    call_args = conn.fetchval.call_args
    # Verify code was passed in the SQL params
    assert "async def run" in str(call_args)


@pytest.mark.asyncio
async def test_get_pending_proposals(mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [
        {"id": uuid4(), "type": "learned_rule", "title": "Test", "status": "pending",
         "description": "desc", "confidence": 0.6, "created_at": "2026-01-01T00:00:00"},
    ]

    with patch("agent1.intelligence.proposals.get_pool", new_callable=AsyncMock, return_value=pool):
        results = await get_pending_proposals()

    assert len(results) == 1
    assert results[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_approve_proposal_updates_status(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = {
        "id": uuid4(), "type": "learned_rule", "title": "Test",
        "description": "Use casual tone", "code": None, "config": None,
        "confidence": 0.8, "status": "pending",
    }
    conn.execute.return_value = "UPDATE 1"

    with patch("agent1.intelligence.proposals.get_pool", new_callable=AsyncMock, return_value=pool):
        with patch("agent1.intelligence.proposals.execute_approval", new_callable=AsyncMock):
            result = await approve_proposal(conn.fetchrow.return_value["id"])

    assert result is True


@pytest.mark.asyncio
async def test_reject_proposal_updates_status(mock_pool):
    pool, conn = mock_pool
    conn.execute.return_value = "UPDATE 1"

    with patch("agent1.intelligence.proposals.get_pool", new_callable=AsyncMock, return_value=pool):
        result = await reject_proposal(uuid4(), reason="Not applicable")

    assert result is True
