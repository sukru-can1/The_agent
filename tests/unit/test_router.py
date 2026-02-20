"""Tests for model routing logic."""

import agent1.common.settings as s
from agent1.common.models import ClassificationResult, Complexity, Event, EventSource, Priority
from agent1.reasoning.router import get_fast_model, get_flash_model, select_model


def _reset_settings(monkeypatch, **env_vars):
    """Reset settings singleton and apply env vars."""
    for key, val in env_vars.items():
        monkeypatch.setenv(key, val)
    s._settings = None


def test_simple_uses_fast_model(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
    )
    model = select_model(result)
    assert model == "gemini-2.5-flash"


def test_complex_uses_pro_model(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="cross_system",
        urgency=Priority.HIGH,
        complexity=Complexity.COMPLEX,
    )
    model = select_model(result)
    assert model == "gemini-3-pro"


def test_vip_always_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_vip=True,
    )
    model = select_model(result)
    assert model == "gemini-3-pro"


def test_financial_always_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_financial=True,
    )
    model = select_model(result)
    assert model == "gemini-3-pro"


def test_moderate_uses_default(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="customer_complaint",
        urgency=Priority.MEDIUM,
        complexity=Complexity.MODERATE,
    )
    model = select_model(result)
    assert model == "gemini-2.5-pro"


def test_chat_event_uses_default(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    classification = ClassificationResult(
        category="question",
        urgency=Priority.MEDIUM,
        complexity=Complexity.MODERATE,
        needs_response=True,
    )
    event = Event(
        source=EventSource.GCHAT,
        event_type="chat_message",
        priority=Priority.MEDIUM,
        payload={"text": "hi"},
    )
    model = select_model(classification, event)
    assert model == "gemini-2.5-pro"


# --- OpenRouter routing ---


def test_openrouter_simple_uses_fast(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
    )
    model = select_model(result)
    assert model == "anthropic/claude-haiku-4"


def test_openrouter_complex_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")

    result = ClassificationResult(
        category="cross_system",
        urgency=Priority.HIGH,
        complexity=Complexity.COMPLEX,
    )
    model = select_model(result)
    assert model == "anthropic/claude-opus-4"


def test_openrouter_vip_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_vip=True,
    )
    model = select_model(result)
    assert model == "anthropic/claude-opus-4"


# --- Helper functions ---


def test_get_flash_model_gemini(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")
    assert get_flash_model() == "gemini-2.0-flash"


def test_get_fast_model_gemini(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")
    assert get_fast_model() == "gemini-2.5-flash"


def test_get_flash_model_openrouter(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")
    assert get_flash_model() == "google/gemini-2.0-flash-001"


def test_get_fast_model_openrouter(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")
    assert get_fast_model() == "anthropic/claude-haiku-4"
