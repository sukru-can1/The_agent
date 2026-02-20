"""Tests for event classifier and JSON extraction."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent1.common.models import Complexity, Priority
from agent1.reasoning.classifier import _extract_json, _fix_truncated_json, classify_event
from agent1.reasoning.providers._base import LLMResponse


# ===========================================================================
# _extract_json tests
# ===========================================================================


class TestExtractJson:
    def test_clean_json(self):
        data = {"category": "spam", "urgency": 9}
        assert _extract_json(json.dumps(data)) == data

    def test_json_with_whitespace(self):
        assert _extract_json('  \n {"a": 1} \n  ') == {"a": 1}

    def test_markdown_fence_json(self):
        text = '```json\n{"category": "spam", "urgency": 9}\n```'
        assert _extract_json(text) == {"category": "spam", "urgency": 9}

    def test_markdown_fence_no_lang(self):
        text = '```\n{"category": "spam"}\n```'
        assert _extract_json(text) == {"category": "spam"}

    def test_leading_prose(self):
        text = 'Here is the classification:\n{"category": "spam", "urgency": 9}'
        result = _extract_json(text)
        assert result["category"] == "spam"

    def test_trailing_prose(self):
        text = '{"category": "spam", "urgency": 9}\n\nLet me know if you need more.'
        result = _extract_json(text)
        assert result["category"] == "spam"

    def test_prose_both_sides(self):
        text = 'Sure!\n```json\n{"x": 1}\n```\nHope that helps!'
        assert _extract_json(text) == {"x": 1}

    def test_truncated_string(self):
        """Gemini cuts off mid-string value."""
        text = '{"category": "delivery_issue", "urgency": 5, "reason": "The customer'
        result = _extract_json(text)
        assert result["category"] == "delivery_issue"
        assert result["urgency"] == 5

    def test_truncated_missing_closing_brace(self):
        text = '{"category": "spam", "urgency": 9'
        result = _extract_json(text)
        assert result["category"] == "spam"

    def test_trailing_comma(self):
        """Gemini sometimes leaves a trailing comma."""
        text = '{"category": "spam", "urgency": 9,}'
        result = _extract_json(text)
        assert result["category"] == "spam"

    def test_severely_truncated_bare_quote(self):
        """Gemini returns only opening brace + partial key."""
        text = '{\n  "'
        result = _extract_json(text)
        assert result == {}

    def test_severely_truncated_dangling_colon(self):
        """Gemini returns key + colon but no value."""
        text = '{\n  "category":'
        result = _extract_json(text)
        assert result == {}

    def test_truncated_second_key_dangling_colon(self):
        """First pair complete, second key has dangling colon."""
        text = '{"category": "spam", "urgency":'
        result = _extract_json(text)
        assert result == {"category": "spam"}

    def test_truncated_second_key_no_colon(self):
        """First pair complete, second key has no colon."""
        text = '{"category": "spam", "ur'
        result = _extract_json(text)
        assert result == {"category": "spam"}

    def test_multiline_truncated_with_trailing_comma(self):
        """Multi-line JSON truncated with trailing comma (production case)."""
        text = (
            '{\n  "category": "payment_problem",\n'
            '  "urgency": 1,\n'
            '  "complexity": "simple",\n'
            '  "involves_vip": false,'
        )
        result = _extract_json(text)
        assert result["category"] == "payment_problem"
        assert result["urgency"] == 1

    def test_raises_on_garbage(self):
        with pytest.raises(ValueError, match="No valid JSON"):
            _extract_json("This is not JSON at all")

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match="No valid JSON"):
            _extract_json("")


# ===========================================================================
# _fix_truncated_json tests
# ===========================================================================


class TestFixTruncatedJson:
    def test_closes_unterminated_string(self):
        result = _fix_truncated_json('{"a": "hello')
        assert result.endswith('"}"') or '"' in result

    def test_closes_open_braces(self):
        result = _fix_truncated_json('{"a": {"b": 1}')
        assert result.count("{") == result.count("}")

    def test_closes_open_brackets(self):
        result = _fix_truncated_json('{"a": [1, 2')
        assert result.count("[") == result.count("]")

    def test_removes_trailing_comma(self):
        result = _fix_truncated_json('{"a": 1, "b": 2,')
        assert not result.rstrip("}]").endswith(",")

    def test_removes_dangling_colon_after_comma(self):
        """Handles , "key": at end."""
        result = _fix_truncated_json('{"a": 1, "b":')
        parsed = json.loads(result)
        assert parsed == {"a": 1}

    def test_removes_dangling_key_after_comma(self):
        """Handles , "key" at end (no colon)."""
        result = _fix_truncated_json('{"a": 1, "b"')
        parsed = json.loads(result)
        assert parsed == {"a": 1}

    def test_removes_dangling_colon_first_entry(self):
        """Handles { "key": as only content."""
        result = _fix_truncated_json('{"category":')
        parsed = json.loads(result)
        assert parsed == {}

    def test_removes_dangling_key_first_entry(self):
        """Handles { "key" as only content."""
        result = _fix_truncated_json('{ "cat"')
        parsed = json.loads(result)
        assert parsed == {}

    def test_bare_quote_after_brace(self):
        """Handles { " (just a bare quote start, closed by unterminated string fix)."""
        result = _fix_truncated_json('{  "')
        parsed = json.loads(result)
        assert parsed == {}


# ===========================================================================
# classify_event tests
# ===========================================================================


class TestClassifier:
    async def test_fallback_when_no_api_key(self, sample_email_event):
        with patch(
            "agent1.reasoning.classifier.provider_available",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await classify_event(sample_email_event)
        assert result.category == sample_email_event.event_type
        assert result.urgency == sample_email_event.priority
        assert result.complexity == Complexity.MODERATE
        assert result.confidence == 0.5

    async def test_successful_classification(self, sample_email_event):
        json_data = {
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

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(
            return_value=LLMResponse(text=json.dumps(json_data))
        )

        with (
            patch(
                "agent1.reasoning.classifier.provider_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "agent1.reasoning.classifier.get_provider",
                new_callable=AsyncMock,
                return_value=mock_provider,
            ),
            patch("agent1.reasoning.classifier.get_fast_model", return_value="test-model"),
        ):
            result = await classify_event(sample_email_event)

        assert result.category == "delivery_issue"
        assert result.urgency == Priority.MEDIUM
        assert result.complexity == Complexity.SIMPLE
        assert result.confidence == 0.92
        assert result.detected_language == "en"

    async def test_handles_markdown_wrapped_json(self, sample_email_event):
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

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(
            return_value=LLMResponse(text=f"```json\n{json.dumps(json_data)}\n```")
        )

        with (
            patch(
                "agent1.reasoning.classifier.provider_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "agent1.reasoning.classifier.get_provider",
                new_callable=AsyncMock,
                return_value=mock_provider,
            ),
            patch("agent1.reasoning.classifier.get_fast_model", return_value="test-model"),
        ):
            result = await classify_event(sample_email_event)

        assert result.category == "spam"
        assert result.urgency == Priority.BACKGROUND

    async def test_handles_truncated_json(self, sample_email_event):
        """When LLM truncates output, classifier recovers what it can."""
        truncated = (
            '{"category": "customer_complaint", "urgency": 3, '
            '"complexity": "moderate", "involves_vip": false, '
            '"involves_financial": false, "needs_response": true, '
            '"confidence": 0.85, "detected_language": "en'
        )

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(
            return_value=LLMResponse(text=truncated)
        )

        with (
            patch(
                "agent1.reasoning.classifier.provider_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "agent1.reasoning.classifier.get_provider",
                new_callable=AsyncMock,
                return_value=mock_provider,
            ),
            patch("agent1.reasoning.classifier.get_fast_model", return_value="test-model"),
        ):
            result = await classify_event(sample_email_event)

        assert result.category == "customer_complaint"
        assert result.urgency == Priority.HIGH

    async def test_handles_api_error(self, sample_email_event):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(side_effect=Exception("API error"))

        with (
            patch(
                "agent1.reasoning.classifier.provider_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "agent1.reasoning.classifier.get_provider",
                new_callable=AsyncMock,
                return_value=mock_provider,
            ),
            patch("agent1.reasoning.classifier.get_fast_model", return_value="test-model"),
        ):
            result = await classify_event(sample_email_event)

        assert result.category == sample_email_event.event_type
        assert result.confidence == 0.0
