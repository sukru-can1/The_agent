"""Test business rules / guardrails."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent1.common.models import (
    ClassificationResult,
    Complexity,
    Event,
    EventSource,
    Priority,
)
from agent1.guardrails.engine import check_guardrails
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


class TestGuardrailsEngine:
    @pytest.mark.asyncio
    async def test_financial_block_creates_proposal(self, sample_freshdesk_event, financial_classification):
        """When a financial event is blocked, a guardrail_override proposal should be created."""
        with patch("agent1.guardrails.engine.check_business_rules") as mock_rules:
            mock_rules.return_value = {
                "allowed": False,
                "rule": "financial_topic",
                "reason": "Financial topics require manual approval",
            }
            with patch("agent1.guardrails.engine.check_rate_limits") as mock_rates:
                mock_rates.return_value = {"allowed": True}
                with patch("agent1.guardrails.engine._notify_block", new_callable=AsyncMock) as mock_notify:
                    result = await check_guardrails(sample_freshdesk_event, financial_classification)

        assert result is False
        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_allowed_event_no_notification(self, sample_email_event, sample_classification):
        """Normal events should not trigger block notifications."""
        with patch("agent1.guardrails.engine.check_business_rules") as mock_rules:
            mock_rules.return_value = {"allowed": True, "rule": None, "reason": None}
            with patch("agent1.guardrails.engine.check_rate_limits") as mock_rates:
                mock_rates.return_value = {"allowed": True}
                result = await check_guardrails(sample_email_event, sample_classification)

        assert result is True
