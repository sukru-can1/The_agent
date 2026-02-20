"""Core reasoning engine with function-calling loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event
from agent1.common.observability import trace_operation
from agent1.reasoning.providers import get_provider, provider_available
from agent1.reasoning.router import select_model
from agent1.tools.registry import execute_tool, get_tool_definitions

if TYPE_CHECKING:
    from agent1.intelligence.context_engine import EnrichedContext

log = get_logger(__name__)

OPS_PLAYBOOK = ""
_playbook_path = Path(__file__).parent / "prompts" / "ops_playbook.md"
if _playbook_path.exists():
    OPS_PLAYBOOK = _playbook_path.read_text(encoding="utf-8")


@trace_operation("reason_and_act")
async def reason_and_act(
    event: Event,
    classification: ClassificationResult,
    plan: dict | None = None,
    enriched_context: EnrichedContext | None = None,
) -> dict:
    """Send event to LLM with tools, execute function calls in a loop until done.

    Returns a dict with model_used, input_tokens, output_tokens, and result.
    """
    if not await provider_available():
        log.warning("no_api_key_skipping_reasoning")
        return {"model_used": "none", "input_tokens": 0, "output_tokens": 0, "result": "skipped"}

    model = select_model(classification, event)
    provider = await get_provider()
    tool_defs = get_tool_definitions()

    # Build context message
    context_parts = [
        f"## Event\n- Source: {event.source.value}\n- Type: {event.event_type}\n- Priority: {event.priority.name}",
        f"\n## Payload\n```json\n{json.dumps(event.payload, indent=2, default=str)}\n```",
        f"\n## Classification\n- Category: {classification.category}\n- Urgency: {classification.urgency.name}\n- Complexity: {classification.complexity.value}\n- VIP: {classification.involves_vip}\n- Financial: {classification.involves_financial}\n- Needs Response: {classification.needs_response}",
    ]

    # Language instruction
    lang = classification.detected_language
    if lang and lang != "en":
        lang_names = {"de": "German", "tr": "Turkish", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch", "pt": "Portuguese", "pl": "Polish", "ru": "Russian", "ar": "Arabic", "ja": "Japanese", "zh": "Chinese"}
        lang_name = lang_names.get(lang, lang.upper())
        context_parts.append(
            f"\n## Language\nThe message is in **{lang_name}** ({lang}). Draft any response in {lang_name} to match the sender's language."
        )

    if plan:
        context_parts.append(
            f"\n## Plan\n- Actions: {', '.join(plan.get('intended_actions', []))}\n- Reasoning: {plan.get('reasoning', '')}"
        )

    # Inject enriched context (replaces old "last 10 taught rules" approach)
    if enriched_context:
        from agent1.intelligence.context_engine import _format_context
        formatted_ctx = _format_context(enriched_context)
        if formatted_ctx:
            context_parts.append(f"\n{formatted_ctx}")
    else:
        # Fallback: inject recent taught rules (backwards compat)
        try:
            from agent1.common.db import get_pool as _get_pool
            pool = await _get_pool()
            async with pool.acquire() as conn:
                knowledge_rows = await conn.fetch(
                    """
                    SELECT content FROM knowledge
                    WHERE active = true
                      AND category IN ('taught_rule', 'edit_pattern', 'approved_rule')
                    ORDER BY created_at DESC
                    LIMIT 10
                    """
                )
                if knowledge_rows:
                    rules = "\n".join(f"- {r['content']}" for r in knowledge_rows)
                    context_parts.append(f"\n## Learned Rules\n{rules}")
        except Exception:
            pass

    context = "\n".join(context_parts)

    # Build initial messages
    messages: list[dict] = [{"role": "user", "content": context}]
    total_input = 0
    total_output = 0

    # Multi-turn function-calling loop
    max_turns = 10
    tools_called: list[str] = []
    for turn in range(max_turns):
        response = await provider.generate(
            model=model,
            messages=messages,
            tools=tool_defs,
            max_tokens=4096,
            system=OPS_PLAYBOOK or None,
        )

        total_input += response.input_tokens
        total_output += response.output_tokens

        if not response.tool_calls:
            # LLM is done — return final text
            final_text = response.text or ""

            log.info(
                "reasoning_complete",
                model=model,
                turns=turn + 1,
                input_tokens=total_input,
                output_tokens=total_output,
            )

            return {
                "model_used": model,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "result": final_text,
                "turns": turn + 1,
                "tools_called": tools_called,
            }

        # Append assistant message with tool calls
        messages.append({
            "role": "assistant",
            "content": response.text,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ],
        })

        # Execute tool calls and append results
        for tc in response.tool_calls:
            tools_called.append(tc.name)
            log.info("tool_call", tool=tc.name, input=tc.arguments)
            try:
                result = await execute_tool(tc.name, tc.arguments)
                result_data = json.dumps(result, default=str) if not isinstance(result, str) else result
            except Exception as exc:
                log.exception("tool_execution_error", tool=tc.name)
                result_data = json.dumps({"error": str(exc)})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.name,
                "content": result_data,
            })

    log.warning("reasoning_max_turns_reached", model=model, turns=max_turns)
    return {
        "model_used": model,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "result": "max_turns_reached",
        "turns": max_turns,
        "tools_called": tools_called,
    }
