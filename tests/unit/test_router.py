"""Tests for model routing logic."""

from agent1.common.models import ClassificationResult, Complexity, Priority
from agent1.reasoning.router import select_model


def test_simple_uses_haiku(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    import agent1.common.settings as s
    s._settings = None

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
    )
    model = select_model(result)
    assert "haiku" in model


def test_complex_uses_opus(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    import agent1.common.settings as s
    s._settings = None

    result = ClassificationResult(
        category="cross_system",
        urgency=Priority.HIGH,
        complexity=Complexity.COMPLEX,
    )
    model = select_model(result)
    assert "opus" in model


def test_vip_always_uses_opus(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    import agent1.common.settings as s
    s._settings = None

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_vip=True,
    )
    model = select_model(result)
    assert "opus" in model


def test_financial_always_uses_opus(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    import agent1.common.settings as s
    s._settings = None

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_financial=True,
    )
    model = select_model(result)
    assert "opus" in model
