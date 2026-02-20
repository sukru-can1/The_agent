"""Tests for feedbacks REST API tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ── Helper Tests ────────────────────────────────────────────


class TestUnwrap:
    def test_extracts_data_from_envelope(self):
        from agent1.tools.feedbacks import _unwrap

        envelope = {"app": "feedbacks", "timestamp": "2024-01-01", "data": {"count": 5}}
        assert _unwrap(envelope) == {"count": 5}

    def test_passes_through_if_no_data_key(self):
        from agent1.tools.feedbacks import _unwrap

        raw = {"count": 5, "items": []}
        assert _unwrap(raw) == {"count": 5, "items": []}


# ── Not-Configured Tests ────────────────────────────────────


class TestNotConfigured:
    @pytest.mark.parametrize(
        "tool_cls",
        [
            "FeedbacksGetInsightsTool",
            "FeedbacksGetOverviewTool",
            "FeedbacksGetTrustpilotReviewsTool",
            "FeedbacksGetTasksTool",
            "FeedbacksGetSurveyResponsesTool",
            "FeedbacksStartAutoReporterTool",
            "FeedbacksTriggerTrustpilotSyncTool",
        ],
    )
    async def test_returns_error_when_api_key_empty(self, tool_cls):
        import agent1.tools.feedbacks as mod

        cls = getattr(mod, tool_cls)
        tool = cls()

        with patch("agent1.tools.feedbacks.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(feedbacks_api_key="", feedbacks_api_url="https://x")
            # Provide required params for tools that need them
            kwargs = {}
            if tool_cls == "FeedbacksGetSurveyResponsesTool":
                kwargs["survey_id"] = "abc"
            result = await tool.execute(**kwargs)

        assert "error" in result


# ── Mock helpers ────────────────────────────────────────────


def _mock_response(json_data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_http_error_response(status_code=500):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = {"error": "server error"}
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=resp
    )
    return resp


def _patch_settings(**overrides):
    defaults = {
        "feedbacks_api_url": "https://survey.glamira.com/api/v1",
        "feedbacks_api_key": "test-key",
    }
    defaults.update(overrides)
    return patch("agent1.tools.feedbacks.get_settings", return_value=MagicMock(**defaults))


def _patch_client(mock_client):
    """Patch httpx.AsyncClient to return our mock."""
    return patch("agent1.tools.feedbacks.httpx.AsyncClient", return_value=mock_client)


def _make_mock_client():
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ── FeedbacksGetInsightsTool Tests ──────────────────────────


class TestFeedbacksGetInsightsTool:
    async def test_success_with_params(self):
        from agent1.tools.feedbacks import FeedbacksGetInsightsTool

        tool = FeedbacksGetInsightsTool()
        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_response({
            "app": "feedbacks",
            "timestamp": "2024-01-01",
            "data": {
                "period": {"days": 7},
                "alerts": [{"type": "csat_drop", "severity": "warning"}],
            },
        })

        with _patch_settings(), _patch_client(mock_client):
            result = await tool.execute(days=7, threshold=0.3, min_sample=10)

        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == "/insights"
        assert call_args[1]["params"]["days"] == 7
        assert call_args[1]["params"]["threshold"] == 0.3
        assert call_args[1]["params"]["minSample"] == 10
        assert "alerts" in result

    async def test_http_error(self):
        from agent1.tools.feedbacks import FeedbacksGetInsightsTool

        tool = FeedbacksGetInsightsTool()
        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_http_error_response(502)

        with _patch_settings(), _patch_client(mock_client):
            result = await tool.execute()

        assert "error" in result
        assert "502" in result["error"]

    async def test_network_error(self):
        from agent1.tools.feedbacks import FeedbacksGetInsightsTool

        tool = FeedbacksGetInsightsTool()
        mock_client = _make_mock_client()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with _patch_settings(), _patch_client(mock_client):
            result = await tool.execute()

        assert "error" in result


# ── FeedbacksGetTrustpilotReviewsTool Tests ─────────────────


class TestFeedbacksGetTrustpilotReviewsTool:
    async def test_success(self):
        from agent1.tools.feedbacks import FeedbacksGetTrustpilotReviewsTool

        tool = FeedbacksGetTrustpilotReviewsTool()
        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_response({
            "data": {
                "reviews": [
                    {"id": 1, "stars": 1, "title": "Bad", "isDefendable": True},
                ],
                "pagination": {"total": 1},
            },
        })

        with _patch_settings(), _patch_client(mock_client):
            result = await tool.execute(max_stars=2, status="new", limit=10)

        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["maxStars"] == 2
        assert call_args[1]["params"]["status"] == "new"
        assert "reviews" in result


# ── FeedbacksGetSurveyResponsesTool Tests ────────────────────


class TestFeedbacksGetSurveyResponsesTool:
    async def test_requires_survey_id_and_builds_url(self):
        from agent1.tools.feedbacks import FeedbacksGetSurveyResponsesTool

        tool = FeedbacksGetSurveyResponsesTool()
        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_response({
            "data": {"responses": [], "pagination": {}},
        })

        with _patch_settings(), _patch_client(mock_client):
            result = await tool.execute(survey_id="srv_123", page=2, limit=25)

        call_args = mock_client.get.call_args
        assert call_args[0][0] == "/surveys/srv_123/responses"
        assert call_args[1]["params"]["page"] == 2


# ── FeedbacksStartAutoReporterTool Tests ─────────────────────


class TestFeedbacksStartAutoReporterTool:
    async def test_posts_with_count(self):
        from agent1.tools.feedbacks import FeedbacksStartAutoReporterTool

        tool = FeedbacksStartAutoReporterTool()
        mock_client = _make_mock_client()
        mock_client.post.return_value = _mock_response({"data": {"started": True}})

        with _patch_settings(), _patch_client(mock_client):
            result = await tool.execute(count=5)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/actions/auto-reporter-start"
        assert call_args[1]["json"]["count"] == 5


# ── FeedbacksTriggerTrustpilotSyncTool Tests ─────────────────


class TestFeedbacksTriggerTrustpilotSyncTool:
    async def test_posts_to_correct_url(self):
        from agent1.tools.feedbacks import FeedbacksTriggerTrustpilotSyncTool

        tool = FeedbacksTriggerTrustpilotSyncTool()
        mock_client = _make_mock_client()
        mock_client.post.return_value = _mock_response({"data": {"synced": 12}})

        with _patch_settings(), _patch_client(mock_client):
            result = await tool.execute()

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/actions/trustpilot-sync"
