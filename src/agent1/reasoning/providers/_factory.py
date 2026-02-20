"""Provider factory — singleton that reads LLM_PROVIDER setting."""

from __future__ import annotations

from agent1.common.settings import get_settings
from agent1.reasoning.providers._base import LLMProvider

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Return the configured LLM provider (singleton)."""
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    name = settings.llm_provider.lower()

    if name == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        from agent1.reasoning.providers._openrouter import OpenRouterProvider

        _provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
    else:
        # Default: gemini
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        from agent1.reasoning.providers._gemini import GeminiProvider

        _provider = GeminiProvider(api_key=settings.gemini_api_key)

    return _provider


def provider_available() -> bool:
    """Check if the active provider's API key is configured."""
    settings = get_settings()
    name = settings.llm_provider.lower()
    if name == "openrouter":
        return bool(settings.openrouter_api_key)
    return bool(settings.gemini_api_key)


def reset_provider() -> None:
    """Reset the singleton (for testing)."""
    global _provider
    _provider = None
