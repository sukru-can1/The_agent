"""Tests for Pydantic domain models."""

from agent1.common.models import (
    ClassificationResult,
    Complexity,
    Event,
    EventSource,
    EventStatus,
    Priority,
)


def test_event_creation():
    event = Event(
        source=EventSource.GMAIL,
        event_type="new_email",
        priority=Priority.HIGH,
        payload={"subject": "Test"},
    )
    assert event.source == EventSource.GMAIL
    assert event.priority == Priority.HIGH
    assert event.status == EventStatus.PENDING
    assert event.retry_count == 0
    assert event.payload["subject"] == "Test"


def test_event_defaults():
    event = Event(source=EventSource.SCHEDULER, event_type="tick")
    assert event.priority == Priority.MEDIUM
    assert event.idempotency_key == ""


def test_classification_result():
    result = ClassificationResult(
        category="customer_complaint",
        urgency=Priority.CRITICAL,
        complexity=Complexity.COMPLEX,
        involves_vip=True,
        involves_financial=False,
        needs_response=True,
        confidence=0.95,
    )
    assert result.involves_vip
    assert result.complexity == Complexity.COMPLEX


def test_priority_ordering():
    assert Priority.CRITICAL < Priority.HIGH < Priority.MEDIUM < Priority.LOW < Priority.BACKGROUND
