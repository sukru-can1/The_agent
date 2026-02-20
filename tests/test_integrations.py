"""Tests for integrations package — BaseAPIClient and all 3 concrete clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent1.integrations._base import BaseAPIClient, IntegrationError


# -- Helpers -----------------------------------------------------------------


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_error_response(status_code: int = 500) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = "Internal Server Error"
    resp.json.return_value = {"error": "server error"}
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=resp
    )
    return resp


def _make_mock_httpx_client() -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ===========================================================================
# BaseAPIClient tests
# ===========================================================================


class TestBaseAPIClient:
    async def test_request_returns_unwrapped_json_on_success(self):
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"result": "ok"})

        client = BaseAPIClient()
        client._client = mock_httpx

        data = await client.request("GET", "/test")
        assert data == {"result": "ok"}

    async def test_request_raises_integration_error_on_http_error(self):
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_error_response(500)

        client = BaseAPIClient()
        client._integration_name = "TestAPI"
        client._client = mock_httpx

        with pytest.raises(IntegrationError) as exc_info:
            await client.request("GET", "/fail")

        assert exc_info.value.status_code == 500
        assert exc_info.value.integration == "TestAPI"

    async def test_request_raises_integration_error_on_network_error(self):
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.side_effect = httpx.ConnectError("Connection refused")

        client = BaseAPIClient()
        client._integration_name = "TestAPI"
        client._client = mock_httpx

        with pytest.raises(IntegrationError) as exc_info:
            await client.request("GET", "/fail")

        assert exc_info.value.status_code is None
        assert "Connection refused" in exc_info.value.detail

    async def test_request_skips_unwrap_when_false(self):
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"data": {"id": 1}})

        class EnvelopeClient(BaseAPIClient):
            _integration_name = "Test"

            def _unwrap(self, data):
                return data["data"]

        client = EnvelopeClient()
        client._client = mock_httpx

        raw = await client.request("GET", "/test", unwrap=False)
        assert raw == {"data": {"id": 1}}

        unwrapped = await client.request("GET", "/test", unwrap=True)
        assert unwrapped == {"id": 1}

    async def test_get_post_put_convenience(self):
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"ok": True})

        client = BaseAPIClient()
        client._client = mock_httpx

        await client.get("/a", params={"x": 1})
        mock_httpx.request.assert_called_with("GET", "/a", params={"x": 1}, json=None)

        await client.post("/b", json={"y": 2})
        mock_httpx.request.assert_called_with("POST", "/b", params=None, json={"y": 2})

        await client.put("/c", json={"z": 3})
        mock_httpx.request.assert_called_with("PUT", "/c", params=None, json={"z": 3})


# ===========================================================================
# FeedbacksClient tests
# ===========================================================================


class TestFeedbacksClient:
    def test_available_returns_false_when_key_empty(self):
        from agent1.integrations.feedbacks import FeedbacksClient

        with patch("agent1.integrations.feedbacks.get_settings") as mock:
            mock.return_value = MagicMock(feedbacks_api_key="")
            assert FeedbacksClient().available is False

    def test_available_returns_true_when_key_set(self):
        from agent1.integrations.feedbacks import FeedbacksClient

        with patch("agent1.integrations.feedbacks.get_settings") as mock:
            mock.return_value = MagicMock(feedbacks_api_key="sk-test")
            assert FeedbacksClient().available is True

    def test_unwrap_strips_envelope(self):
        from agent1.integrations.feedbacks import FeedbacksClient

        client = FeedbacksClient()
        assert client._unwrap({"app": "feedbacks", "timestamp": "t", "data": {"x": 1}}) == {"x": 1}

    def test_unwrap_passes_through_without_data_key(self):
        from agent1.integrations.feedbacks import FeedbacksClient

        client = FeedbacksClient()
        raw = {"items": [1, 2, 3]}
        assert client._unwrap(raw) == raw

    async def test_get_insights_calls_correct_path(self):
        from agent1.integrations.feedbacks import FeedbacksClient

        client = FeedbacksClient()
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"data": {"alerts": []}})
        client._client = mock_httpx

        result = await client.get_insights(days=7, threshold=0.3)
        mock_httpx.request.assert_called_once_with(
            "GET", "/insights", params={"days": 7, "threshold": 0.3}, json=None
        )
        assert result == {"alerts": []}

    async def test_start_auto_reporter_posts_json(self):
        from agent1.integrations.feedbacks import FeedbacksClient

        client = FeedbacksClient()
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"data": {"started": True}})
        client._client = mock_httpx

        result = await client.start_auto_reporter(count=5)
        mock_httpx.request.assert_called_once_with(
            "POST", "/actions/auto-reporter-start", params=None, json={"count": 5}
        )
        assert result == {"started": True}

    async def test_get_trustpilot_summary_calls_correct_path(self):
        from agent1.integrations.feedbacks import FeedbacksClient

        client = FeedbacksClient()
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"data": {"byStatus": {"new": 2}}})
        client._client = mock_httpx

        result = await client.get_trustpilot_summary()
        mock_httpx.request.assert_called_once_with("GET", "/trustpilot", params=None, json=None)
        assert result == {"byStatus": {"new": 2}}


# ===========================================================================
# FreshdeskClient tests
# ===========================================================================


class TestFreshdeskClient:
    def test_available_returns_false_when_key_empty(self):
        from agent1.integrations.freshdesk import FreshdeskClient

        with patch("agent1.integrations.freshdesk.get_settings") as mock:
            mock.return_value = MagicMock(freshdesk_api_key="")
            assert FreshdeskClient().available is False

    def test_available_returns_true_when_key_set(self):
        from agent1.integrations.freshdesk import FreshdeskClient

        with patch("agent1.integrations.freshdesk.get_settings") as mock:
            mock.return_value = MagicMock(freshdesk_api_key="key123")
            assert FreshdeskClient().available is True

    def test_build_client_uses_basic_auth(self):
        from agent1.integrations.freshdesk import FreshdeskClient

        with patch("agent1.integrations.freshdesk.get_settings") as mock:
            mock.return_value = MagicMock(
                freshdesk_api_key="key123", freshdesk_domain="test.freshdesk.com"
            )
            client = FreshdeskClient()
            httpx_client = client._build_client()
            assert httpx_client._auth is not None  # BasicAuth set

    async def test_get_ticket_includes_conversations(self):
        from agent1.integrations.freshdesk import FreshdeskClient

        client = FreshdeskClient()
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"id": 42, "subject": "Test"})
        client._client = mock_httpx

        result = await client.get_ticket(42)
        mock_httpx.request.assert_called_once_with(
            "GET", "/tickets/42", params={"include": "conversations"}, json=None
        )
        assert result["id"] == 42

    async def test_add_note_posts_correct_body(self):
        from agent1.integrations.freshdesk import FreshdeskClient

        client = FreshdeskClient()
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"id": 99})
        client._client = mock_httpx

        await client.add_note(42, "test note", private=False)
        mock_httpx.request.assert_called_once_with(
            "POST",
            "/tickets/42/notes",
            params=None,
            json={"body": "test note", "private": False},
        )


# ===========================================================================
# StarInfinityClient tests
# ===========================================================================


class TestStarInfinityClient:
    def test_available_requires_both_url_and_key(self):
        from agent1.integrations.starinfinity import StarInfinityClient

        with patch("agent1.integrations.starinfinity.get_settings") as mock:
            mock.return_value = MagicMock(starinfinity_base_url="", starinfinity_api_key="key")
            assert StarInfinityClient().available is False

        with patch("agent1.integrations.starinfinity.get_settings") as mock:
            mock.return_value = MagicMock(starinfinity_base_url="https://x", starinfinity_api_key="")
            assert StarInfinityClient().available is False

        with patch("agent1.integrations.starinfinity.get_settings") as mock:
            mock.return_value = MagicMock(
                starinfinity_base_url="https://x", starinfinity_api_key="key"
            )
            assert StarInfinityClient().available is True

    def test_unwrap_handles_dict_with_data(self):
        from agent1.integrations.starinfinity import StarInfinityClient

        client = StarInfinityClient()
        assert client._unwrap({"data": [1, 2, 3]}) == [1, 2, 3]

    def test_unwrap_handles_dict_without_data(self):
        from agent1.integrations.starinfinity import StarInfinityClient

        client = StarInfinityClient()
        raw = {"id": "abc", "name": "Board"}
        assert client._unwrap(raw) == raw

    def test_unwrap_handles_list(self):
        from agent1.integrations.starinfinity import StarInfinityClient

        client = StarInfinityClient()
        raw = [{"id": 1}, {"id": 2}]
        assert client._unwrap(raw) == raw

    async def test_create_item_uses_unwrap_false(self):
        from agent1.integrations.starinfinity import StarInfinityClient

        client = StarInfinityClient()
        mock_httpx = _make_mock_httpx_client()
        raw = {"id": "new123", "data": {"values": {}}}
        mock_httpx.request.return_value = _mock_response(raw)
        client._client = mock_httpx

        result = await client.create_item("board1", folder_id="f1", values={"name": "Task"})
        # unwrap=False so we get raw response
        assert result == raw

    async def test_list_boards_calls_correct_path(self):
        from agent1.integrations.starinfinity import StarInfinityClient

        client = StarInfinityClient()
        mock_httpx = _make_mock_httpx_client()
        mock_httpx.request.return_value = _mock_response({"data": [{"id": "b1", "name": "Board"}]})
        client._client = mock_httpx

        result = await client.list_boards()
        mock_httpx.request.assert_called_once_with("GET", "/boards", params=None, json=None)
        assert result == [{"id": "b1", "name": "Board"}]
