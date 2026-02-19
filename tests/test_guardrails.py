"""Test business rules / guardrails."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent1.common.models import (
    ClassificationResult,
    Complexity,
    Event,
    EventSource,
    Priority,
)
from agent1.guardrails.rules import check_business_rules


def _mock_settings(**overrides):
    settings = MagicMock()
    settings.restricted_contacts = overrides.get("restricted_contacts", [])
    return settings


class TestBusinessRules:
    @pytest.mark.asyncio
    async def test_normal_event_allowed(self, sample_email_event, sample_classification):
        with patch("agent1.guardrails.rules.get_settings", return_value=_mock_settings()):
            result = await check_business_rules(sample_email_event, sample_classification)
        assert result["allowed"] is True
        assert result["rule"] is None

    @pytest.mark.asyncio
    async def test_restricted_contact_blocked(self, sample_email_event, sample_classification):
        with patch(
            "agent1.guardrails.rules.get_settings",
            return_value=_mock_settings(restricted_contacts=["customer@example.com"]),
        ):
            result = await check_business_rules(sample_email_event, sample_classification)
        assert result["allowed"] is False
        assert result["rule"] == "restricted_contact"

    @pytest.mark.asyncio
    async def test_financial_topic_blocked(self, sample_email_event, financial_classification):
        with patch("agent1.guardrails.rules.get_settings", return_value=_mock_settings()):
            result = await check_business_rules(sample_email_event, financial_classification)
        assert result["allowed"] is False
        assert result["rule"] == "financial_topic"

    @pytest.mark.asyncio
    async def test_vip_allowed_but_flagged(self, sample_email_event, vip_classification):
        with patch("agent1.guardrails.rules.get_settings", return_value=_mock_settings()):
            result = await check_business_rules(sample_email_event, vip_classification)
        assert result["allowed"] is True
        assert result["rule"] == "vip_contact"

    @pytest.mark.asyncio
    async def test_legal_content_blocked(self, sample_classification):
        event = Event(
            source=EventSource.GMAIL,
            event_type="new_email",
            payload={
                "from_address": "someone@example.com",
                "subject": "Regarding the lawsuit against GLAMIRA",
                "body": "Please see the attached legal documents.",
            },
        )
        with patch("agent1.guardrails.rules.get_settings", return_value=_mock_settings()):
            result = await check_business_rules(event, sample_classification)
        assert result["allowed"] is False
        assert result["rule"] == "legal_content"

    @pytest.mark.asyncio
    async def test_high_value_order_flagged(self, sample_classification):
        event = Event(
            source=EventSource.FRESHDESK,
            event_type="ticket_created",
            payload={
                "from_address": "buyer@example.com",
                "subject": "Order inquiry",
                "body": "My order status please",
                "order_value": 8500,
            },
        )
        with patch("agent1.guardrails.rules.get_settings", return_value=_mock_settings()):
            result = await check_business_rules(event, sample_classification)
        assert result["allowed"] is True
        assert result["rule"] == "high_value_order"
