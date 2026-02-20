"""Provider factory — singleton with Redis-backed override for cross-process switching."""

from __future__ import annotations

from agent1.common.settings import get_settings
from agent1.reasoning.providers._base import LLMProvider

_provider: LLMProvider | None = None
_cached_provider_name: str | None = None  # tracks which provider the singleton is for

REDIS_KEY = "agent1:llm_provider"


async def _read_redis_override() -> str | None:
    """Read provider override from Redis (shared across webhook + worker)."""
    try:
        from agent1.common.redis_client import get_redis
        redis = await get_redis()
        val = await redis.get(REDIS_KEY)
        if val:
            return val.decode() if isinstance(val, bytes) else val
    except Exception:
        pass
    return None


async def _write_redis_override(name: str | None) -> None:
    """Write provider override to Redis."""
    from agent1.common.redis_client import get_redis
    redis = await get_redis()
    if name:
        await redis.set(REDIS_KEY, name)
    else:
        await redis.delete(REDIS_KEY)


async def _active_provider_name() -> str:
    """Return the active provider name (Redis override > env var)."""
    override = await _read_redis_override()
    if override:
        return override.lower()
    return get_settings().llm_provider.lower()


def _active_provider_name_sync() -> str:
    """Sync version — reads cached name or falls back to env var.

    Used by provider_available() which is called in sync contexts.
    """
    if _cached_provider_name:
        return _cached_provider_name
    return get_settings().llm_provider.lower()


async def get_provider() -> LLMProvider:
    """Return the configured LLM provider (singleton, checks Redis for override)."""
    global _provider, _cached_provider_name

    name = await _active_provider_name()

    # If singleton exists but for a different provider, reset it
    if _provider is not None and _cached_provider_name == name:
        return _provider

    settings = get_settings()
    _provider = None

    if name == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter"
            )
        from agent1.reasoning.providers._openrouter import OpenRouterProvider
        _provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
    else:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required when LLM_PROVIDER=gemini"
            )
        from agent1.reasoning.providers._gemini import GeminiProvider
        _provider = GeminiProvider(api_key=settings.gemini_api_key)

    _cached_provider_name = name
    return _provider


async def provider_available() -> bool:
    """Check if the active provider's API key is configured."""
    settings = get_settings()
    name = await _active_provider_name()
    if name == "openrouter":
        return bool(settings.openrouter_api_key)
    return bool(settings.gemini_api_key)


async def get_active_provider_name() -> str:
    """Return the current provider name (for status endpoints)."""
    return await _active_provider_name()


async def set_provider_override(name: str | None) -> None:
    """Set a runtime override via Redis. Both webhook + worker see it."""
    global _provider, _cached_provider_name
    await _write_redis_override(name)
    _provider = None
    _cached_provider_name = None


def reset_provider() -> None:
    """Reset the singleton (for testing)."""
    global _provider, _cached_provider_name
    _provider = None
    _cached_provider_name = None
