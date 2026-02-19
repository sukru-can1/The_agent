"""Test FastAPI webhook routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_infra():
    """Mock database, redis, and tool registration."""
    with (
        patch("agent1.webhook.app.get_pool", new_callable=AsyncMock),
        patch("agent1.webhook.app.get_redis", new_callable=AsyncMock),
        patch("agent1.tools.registry.register_all_tools"),
        patch("agent1.webhook.routes.gchat.publish_event", new_callable=AsyncMock),
        patch("agent1.webhook.routes.freshdesk.publish_event", new_callable=AsyncMock),
        patch("agent1.webhook.routes.gchat.get_pool", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
async def client(mock_infra):
    from agent1.webhook.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "agent" in data

    @pytest.mark.asyncio
    async def test_status(self, client):
        with (
            patch("agent1.webhook.routes.health.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("agent1.webhook.routes.health.get_redis", new_callable=AsyncMock) as mock_redis,
        ):
            mock_conn = AsyncMock()
            mock_conn.fetchval = AsyncMock(return_value=1)
            mock_pool.return_value.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.return_value.acquire.return_value.__aexit__ = AsyncMock()

            mock_redis_inst = AsyncMock()
            mock_redis_inst.ping = AsyncMock()
            mock_redis.return_value = mock_redis_inst

            response = await client.get("/status")
        assert response.status_code == 200


class TestGchatWebhook:
    @pytest.mark.asyncio
    async def test_added_to_space(self, client):
        response = await client.post(
            "/webhooks/gchat",
            json={"type": "ADDED_TO_SPACE"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "Hello" in data.get("text", "")

    @pytest.mark.asyncio
    async def test_message_event(self, client):
        response = await client.post(
            "/webhooks/gchat",
            json={
                "type": "MESSAGE",
                "message": {
                    "name": "spaces/abc/messages/123",
                    "text": "What is the queue depth?",
                    "thread": {"name": "spaces/abc/threads/t1"},
                },
                "user": {"displayName": "Sukru", "email": "sukru@glamira.com"},
                "space": {"name": "spaces/abc"},
            },
        )
        assert response.status_code == 200
        assert "Processing" in response.json().get("text", "")


class TestFreshdeskWebhook:
    @pytest.mark.asyncio
    async def test_ticket_event(self, client):
        response = await client.post(
            "/webhooks/freshdesk",
            json={
                "ticket_id": 12345,
                "triggered_event": "ticket_created",
                "ticket_priority": 3,
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
