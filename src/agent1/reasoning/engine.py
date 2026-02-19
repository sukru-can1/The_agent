"""Core Claude reasoning engine with tool_use loop."""

from __future__ import annotations

import json
from pathlib import Path

import anthropic

from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event
from agent1.common.observability import trace_operation
from agent1.common.settings import get_settings
from agent1.reasoning.router import select_model
from agent1.tools.registry import get_tool_definitions, execute_tool

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
) -> dict:
    """Send event to Claude with tools, execute tool calls in a loop until done.

    Returns a dict with model_used, input_tokens, output_tokens, and result.
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        log.warning("no_api_key_skipping_reasoning")
        return {"model_used": "none", "input_tokens": 0, "output_tokens": 0, "result": "skipped"}

    model = select_model(classification, event)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    tools = get_tool_definitions()

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

    # Inject learned knowledge patterns
    try:
        from agent1.common.db import get_pool as _get_pool

        pool = await _get_pool()
        async with pool.acquire() as conn:
            knowledge_rows = await conn.fetch(
                """
                SELECT content FROM knowledge
                WHERE active = true
                  AND category IN ('taught_rule', 'edit_pattern')
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

    messages = [{"role": "user", "content": context}]
    total_input = 0
    total_output = 0

    # Multi-turn tool_use loop
    max_turns = 10
    for turn in range(max_turns):
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=OPS_PLAYBOOK,
            tools=tools,
            messages=messages,
        )

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

        # Check if Claude wants to call tools
        tool_calls = [block for block in response.content if block.type == "tool_use"]

        if not tool_calls:
            # Claude is done — extract final text response
            text_blocks = [block.text for block in response.content if block.type == "text"]
            final_text = "\n".join(text_blocks) if text_blocks else ""

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
            }

        # Execute tool calls
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for call in tool_calls:
            log.info("tool_call", tool=call.name, input=call.input)
            try:
                result = await execute_tool(call.name, call.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": json.dumps(result, default=str) if not isinstance(result, str) else result,
                    }
                )
            except Exception as exc:
                log.exception("tool_execution_error", tool=call.name)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": f"Error: {exc}",
                        "is_error": True,
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    log.warning("reasoning_max_turns_reached", model=model, turns=max_turns)
    return {
        "model_used": model,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "result": "max_turns_reached",
        "turns": max_turns,
    }
