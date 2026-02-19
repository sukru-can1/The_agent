"""Tiered model selection based on task complexity."""

from __future__ import annotations

from __future__ import annotations

from agent1.common.models import ClassificationResult, Complexity, Event
from agent1.common.settings import get_settings


def select_model(classification: ClassificationResult, event: "Event | None" = None) -> str:
    """Select the appropriate Claude model based on classification.

    Routing rules:
    - Simple tasks (classification, simple Q&A) → Haiku
    - Moderate tasks (email drafting, tool orchestration) → Sonnet
    - Complex tasks (VIP/legal/financial, cross-system correlation) → Opus
    - Chat messages with needs_response → at least Sonnet (tool use)
    """
    settings = get_settings()

    # Always use Opus for VIP or financial matters
    if classification.involves_vip or classification.involves_financial:
        return settings.claude_model_opus

    # Chat messages that need a response should use at least Sonnet for tool use
    if event and event.source.value == "gchat" and classification.needs_response:
        if classification.complexity == Complexity.COMPLEX:
            return settings.claude_model_opus
        return settings.claude_model_default  # Sonnet

    # Route by complexity
    if classification.complexity == Complexity.SIMPLE:
        return settings.claude_model_haiku
    elif classification.complexity == Complexity.COMPLEX:
        return settings.claude_model_opus
    else:
        return settings.claude_model_default
