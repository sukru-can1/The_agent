"""Tests for model routing logic."""

from unittest.mock import AsyncMock, patch

import agent1.common.settings as s
from agent1.common.models import ClassificationResult, Complexity, Event, EventSource, Priority
from agent1.reasoning.router import get_fast_model, get_flash_model, select_model


def _reset_settings(monkeypatch, **env_vars):
    """Reset settings singleton and apply env vars."""
    for key, val in env_vars.items():
        monkeypatch.setenv(key, val)
    s._settings = None


def _mock_redis(provider: str):
    """Return a patch that makes get_active_provider_name return the given provider."""
    return patch(
        "agent1.reasoning.providers.get_active_provider_name",
        new_callable=AsyncMock,
        return_value=provider,
    )


async def test_simple_uses_fast_model(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
    )
    with _mock_redis("gemini"):
        model = await select_model(result)
    assert model == "gemini-2.5-flash"


async def test_complex_uses_pro_model(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="cross_system",
        urgency=Priority.HIGH,
        complexity=Complexity.COMPLEX,
    )
    with _mock_redis("gemini"):
        model = await select_model(result)
    assert model == "gemini-3-pro"


async def test_vip_always_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_vip=True,
    )
    with _mock_redis("gemini"):
        model = await select_model(result)
    assert model == "gemini-3-pro"


async def test_financial_always_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_financial=True,
    )
    with _mock_redis("gemini"):
        model = await select_model(result)
    assert model == "gemini-3-pro"


async def test_moderate_uses_default(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")

    result = ClassificationResult(
        category="customer_complaint",
        urgency=Priority.MEDIUM,
        complexity=Complexity.MODERATE,
    )
    with _mock_redis("gemini"):
        model = await select_model(result)
    assert model == "gemini-2.5-pro"


async def test_chat_event_uses_default(monkeypatch):
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
    with _mock_redis("gemini"):
        model = await select_model(classification, event)
    assert model == "gemini-2.5-pro"


# --- OpenRouter routing ---


async def test_openrouter_simple_uses_fast(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
    )
    with _mock_redis("openrouter"):
        model = await select_model(result)
    assert model == "moonshotai/kimi-k2.5"


async def test_openrouter_complex_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")

    result = ClassificationResult(
        category="cross_system",
        urgency=Priority.HIGH,
        complexity=Complexity.COMPLEX,
    )
    with _mock_redis("openrouter"):
        model = await select_model(result)
    assert model == "moonshotai/kimi-k2-thinking"


async def test_openrouter_vip_uses_pro(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")

    result = ClassificationResult(
        category="routine",
        urgency=Priority.LOW,
        complexity=Complexity.SIMPLE,
        involves_vip=True,
    )
    with _mock_redis("openrouter"):
        model = await select_model(result)
    assert model == "moonshotai/kimi-k2-thinking"


# --- Helper functions ---


async def test_get_flash_model_gemini(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")
    with _mock_redis("gemini"):
        assert await get_flash_model() == "gemini-2.0-flash"


async def test_get_fast_model_gemini(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="gemini")
    with _mock_redis("gemini"):
        assert await get_fast_model() == "gemini-2.5-flash"


async def test_get_flash_model_openrouter(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")
    with _mock_redis("openrouter"):
        assert await get_flash_model() == "google/gemini-2.5-flash"


async def test_get_fast_model_openrouter(monkeypatch):
    _reset_settings(monkeypatch, LLM_PROVIDER="openrouter")
    with _mock_redis("openrouter"):
        assert await get_fast_model() == "moonshotai/kimi-k2.5"
