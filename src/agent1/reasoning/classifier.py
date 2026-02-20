"""Fast event classification using Gemini Flash."""

from __future__ import annotations

import json
import re
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


def _extract_json(text: str) -> dict:
    """Extract a JSON object from LLM output, handling common edge cases.

    Handles: markdown fences, leading/trailing prose, truncated strings,
    trailing commas.
    Raises ValueError if no valid JSON can be extracted.
    """
    text = text.strip()

    # 1. Try direct parse first (ideal case with response_mime_type)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences: ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        inner = fence_match.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            # Try fixing the fenced content too
            fixed = _fix_truncated_json(inner)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    # 3. Find the first { ... } block (handles leading/trailing prose)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            fixed = _fix_truncated_json(candidate)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    # 4. Handle truncated JSON: starts with { but no closing }
    brace_start = text.find("{")
    if brace_start >= 0:
        candidate = text[brace_start:]
        fixed = _fix_truncated_json(candidate)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in: {text[:200]}")


def _fix_truncated_json(text: str) -> str:
    """Attempt to fix JSON truncated mid-string or mid-object."""
    # Close any unterminated string
    quote_count = text.count('"') - text.count('\\"')
    if quote_count % 2 == 1:
        text += '"'

    # Remove trailing comma (before we add closing delimiters)
    text = re.sub(r",\s*$", "", text)

    # Remove trailing comma before closing braces/brackets: ,} or ,]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Balance braces and brackets
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    text += "]" * max(open_brackets, 0)
    text += "}" * max(open_braces, 0)

    return text


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
                system_instruction=(
                    CLASSIFIER_PROMPT
                    or "Classify this event. Respond with valid JSON only."
                ),
                response_mime_type="application/json",
                max_output_tokens=500,
            ),
        )

        data = _extract_json(response.text)

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
