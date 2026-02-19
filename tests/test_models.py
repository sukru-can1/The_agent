"""Test Pydantic domain models."""

from __future__ import annotations

from uuid import UUID

from agent1.common.models import (
    ClassificationResult,
    Complexity,
    Event,
    EventSource,
    EventStatus,
    Priority,
)


class TestPriority:
    def test_ordering(self):
        assert Priority.CRITICAL < Priority.HIGH < Priority.MEDIUM < Priority.LOW < Priority.BACKGROUND

    def test_values(self):
        assert Priority.CRITICAL == 1
        assert Priority.HIGH == 3
        assert Priority.MEDIUM == 5
        assert Priority.LOW == 7
        assert Priority.BACKGROUND == 9


class TestEventSource:
    def test_values(self):
        assert EventSource.GMAIL == "gmail"
        assert EventSource.GCHAT == "gchat"
        assert EventSource.FRESHDESK == "freshdesk"
        assert EventSource.STARINFINITY == "starinfinity"
        assert EventSource.FEEDBACKS == "feedbacks"
        assert EventSource.SCHEDULER == "scheduler"


class TestEvent:
    def test_default_values(self):
        event = Event(source=EventSource.GMAIL, event_type="test")
        assert isinstance(event.id, UUID)
        assert event.status == EventStatus.PENDING
        assert event.priority == Priority.MEDIUM
        assert event.retry_count == 0
        assert event.error is None
        assert event.payload == {}
        assert event.created_at is not None

    def test_custom_values(self):
        event = Event(
            source=EventSource.FRESHDESK,
            event_type="ticket_created",
            priority=Priority.CRITICAL,
            payload={"ticket_id": 123},
            idempotency_key="fd:123",
        )
        assert event.source == EventSource.FRESHDESK
        assert event.priority == Priority.CRITICAL
        assert event.payload["ticket_id"] == 123
        assert event.idempotency_key == "fd:123"

    def test_serialization_roundtrip(self):
        event = Event(
            source=EventSource.GMAIL,
            event_type="new_email",
            payload={"subject": "Test"},
        )
        data = event.model_dump()
        restored = Event(**data)
        assert restored.id == event.id
        assert restored.source == event.source
        assert restored.payload == event.payload


class TestClassificationResult:
    def test_defaults(self):
        result = ClassificationResult(
            category="test",
            urgency=Priority.MEDIUM,
            complexity=Complexity.SIMPLE,
        )
        assert result.involves_vip is False
        assert result.involves_financial is False
        assert result.needs_response is False
        assert result.confidence == 0.0
        assert result.detected_language == "en"
        assert result.is_teachable_rule is False

    def test_full_classification(self):
        result = ClassificationResult(
            category="customer_complaint",
            urgency=Priority.CRITICAL,
            complexity=Complexity.COMPLEX,
            involves_vip=True,
            involves_financial=True,
            needs_response=True,
            confidence=0.95,
            detected_language="de",
            is_teachable_rule=False,
        )
        assert result.urgency == Priority.CRITICAL
        assert result.detected_language == "de"
        assert result.involves_vip is True
