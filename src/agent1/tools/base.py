"""Base tool abstract class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name as used in Claude tool_use calls."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for Claude."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema for tool input parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with given parameters."""
        ...

    def to_tool_definition(self) -> dict:
        """Convert to Claude API tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
