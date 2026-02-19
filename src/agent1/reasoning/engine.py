"""Core Gemini reasoning engine with function-calling loop."""

from __future__ import annotations

import json
from pathlib import Path

from google import genai
from google.genai import types

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


def _convert_schema(schema: dict) -> dict:
    """Convert JSON Schema types to Gemini's uppercase type format."""
    if not isinstance(schema, dict):
        return schema

    result = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, str):
            result[key] = value.upper()
        elif key == "properties" and isinstance(value, dict):
            result[key] = {k: _convert_schema(v) for k, v in value.items()}
        elif key == "items" and isinstance(value, dict):
            result[key] = _convert_schema(value)
        else:
            result[key] = value
    return result


def _build_gemini_tools(tool_defs: list[dict]) -> list[types.Tool]:
    """Convert Anthropic-style tool definitions to Gemini FunctionDeclarations."""
    declarations = []
    for td in tool_defs:
        schema = td.get("input_schema", {})
        converted = _convert_schema(schema)
        declarations.append(
            types.FunctionDeclaration(
                name=td["name"],
                description=td.get("description", ""),
                parameters=converted if converted.get("properties") else None,
            )
        )
    return [types.Tool(function_declarations=declarations)]


@trace_operation("reason_and_act")
async def reason_and_act(
    event: Event,
    classification: ClassificationResult,
    plan: dict | None = None,
) -> dict:
    """Send event to Gemini with tools, execute function calls in a loop until done.

    Returns a dict with model_used, input_tokens, output_tokens, and result.
    """
    settings = get_settings()

    if not settings.gemini_api_key:
        log.warning("no_api_key_skipping_reasoning")
        return {"model_used": "none", "input_tokens": 0, "output_tokens": 0, "result": "skipped"}

    model = select_model(classification, event)
    client = genai.Client(api_key=settings.gemini_api_key)
    tool_defs = get_tool_definitions()
    gemini_tools = _build_gemini_tools(tool_defs)

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

    # Build initial contents
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=context)])]
    total_input = 0
    total_output = 0

    # Multi-turn function-calling loop
    max_turns = 10
    tools_called: list[str] = []
    for turn in range(max_turns):
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=OPS_PLAYBOOK or None,
                max_output_tokens=4096,
                tools=gemini_tools,
            ),
        )

        total_input += response.usage_metadata.prompt_token_count or 0
        total_output += response.usage_metadata.candidates_token_count or 0

        # Extract function calls from response parts
        candidate = response.candidates[0]
        function_calls = [
            part for part in candidate.content.parts
            if part.function_call
        ]

        if not function_calls:
            # Gemini is done — extract final text
            text_parts = [
                part.text for part in candidate.content.parts
                if part.text
            ]
            final_text = "\n".join(text_parts) if text_parts else ""

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

        # Append model's response to conversation
        contents.append(candidate.content)

        # Execute function calls and build response parts
        fn_response_parts = []
        for part in function_calls:
            fc = part.function_call
            tools_called.append(fc.name)
            log.info("tool_call", tool=fc.name, input=dict(fc.args) if fc.args else {})
            try:
                result = await execute_tool(fc.name, dict(fc.args) if fc.args else {})
                result_data = json.dumps(result, default=str) if not isinstance(result, str) else result
                fn_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result_data},
                    )
                )
            except Exception as exc:
                log.exception("tool_execution_error", tool=fc.name)
                fn_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"error": str(exc)},
                    )
                )

        # Send function results back as user turn
        contents.append(types.Content(role="user", parts=fn_response_parts))

    log.warning("reasoning_max_turns_reached", model=model, turns=max_turns)
    return {
        "model_used": model,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "result": "max_turns_reached",
        "turns": max_turns,
        "tools_called": tools_called,
    }
