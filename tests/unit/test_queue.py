"""Tests for event queue scoring and key generation."""

from agent1.common.models import Priority
from agent1.queue.events import compute_score, dedup_key, event_hash_key, lock_key


def test_compute_score_priority_ordering():
    """Higher priority (lower number) should have lower score."""
    critical = compute_score(Priority.CRITICAL, 1000)
    high = compute_score(Priority.HIGH, 1000)
    medium = compute_score(Priority.MEDIUM, 1000)

    assert critical < high < medium


def test_compute_score_same_priority_time_ordering():
    """For same priority, earlier timestamp should have lower score."""
    earlier = compute_score(Priority.MEDIUM, 1000)
    later = compute_score(Priority.MEDIUM, 2000)

    assert earlier < later


def test_event_hash_key():
    assert event_hash_key("abc-123") == "agent1:event:abc-123"


def test_dedup_key():
    assert dedup_key("gmail", "msg123") == "agent1:dedup:gmail:msg123"


def test_lock_key():
    assert lock_key("event:abc") == "agent1:lock:event:abc"
