"""Tests for the context engine."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent1.common.models import (
    ClassificationResult, Complexity, Event, EventSource, Priority,
)
from agent1.intelligence.context_engine import (
    EnrichedContext,
    enrich,
    _extract_search_query,
    _estimate_tokens,
)


@pytest.fixture
def email_event():
    return Event(
        source=EventSource.GMAIL,
        event_type="new_email",
        priority=Priority.MEDIUM,
        payload={
            "from_address": "customer@example.de",
            "subject": "Missing ring from order DE-45123",
            "body": "I ordered a ring 3 days ago and it arrived without the center diamond.",
        },
    )


@pytest.fixture
def classification():
    return ClassificationResult(
        category="customer_complaint",
        urgency=Priority.HIGH,
        complexity=Complexity.MODERATE,
        needs_response=True,
        confidence=0.9,
    )


def test_extract_search_query_gmail(email_event):
    query = _extract_search_query(email_event)
    assert "Missing ring" in query
    assert "customer@example.de" in query


def test_extract_search_query_freshdesk():
    event = Event(
        source=EventSource.FRESHDESK,
        event_type="ticket_updated",
        payload={"ticket_id": 4523, "subject": "Refund request"},
    )
    query = _extract_search_query(event)
    assert "Refund request" in query
    assert "4523" in query


def test_extract_search_query_chat():
    event = Event(
        source=EventSource.GCHAT,
        event_type="chat_message",
        payload={"text": "What tickets are open for DE market?", "sender": "Sukru"},
    )
    query = _extract_search_query(event)
    assert "What tickets are open" in query


def test_estimate_tokens():
    assert _estimate_tokens("hello world") > 0
    assert _estimate_tokens("a" * 1000) > _estimate_tokens("hello")


def test_enriched_context_dataclass():
    ctx = EnrichedContext(
        similar_incidents=[],
        sender_history=[],
        relevant_knowledge=[],
        related_recent_events=[],
        context_summary="",
        token_estimate=0,
    )
    assert ctx.token_estimate == 0


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool with proper async context manager."""
    pool = MagicMock()
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


@pytest.mark.asyncio
async def test_enrich_returns_context(email_event, classification, mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = []

    with patch("agent1.intelligence.context_engine.get_pool", new_callable=AsyncMock, return_value=pool):
        with patch("agent1.intelligence.context_engine.embed_text", new_callable=AsyncMock, return_value=[0.0] * 1024):
            ctx = await enrich(email_event, classification)

    assert isinstance(ctx, EnrichedContext)
    assert ctx.token_estimate >= 0
