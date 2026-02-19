"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from agent1.common.models import (
    ClassificationResult,
    Complexity,
    Event,
    EventSource,
    Priority,
)


@pytest.fixture
def sample_email_event() -> Event:
    return Event(
        source=EventSource.GMAIL,
        event_type="new_email",
        priority=Priority.MEDIUM,
        payload={
            "message_id": "msg_123",
            "from_address": "customer@example.com",
            "subject": "Order status inquiry",
            "body": "Hi, I ordered a ring 3 days ago and have no tracking info.",
            "thread_id": "thread_456",
        },
        idempotency_key="gmail:msg_123",
    )


@pytest.fixture
def sample_chat_event() -> Event:
    return Event(
        source=EventSource.GCHAT,
        event_type="chat_message",
        priority=Priority.MEDIUM,
        payload={
            "space": "spaces/abc",
            "thread": "spaces/abc/threads/123",
            "sender": "Sukru",
            "sender_email": "sukru@glamira.com",
            "text": "What is the status of the DE queue?",
        },
        idempotency_key="gchat:msg_789",
    )


@pytest.fixture
def sample_teachable_event() -> Event:
    return Event(
        source=EventSource.GCHAT,
        event_type="teachable_rule",
        priority=Priority.HIGH,
        payload={
            "space": "spaces/abc",
            "thread": "spaces/abc/threads/123",
            "sender": "Sukru",
            "sender_email": "sukru@glamira.com",
            "text": "From now on, always CC logistics@glamira.com on shipping complaints.",
        },
    )


@pytest.fixture
def sample_freshdesk_event() -> Event:
    return Event(
        source=EventSource.FRESHDESK,
        event_type="ticket_created",
        priority=Priority.HIGH,
        payload={
            "ticket_id": 12345,
            "subject": "Missing diamond on engagement ring",
            "description": "I received my ring and the center diamond is missing.",
            "priority": 3,
            "status": 2,
            "requester_email": "vip@example.com",
        },
    )


@pytest.fixture
def sample_classification() -> ClassificationResult:
    return ClassificationResult(
        category="customer_complaint",
        urgency=Priority.HIGH,
        complexity=Complexity.MODERATE,
        involves_vip=False,
        involves_financial=False,
        needs_response=True,
        confidence=0.9,
        detected_language="en",
    )


@pytest.fixture
def financial_classification() -> ClassificationResult:
    return ClassificationResult(
        category="payment_problem",
        urgency=Priority.CRITICAL,
        complexity=Complexity.COMPLEX,
        involves_vip=False,
        involves_financial=True,
        needs_response=True,
        confidence=0.95,
    )


@pytest.fixture
def vip_classification() -> ClassificationResult:
    return ClassificationResult(
        category="customer_complaint",
        urgency=Priority.HIGH,
        complexity=Complexity.MODERATE,
        involves_vip=True,
        involves_financial=False,
        needs_response=True,
        confidence=0.85,
    )
