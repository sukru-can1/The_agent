"""Tiered model selection based on task complexity."""

from __future__ import annotations

from agent1.common.models import ClassificationResult, Complexity, Event
from agent1.common.settings import get_settings


async def _model(tier: str) -> str:
    """Return the model name for a given tier, respecting active provider (including Redis override)."""
    from agent1.reasoning.providers import get_active_provider_name

    settings = get_settings()
    prefix = await get_active_provider_name()
    return getattr(settings, f"{prefix}_model_{tier}")


async def get_flash_model() -> str:
    """Return the flash-tier model (auto-response, trivial)."""
    return await _model("flash")


async def get_fast_model() -> str:
    """Return the fast-tier model (classification, planning)."""
    return await _model("fast")


async def select_model(classification: ClassificationResult, event: Event | None = None) -> str:
    """Select the appropriate model based on classification.

    Routing rules (4-tier):
    - Trivial (auto-response, quick Q&A) → flash
    - Simple (classification, planning) → fast
    - Moderate (email drafting, tool orchestration, chat) → default
    - Complex (VIP/financial, cross-system) → pro
    """
    # Always use Pro for VIP or financial matters
    if classification.involves_vip or classification.involves_financial:
        return await _model("pro")

    # Chat messages that need a response should use at least default for tool use
    if event and event.source.value == "gchat" and classification.needs_response:
        if classification.complexity == Complexity.COMPLEX:
            return await _model("pro")
        return await _model("default")

    # Route by complexity
    if classification.complexity == Complexity.SIMPLE:
        return await _model("fast")
    elif classification.complexity == Complexity.COMPLEX:
        return await _model("pro")
    else:
        return await _model("default")
