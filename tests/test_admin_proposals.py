"""Tests for admin API proposal and solution endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


@pytest.fixture
def mock_redis():
    return AsyncMock()


# ── list_proposals ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_proposals_default(mock_pool):
    pool, conn = mock_pool
    fake_rows = [
        {"id": uuid4(), "type": "learned_rule", "title": "Test", "description": "desc",
         "evidence": None, "code": None, "config": None, "confidence": 0.8,
         "status": "pending", "created_at": "2026-01-01", "expires_at": None,
         "reviewed_at": None, "reviewed_by": None},
    ]
    conn.fetch.return_value = fake_rows

    with patch("agent1.webhook.routes.admin.get_pool", new_callable=AsyncMock, return_value=pool):
        from agent1.webhook.routes.admin import list_proposals
        result = await list_proposals(status="pending", type=None, limit=20)

    assert len(result) == 1
    assert result[0]["type"] == "learned_rule"
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_list_proposals_with_type_filter(mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = []

    with patch("agent1.webhook.routes.admin.get_pool", new_callable=AsyncMock, return_value=pool):
        from agent1.webhook.routes.admin import list_proposals
        result = await list_proposals(status="pending", type="tool_creation", limit=10)

    assert result == []
    # Should have called with 3 params (status, type, limit)
    args = conn.fetch.call_args
    assert args[0][1] == "pending"
    assert args[0][2] == "tool_creation"
    assert args[0][3] == 10


# ── proposal_stats ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_proposal_stats():
    fake_stats = {"pending": 5, "approved": 10, "rejected": 2}
    with patch("agent1.intelligence.proposals.get_proposal_stats", new_callable=AsyncMock, return_value=fake_stats):
        from agent1.webhook.routes.admin import proposal_stats
        result = await proposal_stats()
    assert result["pending"] == 5


# ── get_proposal_detail ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_proposal_detail_found():
    pid = uuid4()
    fake = {"id": pid, "title": "Test proposal"}
    with patch("agent1.intelligence.proposals.get_proposal", new_callable=AsyncMock, return_value=fake):
        from agent1.webhook.routes.admin import get_proposal_detail
        result = await get_proposal_detail(str(pid))
    assert result["title"] == "Test proposal"


@pytest.mark.asyncio
async def test_get_proposal_detail_not_found():
    with patch("agent1.intelligence.proposals.get_proposal", new_callable=AsyncMock, return_value=None):
        from agent1.webhook.routes.admin import get_proposal_detail
        with pytest.raises(Exception):  # HTTPException
            await get_proposal_detail(str(uuid4()))


# ── approve / reject ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_proposal_endpoint():
    pid = uuid4()
    with patch("agent1.intelligence.proposals.approve_proposal", new_callable=AsyncMock, return_value=True):
        from agent1.webhook.routes.admin import approve_proposal_endpoint, ProposalApproveBody
        result = await approve_proposal_endpoint(str(pid), ProposalApproveBody(notes="good"))
    assert result["status"] == "approved"


@pytest.mark.asyncio
async def test_reject_proposal_endpoint():
    pid = uuid4()
    with patch("agent1.intelligence.proposals.reject_proposal", new_callable=AsyncMock, return_value=True):
        from agent1.webhook.routes.admin import reject_proposal_endpoint, ProposalRejectBody
        result = await reject_proposal_endpoint(str(pid), ProposalRejectBody(reason="not needed"))
    assert result["status"] == "rejected"


# ── solutions ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_solutions():
    fake = [{"id": 1, "name": "tool1", "solution_type": "tool", "active": True}]
    with patch("agent1.intelligence.solutions.factory.get_active_solutions", new_callable=AsyncMock, return_value=fake):
        from agent1.webhook.routes.admin import list_solutions
        result = await list_solutions(type="tool")
    assert len(result) == 1


# ── status includes pending_proposals ───────────────────────────────


@pytest.mark.asyncio
async def test_status_includes_pending_proposals(mock_pool, mock_redis):
    pool, conn = mock_pool
    # fetchval returns sequentially: pending_drafts, dlq_count, pending_proposals
    conn.fetchval.side_effect = [5, 2, 3]
    conn.fetchrow.return_value = {"timestamp": "2026-01-01", "system": "gmail", "action_type": "send"}

    with (
        patch("agent1.webhook.routes.admin.get_pool", new_callable=AsyncMock, return_value=pool),
        patch("agent1.webhook.routes.admin.get_redis", new_callable=AsyncMock, return_value=mock_redis),
    ):
        mock_redis.zcard.return_value = 10
        mock_redis.exists.return_value = 0
        from agent1.webhook.routes.admin import admin_status
        result = await admin_status()

    assert "pending_proposals" in result
    assert result["pending_proposals"] == 3
