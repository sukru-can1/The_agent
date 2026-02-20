"""Abstract base for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A tool/function call returned by the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
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
        """Generate a response from the LLM.

        Args:
            model: Model identifier (provider-specific).
            messages: List of message dicts with keys:
                - role: "user" | "assistant" | "tool"
                - content: text content
                - tool_calls: (assistant only) list of {id, name, arguments}
                - tool_call_id: (tool only) ID of the tool call being responded to
                - name: (tool only) name of the tool
            tools: List of tool definition dicts with keys:
                - name: tool name
                - description: tool description
                - input_schema or parameters: JSON Schema for arguments
            max_tokens: Maximum output tokens.
            json_mode: If True, request JSON output.
            system: System prompt.

        Returns:
            LLMResponse with text and/or tool_calls.
        """
