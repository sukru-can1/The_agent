"""Tiered model selection based on task complexity."""

from __future__ import annotations

from __future__ import annotations

from agent1.common.models import ClassificationResult, Complexity, Event
from agent1.common.settings import get_settings


def select_model(classification: ClassificationResult, event: "Event | None" = None) -> str:
    """Select the appropriate Gemini model based on classification.

    Routing rules (4-tier):
    - Trivial (auto-response, quick Q&A) → gemini-2.0-flash
    - Simple (classification, planning) → gemini-2.5-flash
    - Moderate (email drafting, tool orchestration, chat) → gemini-2.5-pro
    - Complex (VIP/financial, cross-system) → gemini-3-pro
    """
    settings = get_settings()

    # Always use Pro for VIP or financial matters
    if classification.involves_vip or classification.involves_financial:
        return settings.gemini_model_pro

    # Chat messages that need a response should use at least default for tool use
    if event and event.source.value == "gchat" and classification.needs_response:
        if classification.complexity == Complexity.COMPLEX:
            return settings.gemini_model_pro
        return settings.gemini_model_default

    # Route by complexity
    if classification.complexity == Complexity.SIMPLE:
        return settings.gemini_model_fast
    elif classification.complexity == Complexity.COMPLEX:
        return settings.gemini_model_pro
    else:
        return settings.gemini_model_default
