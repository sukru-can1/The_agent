"""Tiered model selection based on task complexity."""

from __future__ import annotations

from agent1.common.models import ClassificationResult, Complexity, Event
from agent1.common.settings import get_settings


def _model(tier: str) -> str:
    """Return the model name for a given tier, respecting active provider."""
    settings = get_settings()
    prefix = "openrouter" if settings.llm_provider.lower() == "openrouter" else "gemini"
    return getattr(settings, f"{prefix}_model_{tier}")


def get_flash_model() -> str:
    """Return the flash-tier model (auto-response, trivial)."""
    return _model("flash")


def get_fast_model() -> str:
    """Return the fast-tier model (classification, planning)."""
    return _model("fast")


def select_model(classification: ClassificationResult, event: Event | None = None) -> str:
    """Select the appropriate model based on classification.

    Routing rules (4-tier):
    - Trivial (auto-response, quick Q&A) → flash
    - Simple (classification, planning) → fast
    - Moderate (email drafting, tool orchestration, chat) → default
    - Complex (VIP/financial, cross-system) → pro
    """
    # Always use Pro for VIP or financial matters
    if classification.involves_vip or classification.involves_financial:
        return _model("pro")

    # Chat messages that need a response should use at least default for tool use
    if event and event.source.value == "gchat" and classification.needs_response:
        if classification.complexity == Complexity.COMPLEX:
            return _model("pro")
        return _model("default")

    # Route by complexity
    if classification.complexity == Complexity.SIMPLE:
        return _model("fast")
    elif classification.complexity == Complexity.COMPLEX:
        return _model("pro")
    else:
        return _model("default")
