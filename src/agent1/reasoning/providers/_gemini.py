"""Gemini provider — wraps google-genai SDK."""

from __future__ import annotations

import uuid

from google import genai
from google.genai import types

from agent1.reasoning.providers._base import LLMProvider, LLMResponse, ToolCall


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
    """Convert tool definitions to Gemini FunctionDeclarations."""
    declarations = []
    for td in tool_defs:
        schema = td.get("input_schema") or td.get("parameters") or {}
        converted = _convert_schema(schema)
        declarations.append(
            types.FunctionDeclaration(
                name=td["name"],
                description=td.get("description", ""),
                parameters=converted if converted.get("properties") else None,
            )
        )
    return [types.Tool(function_declarations=declarations)]


def _messages_to_contents(messages: list[dict]) -> list[types.Content]:
    """Convert unified message format to Gemini Content objects.

    Gemini requires:
    - user messages as Content(role="user")
    - assistant messages as Content(role="model")
    - tool responses grouped into a single Content(role="user") with Part.from_function_response
    """
    contents: list[types.Content] = []
    pending_tool_responses: list[types.Part] = []

    for msg in messages:
        role = msg["role"]

        if role == "tool":
            # Accumulate tool responses — Gemini wants them in one user turn
            import json

            raw = msg.get("content", "")
            try:
                response_data = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                response_data = {"result": raw}
            if not isinstance(response_data, dict):
                response_data = {"result": response_data}
            pending_tool_responses.append(
                types.Part.from_function_response(
                    name=msg.get("name", "unknown"),
                    response=response_data,
                )
            )
            continue

        # Flush any pending tool responses before a non-tool message
        if pending_tool_responses:
            contents.append(types.Content(role="user", parts=pending_tool_responses))
            pending_tool_responses = []

        if role == "user":
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])])
            )

        elif role == "assistant":
            parts: list[types.Part] = []
            if msg.get("content"):
                parts.append(types.Part.from_text(text=msg["content"]))
            for tc in msg.get("tool_calls", []):
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=tc["name"],
                            args=tc["arguments"],
                        )
                    )
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))

    # Flush any remaining tool responses
    if pending_tool_responses:
        contents.append(types.Content(role="user", parts=pending_tool_responses))

    return contents


class GeminiProvider(LLMProvider):
    """LLM provider backed by Google Gemini (google-genai SDK)."""

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    async def generate(
        self,
        model: str,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
        system: str | None = None,
    ) -> LLMResponse:
        contents = _messages_to_contents(messages)

        config_kwargs: dict = {"max_output_tokens": max_tokens}
        if system:
            config_kwargs["system_instruction"] = system
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        if tools:
            config_kwargs["tools"] = _build_gemini_tools(tools)

        config = types.GenerateContentConfig(**config_kwargs)

        response = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        # Extract token counts
        input_tokens = response.usage_metadata.prompt_token_count or 0
        output_tokens = response.usage_metadata.candidates_token_count or 0

        # Parse response parts
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.text:
                text_parts.append(part.text)
            if part.function_call:
                fc = part.function_call
                tool_calls.append(
                    ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    )
                )

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
