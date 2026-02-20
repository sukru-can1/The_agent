"""LLM provider abstraction — swap between Gemini and OpenRouter via env var."""

from agent1.reasoning.providers._base import LLMProvider, LLMResponse, ToolCall
from agent1.reasoning.providers._factory import (
    get_active_provider_name,
    get_provider,
    provider_available,
    reset_provider,
    set_provider_override,
)

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "get_active_provider_name",
    "get_provider",
    "provider_available",
    "reset_provider",
    "set_provider_override",
]
