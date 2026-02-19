"""Test event classifier."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent1.common.models import Complexity, Event, EventSource, Priority
from agent1.reasoning.classifier import classify_event


def _mock_settings(**overrides):
    settings = MagicMock()
    settings.anthropic_api_key = overrides.get("anthropic_api_key", "")
    settings.claude_model_haiku = overrides.get("claude_model_haiku", "claude-haiku-4-5-20251001")
    return settings


class TestClassifier:
    @pytest.mark.asyncio
    async def test_fallback_classification_no_api_key(self, sample_email_event):
        """Without API key, classifier returns fallback result."""
        with patch("agent1.reasoning.classifier.get_settings", return_value=_mock_settings()):
            result = await classify_event(sample_email_event)
        assert result.category == sample_email_event.event_type
        assert result.urgency == sample_email_event.priority
        assert result.complexity == Complexity.MODERATE
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_successful_classification(self, sample_email_event):
        """With API key, classifier parses Claude response."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "delivery_issue",
                        "urgency": 5,
                        "complexity": "simple",
                        "involves_vip": False,
                        "involves_financial": False,
                        "needs_response": True,
                        "confidence": 0.92,
                        "detected_language": "en",
                        "is_teachable_rule": False,
                    }
                )
            )
        ]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch("agent1.reasoning.classifier.get_settings", return_value=_mock_settings(anthropic_api_key="sk-test")),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await classify_event(sample_email_event)

        assert result.category == "delivery_issue"
        assert result.urgency == Priority.MEDIUM
        assert result.complexity == Complexity.SIMPLE
        assert result.confidence == 0.92
        assert result.detected_language == "en"

    @pytest.mark.asyncio
    async def test_classification_handles_api_error(self, sample_email_event):
        """When Claude API fails, classifier returns safe fallback."""
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        with (
            patch("agent1.reasoning.classifier.get_settings", return_value=_mock_settings(anthropic_api_key="sk-test")),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await classify_event(sample_email_event)

        assert result.category == sample_email_event.event_type
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_classification_handles_markdown_json(self, sample_email_event):
        """Classifier strips markdown code fences from JSON."""
        json_data = {
            "category": "spam",
            "urgency": 9,
            "complexity": "simple",
            "involves_vip": False,
            "involves_financial": False,
            "needs_response": False,
            "confidence": 0.99,
            "detected_language": "en",
            "is_teachable_rule": False,
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=f"```json\n{json.dumps(json_data)}\n```")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch("agent1.reasoning.classifier.get_settings", return_value=_mock_settings(anthropic_api_key="sk-test")),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await classify_event(sample_email_event)

        assert result.category == "spam"
        assert result.urgency == Priority.BACKGROUND
