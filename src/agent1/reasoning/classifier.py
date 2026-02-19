"""Fast event classification using Gemini Flash."""

from __future__ import annotations

import json
from pathlib import Path

from google import genai
from google.genai import types

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
    """Classify an event using Gemini Flash for fast, cheap categorization.

    Returns a ClassificationResult with category, urgency, complexity, etc.
    """
    settings = get_settings()

    if not settings.gemini_api_key:
        # Fallback classification when no API key (dev/testing)
        return ClassificationResult(
            category=event.event_type,
            urgency=event.priority,
            complexity=Complexity.MODERATE,
            needs_response=True,
            confidence=0.5,
        )

    client = genai.Client(api_key=settings.gemini_api_key)

    context = json.dumps(
        {
            "source": event.source.value,
            "event_type": event.event_type,
            "payload": event.payload,
        },
        default=str,
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model_fast,
            contents=f"Classify this event:\n\n{context}",
            config=types.GenerateContentConfig(
                system_instruction=CLASSIFIER_PROMPT or "Classify this event. Respond with valid JSON only.",
                max_output_tokens=500,
            ),
        )

        text = response.text.strip()
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
            detected_language=data.get("detected_language", "en"),
            is_teachable_rule=data.get("is_teachable_rule", False),
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
