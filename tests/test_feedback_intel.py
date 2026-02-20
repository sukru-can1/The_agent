"""Tests for feedback intelligence — qualitative edit analysis."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


from agent1.intelligence.feedback_intel import (
    analyze_edit,
    analyze_rejection,
    _parse_rules_from_response,
)


def test_parse_rules_from_response_extracts_rules():
    response = """Here are the changes:
RULE: Use first name instead of formal greeting for .de customers
RULE: Keep response under 3 paragraphs
RULE: Always reference the order number"""
    rules = _parse_rules_from_response(response)
    assert len(rules) == 3
    assert "first name" in rules[0]


def test_parse_rules_empty_response():
    rules = _parse_rules_from_response("")
    assert rules == []


def test_parse_rules_no_rules_in_response():
    rules = _parse_rules_from_response("The edits were minor formatting changes.")
    assert rules == []


@pytest.mark.asyncio
async def test_analyze_edit_creates_proposals():
    with patch("agent1.intelligence.feedback_intel._call_flash", new_callable=AsyncMock) as mock_flash:
        mock_flash.return_value = "RULE: Use casual tone for .de customers"
        with patch("agent1.intelligence.feedback_intel.create_proposal", new_callable=AsyncMock) as mock_create:
            from uuid import uuid4
            mock_create.return_value = uuid4()

            await analyze_edit(
                draft_id=1,
                original="Dear valued customer, we sincerely apologize...",
                edited="Hi Maria, sorry about this...",
                sender_domain="example.de",
                category="customer_complaint",
            )

    mock_flash.assert_called_once()
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_rejection_creates_proposal():
    with patch("agent1.intelligence.feedback_intel._call_flash", new_callable=AsyncMock) as mock_flash:
        mock_flash.return_value = "RULE: Never draft a response for legal inquiries"
        with patch("agent1.intelligence.feedback_intel.create_proposal", new_callable=AsyncMock) as mock_create:
            from uuid import uuid4
            mock_create.return_value = uuid4()

            await analyze_rejection(
                draft_id=2,
                draft_body="We can help with your legal question...",
                event_payload={"subject": "Legal inquiry about warranty"},
                rejection_reason="This should not have been drafted at all",
            )

    mock_create.assert_called_once()
