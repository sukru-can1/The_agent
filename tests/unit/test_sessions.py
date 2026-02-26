"""Tests for conversation sessions: key resolution, expiry logic, and integration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent1.common.models import Event, EventSource, Priority
from agent1.sessions.manager import (
    _is_session_expired,
    load_session_history,
    resolve_session_key,
    store_session_messages,
)


def _mock_pool(conn: AsyncMock) -> AsyncMock:
    """Create a mock asyncpg pool whose acquire() returns *conn* as async ctx mgr."""

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = AsyncMock()
    pool.acquire = _acquire
    return pool


# ---------------------------------------------------------------------------
# resolve_session_key
# ---------------------------------------------------------------------------


def _make_event(source: EventSource, payload: dict | None = None) -> Event:
    return Event(
        source=source,
        event_type="MESSAGE",
        priority=Priority.MEDIUM,
        payload=payload or {},
    )


def test_resolve_gchat_with_space_and_thread():
    event = _make_event(EventSource.GCHAT, {"space": "spaces/AAA", "thread": "spaces/AAA/threads/123"})
    assert resolve_session_key(event) == "gchat:spaces/AAA:spaces/AAA/threads/123"


def test_resolve_gchat_space_only_dm():
    """GChat without thread (DMs) should fall back to space-only key."""
    event = _make_event(EventSource.GCHAT, {"space": "spaces/BBB", "thread": ""})
    assert resolve_session_key(event) == "gchat:spaces/BBB"


def test_resolve_gchat_no_space_returns_none():
    event = _make_event(EventSource.GCHAT, {"text": "hello"})
    assert resolve_session_key(event) is None


def test_resolve_dashboard():
    event = _make_event(EventSource.DASHBOARD, {"sender_email": "sukru@example.com"})
    assert resolve_session_key(event) == "dashboard:sukru@example.com"


def test_resolve_dashboard_default_email():
    event = _make_event(EventSource.DASHBOARD, {})
    assert resolve_session_key(event) == "dashboard:admin"


def test_resolve_gmail_returns_none():
    event = _make_event(EventSource.GMAIL, {"from_address": "a@b.com"})
    assert resolve_session_key(event) is None


def test_resolve_freshdesk_returns_none():
    event = _make_event(EventSource.FRESHDESK, {"ticket_id": "123"})
    assert resolve_session_key(event) is None


def test_resolve_starinfinity_returns_none():
    event = _make_event(EventSource.STARINFINITY, {"task_id": "t1"})
    assert resolve_session_key(event) is None


def test_resolve_scheduler_returns_none():
    event = _make_event(EventSource.SCHEDULER, {})
    assert resolve_session_key(event) is None


# ---------------------------------------------------------------------------
# _is_session_expired
# ---------------------------------------------------------------------------


class TestIsSessionExpired:
    """Tests for the inline expiry checker."""

    def test_gchat_10min_not_expired(self):
        last_active = datetime.now(UTC) - timedelta(minutes=10)
        assert _is_session_expired(last_active, "gchat") is False

    def test_gchat_31min_expired(self):
        last_active = datetime.now(UTC) - timedelta(minutes=31)
        assert _is_session_expired(last_active, "gchat") is True

    def test_gchat_exactly_30min_not_expired(self):
        last_active = datetime.now(UTC) - timedelta(minutes=30)
        assert _is_session_expired(last_active, "gchat") is False

    def test_dashboard_2h_not_expired(self):
        last_active = datetime.now(UTC) - timedelta(hours=2)
        assert _is_session_expired(last_active, "dashboard") is False

    def test_dashboard_25h_expired(self):
        last_active = datetime.now(UTC) - timedelta(hours=25)
        assert _is_session_expired(last_active, "dashboard") is True

    def test_dashboard_daily_reset(self):
        """Sessions active before today's 04:00 UTC should expire after that time."""
        now = datetime.now(UTC)
        reset = now.replace(hour=4, minute=0, second=0, microsecond=0)

        if now >= reset:
            # Last active was before today's reset
            last_active = reset - timedelta(hours=1)
            assert _is_session_expired(last_active, "dashboard") is True
        else:
            # Before 04:00 today — yesterday's session still active
            last_active = now - timedelta(hours=1)
            assert _is_session_expired(last_active, "dashboard") is False

    def test_unknown_platform_not_expired(self):
        last_active = datetime.now(UTC) - timedelta(days=30)
        assert _is_session_expired(last_active, "unknown") is False


# ---------------------------------------------------------------------------
# load_session_history (mocked DB)
# ---------------------------------------------------------------------------


class _FakeRow(dict):
    """Minimal dict subclass that supports attribute-style + key access."""
    def __getitem__(self, key):
        return super().__getitem__(key)


def _fake_rows(pairs: list[tuple[str, str]]) -> list[_FakeRow]:
    return [_FakeRow(role=role, content=content) for role, content in pairs]


@pytest.mark.asyncio
async def test_load_session_history_returns_alternating():
    """Should return user/assistant pairs in chronological order."""
    session_id = uuid4()
    rows = _fake_rows([
        ("user", "What is DE status?"),
        ("assistant", "DE queue has 3 items."),
        ("user", "And FR?"),
        ("assistant", "FR queue has 1 item."),
    ])

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)  # no summary
    conn.fetch = AsyncMock(return_value=rows)

    with patch("agent1.sessions.manager.get_pool", AsyncMock(return_value=_mock_pool(conn))):
        history = await load_session_history(session_id, max_messages=20, max_tokens=4000)

    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_load_session_history_with_summary():
    """When a summary exists, it should be prepended as user+assistant pair."""
    session_id = uuid4()
    rows = _fake_rows([
        ("user", "hello"),
        ("assistant", "hi there"),
    ])

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value="User asked about DE and FR queues.")
    conn.fetch = AsyncMock(return_value=rows)

    with patch("agent1.sessions.manager.get_pool", AsyncMock(return_value=_mock_pool(conn))):
        history = await load_session_history(session_id, max_messages=20, max_tokens=4000)

    assert len(history) == 4
    assert "[Session summary" in history[0]["content"]
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_load_session_history_empty_returns_empty():
    """No messages → empty list."""
    session_id = uuid4()

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])

    with patch("agent1.sessions.manager.get_pool", AsyncMock(return_value=_mock_pool(conn))):
        history = await load_session_history(session_id, max_messages=20, max_tokens=4000)

    assert history == []


@pytest.mark.asyncio
async def test_load_session_history_trims_to_token_budget():
    """Should trim oldest messages when they exceed the token budget."""
    session_id = uuid4()
    # Each message ~ 100 chars = 25 tokens. 6 messages = 150 tokens.
    # With a budget of 50 tokens (200 chars), only last pair should survive.
    rows = _fake_rows([
        ("user", "A" * 100),
        ("assistant", "B" * 100),
        ("user", "C" * 100),
        ("assistant", "D" * 100),
        ("user", "E" * 100),
        ("assistant", "F" * 100),
    ])

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=rows)

    with patch("agent1.sessions.manager.get_pool", AsyncMock(return_value=_mock_pool(conn))):
        history = await load_session_history(session_id, max_messages=20, max_tokens=50)

    # Should have trimmed to fit ~ 200 chars (50 tokens * 4)
    assert len(history) <= 4
    # Must still end with assistant
    if history:
        assert history[-1]["role"] == "assistant"
        assert history[0]["role"] == "user"


# ---------------------------------------------------------------------------
# store_session_messages (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_session_messages_inserts_both():
    """Should insert user and assistant messages and update session."""
    session_id = uuid4()
    event_id = uuid4()

    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=5)  # message_count < threshold

    @asynccontextmanager
    async def _fake_tx():
        yield

    conn.transaction = _fake_tx

    with patch("agent1.sessions.manager.get_pool", AsyncMock(return_value=_mock_pool(conn))):
        await store_session_messages(session_id, "hello", "hi back", event_id)

    # Should have 2 INSERT + 1 UPDATE (fetchval) = 2 execute calls + 1 fetchval
    assert conn.execute.call_count == 2
    assert conn.fetchval.call_count == 1


@pytest.mark.asyncio
async def test_store_session_messages_skips_empty():
    """Should skip storage when both texts are empty."""
    session_id = uuid4()

    called = False

    async def _should_not_be_called():
        nonlocal called
        called = True

    with patch("agent1.sessions.manager.get_pool", _should_not_be_called):
        await store_session_messages(session_id, "", "", None)

    assert not called
