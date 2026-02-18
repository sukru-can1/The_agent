"""Planning step before tool execution."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event
from agent1.common.observability import trace_operation

log = get_logger(__name__)


@trace_operation("create_plan")
async def create_plan(event: Event, classification: ClassificationResult) -> dict:
    """Ask Claude to create a plan of intended actions before executing tools.

    Returns a plan dict with intended_actions, tools_needed, reasoning.
    """
    from agent1.reasoning.router import select_model

    model = select_model(classification)

    # For Phase 0, return a simple placeholder plan
    # Full implementation in Phase 1 will call Claude for planning
    plan = {
        "event_type": event.event_type,
        "source": event.source.value,
        "intended_actions": [f"Process {event.event_type} from {event.source.value}"],
        "tools_needed": [],
        "reasoning": f"Event classified as {classification.category} ({classification.complexity.value})",
        "model": model,
    }

    log.info("plan_created", event_id=str(event.id), plan=plan)
    return plan
