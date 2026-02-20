"""OpenRouter provider — wraps OpenAI SDK pointed at OpenRouter API."""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from agent1.reasoning.providers._base import LLMProvider, LLMResponse, ToolCall


def _build_openai_tools(tool_defs: list[dict]) -> list[dict]:
    """Convert tool definitions to OpenAI function-calling format."""
    result = []
    for td in tool_defs:
        params = td.get("input_schema") or td.get("parameters") or {"type": "object"}
        result.append({
            "type": "function",
            "function": {
                "name": td["name"],
                "description": td.get("description", ""),
                "parameters": params,
            },
        })
    return result


def _build_openai_messages(messages: list[dict], system: str | None) -> list[dict]:
    """Convert unified messages to OpenAI chat format."""
    result: list[dict] = []

    if system:
        result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg["role"]

        if role == "user":
            result.append({"role": "user", "content": msg["content"]})

        elif role == "assistant":
            entry: dict = {"role": "assistant"}
            if msg.get("content"):
                entry["content"] = msg["content"]
            else:
                entry["content"] = None
            tcs = msg.get("tool_calls", [])
            if tcs:
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in tcs
                ]
            result.append(entry)

        elif role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": msg.get("content", ""),
            })

    return result


class OpenRouterProvider(LLMProvider):
    """LLM provider backed by OpenRouter (OpenAI-compatible API)."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

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
        openai_messages = _build_openai_messages(messages, system)

        kwargs: dict = {
            "model": model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = _build_openai_tools(tools)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        msg = choice.message

        # Parse tool calls
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        # Token counts
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return LLMResponse(
            text=msg.content,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
