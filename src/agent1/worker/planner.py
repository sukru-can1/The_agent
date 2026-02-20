"""Planning step before tool execution — uses Gemini to create action plans."""

from __future__ import annotations

import json
from pathlib import Path

from google import genai
from google.genai import types

from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event
from agent1.common.observability import trace_operation
from agent1.common.settings import get_settings

log = get_logger(__name__)

PLANNER_PROMPT_PATH = Path(__file__).parent.parent / "reasoning" / "prompts" / "planner.md"
try:
    PLANNER_PROMPT = PLANNER_PROMPT_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    PLANNER_PROMPT = "Create a brief JSON plan with intended_actions, tools_needed, reasoning, risks."


@trace_operation("create_plan")
async def create_plan(event: Event, classification: ClassificationResult) -> dict:
    """Ask Gemini to create a plan of intended actions before executing tools.

    For simple events, returns a lightweight plan without an API call.
    For complex events, calls Flash for fast planning.
    """
    from agent1.reasoning.router import select_model

    model = select_model(classification)

    # Simple events get a fast local plan (no API call)
    if classification.complexity.value == "simple":
        plan = {
            "event_type": event.event_type,
            "source": event.source.value,
            "intended_actions": [f"Process {event.event_type} from {event.source.value}"],
            "tools_needed": _guess_tools(event),
            "reasoning": f"Simple {classification.category} event — standard processing",
            "risks": [],
            "model": model,
        }
        log.info("plan_created", event_id=str(event.id), complexity="simple")
        return plan

    # Complex events get a Gemini-generated plan
    settings = get_settings()
    if not settings.gemini_api_key:
        return _fallback_plan(event, classification, model)

    try:
        from agent1.reasoning.classifier import _extract_json

        client = genai.Client(api_key=settings.gemini_api_key)
        response = await client.aio.models.generate_content(
            model=settings.gemini_model_fast,
            contents=(
                f"Event: {event.event_type} from {event.source.value}\n"
                f"Priority: {event.priority}\n"
                f"Classification: category={classification.category}, "
                f"urgency={classification.urgency}, "
                f"complexity={classification.complexity.value}, "
                f"involves_vip={classification.involves_vip}, "
                f"involves_financial={classification.involves_financial}\n"
                f"Payload: {json.dumps(event.payload, default=str)[:1000]}"
            ),
            config=types.GenerateContentConfig(
                system_instruction=PLANNER_PROMPT,
                response_mime_type="application/json",
                max_output_tokens=500,
            ),
        )

        plan = _extract_json(response.text)
        plan["model"] = model
        plan["event_type"] = event.event_type
        plan["source"] = event.source.value
        log.info(
            "plan_created",
            event_id=str(event.id),
            complexity="complex",
            model=settings.gemini_model_fast,
        )
        return plan

    except Exception as exc:
        log.warning(
            "plan_creation_failed",
            error=str(exc),
            event_id=str(event.id),
        )
        return _fallback_plan(event, classification, model)


def _fallback_plan(event: Event, classification: ClassificationResult, model: str) -> dict:
    """Generate a plan without an API call."""
    return {
        "event_type": event.event_type,
        "source": event.source.value,
        "intended_actions": [f"Process {event.event_type} from {event.source.value}"],
        "tools_needed": _guess_tools(event),
        "reasoning": f"Event classified as {classification.category} ({classification.complexity.value})",
        "risks": [],
        "model": model,
    }


def _guess_tools(event: Event) -> list[str]:
    """Guess which tools will be needed based on event source."""
    source_tools = {
        "gmail": ["gmail_get_email", "gmail_draft_reply", "memory_search"],
        "freshdesk": ["freshdesk_get_ticket", "freshdesk_add_note", "memory_search"],
        "gchat": ["gchat_reply_as_agent", "memory_search"],
        "feedbacks": ["feedbacks_get_customer_responses", "memory_search"],
        "starinfinity": ["starinfinity_get_tasks", "memory_search"],
        "scheduler": ["memory_search"],
    }
    return source_tools.get(event.source.value, ["memory_search"])
