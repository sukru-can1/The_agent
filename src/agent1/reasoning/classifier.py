"""Haiku-based fast event classification."""

from __future__ import annotations

import json
from pathlib import Path

import anthropic

from agent1.common.logging import get_logger
from agent1.common.models import (
    ClassificationResult,
    Complexity,
    Event,
    Priority,
)
from agent1.common.observability import trace_operation
from agent1.common.settings import get_settings

log = get_logger(__name__)

CLASSIFIER_PROMPT = (Path(__file__).parent / "prompts" / "classifier.md").read_text(
    encoding="utf-8"
) if (Path(__file__).parent / "prompts" / "classifier.md").exists() else ""


@trace_operation("classify_event")
async def classify_event(event: Event) -> ClassificationResult:
    """Classify an event using Haiku for fast, cheap categorization.

    Returns a ClassificationResult with category, urgency, complexity, etc.
    Cost: ~$0.001 per classification.
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        # Fallback classification when no API key (dev/testing)
        return ClassificationResult(
            category=event.event_type,
            urgency=event.priority,
            complexity=Complexity.MODERATE,
            needs_response=True,
            confidence=0.5,
        )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    context = json.dumps(
        {
            "source": event.source.value,
            "event_type": event.event_type,
            "payload": event.payload,
        },
        default=str,
    )

    try:
        response = await client.messages.create(
            model=settings.claude_model_haiku,
            max_tokens=500,
            system=CLASSIFIER_PROMPT or "Classify this event. Respond with valid JSON only.",
            messages=[
                {
                    "role": "user",
                    "content": f"Classify this event:\n\n{context}",
                }
            ],
        )

        text = response.content[0].text.strip()
        # Parse JSON from response
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)

        return ClassificationResult(
            category=data.get("category", event.event_type),
            urgency=Priority(data.get("urgency", event.priority.value)),
            complexity=Complexity(data.get("complexity", "moderate")),
            involves_vip=data.get("involves_vip", False),
            involves_financial=data.get("involves_financial", False),
            needs_response=data.get("needs_response", True),
            confidence=data.get("confidence", 0.8),
        )
    except Exception:
        log.exception("classification_failed", event_id=str(event.id))
        return ClassificationResult(
            category=event.event_type,
            urgency=event.priority,
            complexity=Complexity.MODERATE,
            needs_response=True,
            confidence=0.0,
        )
