"""Tests for feedbacks poller (REST API version)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _mock_response(json_data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _make_mock_client():
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _patch_settings(**overrides):
    defaults = {
        "feedbacks_api_url": "https://survey.glamira.com/api/v1",
        "feedbacks_api_key": "test-key",
    }
    defaults.update(overrides)
    return patch(
        "agent1.worker.pollers.feedbacks_poller.get_settings",
        return_value=MagicMock(**defaults),
    )


class TestPollFeedbacksSkips:
    async def test_skips_when_api_key_empty(self):
        from agent1.worker.pollers.feedbacks_poller import poll_feedbacks

        with _patch_settings(feedbacks_api_key=""):
            # Should not raise, just silently skip
            await poll_feedbacks()

    async def test_handles_network_error_gracefully(self):
        from agent1.worker.pollers.feedbacks_poller import poll_feedbacks

        mock_client = _make_mock_client()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with (
            _patch_settings(),
            patch("agent1.worker.pollers.feedbacks_poller.httpx.AsyncClient", return_value=mock_client),
        ):
            # Should not raise
            await poll_feedbacks()


class TestPollNewComplaints:
    async def test_publishes_event_when_new_complaints(self):
        from agent1.worker.pollers.feedbacks_poller import _poll_new_complaints

        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_response({
            "data": {
                "complaints": {"new": 3, "in_progress": 1, "done": 10},
            },
        })

        mock_publish = AsyncMock()
        mock_is_dup = AsyncMock(return_value=False)
        mock_mark = AsyncMock()

        with (
            patch("agent1.worker.pollers.feedbacks_poller.publish_event", mock_publish),
            patch("agent1.worker.pollers.feedbacks_poller.is_duplicate", mock_is_dup),
            patch("agent1.worker.pollers.feedbacks_poller.mark_processed", mock_mark),
        ):
            await _poll_new_complaints(mock_client)

        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert event.event_type == "new_complaints"
        assert event.payload["new_count"] == 3

        # Verify 2-arg dedup calls
        mock_is_dup.assert_called_once()
        assert mock_is_dup.call_args[0][0] == "feedbacks"
        mock_mark.assert_called_once()
        assert mock_mark.call_args[0][0] == "feedbacks"


class TestPollTrustpilotReviews:
    async def test_publishes_events_for_low_star_reviews(self):
        from agent1.worker.pollers.feedbacks_poller import _poll_trustpilot_reviews

        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_response({
            "data": {
                "reviews": [
                    {
                        "id": "r1",
                        "trustpilotId": "tp1",
                        "title": "Terrible",
                        "stars": 1,
                        "reviewerName": "John",
                        "reviewerCountry": "DE",
                        "isDefendable": True,
                    },
                    {
                        "id": "r2",
                        "trustpilotId": "tp2",
                        "title": "Bad",
                        "stars": 2,
                        "reviewerName": "Jane",
                        "reviewerCountry": "US",
                        "isDefendable": False,
                    },
                ],
                "pagination": {"total": 2},
            },
        })

        mock_publish = AsyncMock()
        mock_is_dup = AsyncMock(return_value=False)
        mock_mark = AsyncMock()

        with (
            patch("agent1.worker.pollers.feedbacks_poller.publish_event", mock_publish),
            patch("agent1.worker.pollers.feedbacks_poller.is_duplicate", mock_is_dup),
            patch("agent1.worker.pollers.feedbacks_poller.mark_processed", mock_mark),
        ):
            await _poll_trustpilot_reviews(mock_client)

        assert mock_publish.call_count == 2
        # All dedup calls should use 2 args
        for call in mock_is_dup.call_args_list:
            assert call[0][0] == "feedbacks"

    async def test_deduplicates_reviews(self):
        from agent1.worker.pollers.feedbacks_poller import _poll_trustpilot_reviews

        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_response({
            "data": {
                "reviews": [
                    {"id": "r1", "trustpilotId": "tp1", "title": "Bad", "stars": 1,
                     "reviewerName": "John", "reviewerCountry": "DE", "isDefendable": False},
                ],
            },
        })

        mock_publish = AsyncMock()
        mock_is_dup = AsyncMock(return_value=True)  # Already seen

        with (
            patch("agent1.worker.pollers.feedbacks_poller.publish_event", mock_publish),
            patch("agent1.worker.pollers.feedbacks_poller.is_duplicate", mock_is_dup),
            patch("agent1.worker.pollers.feedbacks_poller.mark_processed", AsyncMock()),
        ):
            await _poll_trustpilot_reviews(mock_client)

        mock_publish.assert_not_called()


class TestCheckTrustpilotSpikes:
    async def test_publishes_critical_when_spike(self):
        from agent1.worker.pollers.feedbacks_poller import _check_trustpilot_spikes

        mock_client = _make_mock_client()
        mock_client.get.return_value = _mock_response({
            "data": {
                "byStatus": {"new": 5, "responded": 10},
                "total": 15,
            },
        })

        mock_publish = AsyncMock()
        mock_is_dup = AsyncMock(return_value=False)
        mock_mark = AsyncMock()

        with (
            patch("agent1.worker.pollers.feedbacks_poller.publish_event", mock_publish),
            patch("agent1.worker.pollers.feedbacks_poller.is_duplicate", mock_is_dup),
            patch("agent1.worker.pollers.feedbacks_poller.mark_processed", mock_mark),
        ):
            await _check_trustpilot_spikes(mock_client)

        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert event.priority.name == "CRITICAL"
        assert event.payload["negative_review_count"] == 5
