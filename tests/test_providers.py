"""Tests for LLM provider abstraction."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent1.reasoning.providers._base import LLMProvider, LLMResponse, ToolCall
from agent1.reasoning.providers._factory import get_provider, provider_available, reset_provider


# ===========================================================================
# LLMResponse / ToolCall dataclass tests
# ===========================================================================


class TestDataclasses:
    def test_llm_response_defaults(self):
        r = LLMResponse()
        assert r.text is None
        assert r.tool_calls == []
        assert r.input_tokens == 0
        assert r.output_tokens == 0

    def test_llm_response_with_values(self):
        tc = ToolCall(id="call_1", name="my_tool", arguments={"x": 1})
        r = LLMResponse(text="hello", tool_calls=[tc], input_tokens=10, output_tokens=5)
        assert r.text == "hello"
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "my_tool"

    def test_tool_call_fields(self):
        tc = ToolCall(id="call_abc", name="search", arguments={"query": "test"})
        assert tc.id == "call_abc"
        assert tc.name == "search"
        assert tc.arguments == {"query": "test"}


# ===========================================================================
# GeminiProvider tests
# ===========================================================================


class TestGeminiProvider:
    def test_convert_schema(self):
        from agent1.reasoning.providers._gemini import _convert_schema

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "items": {"type": "array", "items": {"type": "string"}},
            },
        }
        result = _convert_schema(schema)
        assert result["type"] == "OBJECT"
        assert result["properties"]["name"]["type"] == "STRING"
        assert result["properties"]["count"]["type"] == "INTEGER"
        assert result["properties"]["items"]["items"]["type"] == "STRING"

    def test_build_gemini_tools(self):
        from agent1.reasoning.providers._gemini import _build_gemini_tools

        tool_defs = [
            {
                "name": "search",
                "description": "Search for things",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ]
        result = _build_gemini_tools(tool_defs)
        assert len(result) == 1
        assert len(result[0].function_declarations) == 1
        assert result[0].function_declarations[0].name == "search"

    def test_messages_to_contents_simple(self):
        from agent1.reasoning.providers._gemini import _messages_to_contents

        messages = [{"role": "user", "content": "hello"}]
        contents = _messages_to_contents(messages)
        assert len(contents) == 1
        assert contents[0].role == "user"

    def test_messages_to_contents_with_assistant(self):
        from agent1.reasoning.providers._gemini import _messages_to_contents

        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        contents = _messages_to_contents(messages)
        assert len(contents) == 2
        assert contents[1].role == "model"

    def test_messages_to_contents_tool_grouping(self):
        """Tool responses should be grouped into a single user turn."""
        from agent1.reasoning.providers._gemini import _messages_to_contents

        messages = [
            {"role": "user", "content": "do something"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "name": "tool_a", "arguments": {}},
                    {"id": "c2", "name": "tool_b", "arguments": {}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "tool_a", "content": '{"result": "a"}'},
            {"role": "tool", "tool_call_id": "c2", "name": "tool_b", "content": '{"result": "b"}'},
        ]
        contents = _messages_to_contents(messages)
        # user, model, user(tool responses grouped)
        assert len(contents) == 3
        assert contents[2].role == "user"
        assert len(contents[2].parts) == 2  # two function responses grouped

    async def test_generate_simple_text(self):
        """GeminiProvider.generate returns text from a mocked Gemini response."""
        from agent1.reasoning.providers._gemini import GeminiProvider

        mock_part = MagicMock()
        mock_part.text = "Hello world"
        mock_part.function_call = None

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.candidates_token_count = 5

        with patch("agent1.reasoning.providers._gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate(
                model="gemini-2.0-flash",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert result.text == "Hello world"
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert result.tool_calls == []

    async def test_generate_with_tool_calls(self):
        """GeminiProvider.generate extracts tool calls from function_call parts."""
        from agent1.reasoning.providers._gemini import GeminiProvider

        mock_fc = MagicMock()
        mock_fc.name = "search"
        mock_fc.args = {"query": "test"}

        mock_part = MagicMock()
        mock_part.text = None
        mock_part.function_call = mock_fc

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata.prompt_token_count = 15
        mock_response.usage_metadata.candidates_token_count = 8

        with patch("agent1.reasoning.providers._gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "search for something"}],
                tools=[{
                    "name": "search",
                    "description": "search",
                    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                }],
            )

        assert result.text is None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].arguments == {"query": "test"}
        assert result.tool_calls[0].id.startswith("call_")


# ===========================================================================
# OpenRouterProvider tests
# ===========================================================================


class TestOpenRouterProvider:
    async def test_generate_simple_text(self):
        """OpenRouterProvider.generate returns text from mocked OpenAI response."""
        from agent1.reasoning.providers._openrouter import OpenRouterProvider

        mock_message = MagicMock()
        mock_message.content = "Hello from OpenRouter"
        mock_message.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 12
        mock_usage.completion_tokens = 6

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("agent1.reasoning.providers._openrouter.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai_cls.return_value = mock_client

            provider = OpenRouterProvider(api_key="test-key")
            result = await provider.generate(
                model="anthropic/claude-sonnet-4",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert result.text == "Hello from OpenRouter"
        assert result.input_tokens == 12
        assert result.output_tokens == 6
        assert result.tool_calls == []

    async def test_generate_with_tool_calls(self):
        """OpenRouterProvider.generate extracts tool calls."""
        from agent1.reasoning.providers._openrouter import OpenRouterProvider

        mock_tc = MagicMock()
        mock_tc.id = "call_xyz"
        mock_tc.function.name = "search"
        mock_tc.function.arguments = '{"query": "test"}'

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tc]

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 20
        mock_usage.completion_tokens = 10

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("agent1.reasoning.providers._openrouter.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai_cls.return_value = mock_client

            provider = OpenRouterProvider(api_key="test-key")
            result = await provider.generate(
                model="anthropic/claude-sonnet-4",
                messages=[{"role": "user", "content": "search"}],
                tools=[{
                    "name": "search",
                    "description": "search",
                    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                }],
            )

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_xyz"
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].arguments == {"query": "test"}

    async def test_generate_with_system_prompt(self):
        """System prompt is prepended as system message."""
        from agent1.reasoning.providers._openrouter import OpenRouterProvider

        mock_message = MagicMock()
        mock_message.content = "response"
        mock_message.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 5
        mock_usage.completion_tokens = 3

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("agent1.reasoning.providers._openrouter.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai_cls.return_value = mock_client

            provider = OpenRouterProvider(api_key="test-key")
            await provider.generate(
                model="anthropic/claude-sonnet-4",
                messages=[{"role": "user", "content": "hi"}],
                system="You are helpful.",
            )

            # Verify system message was prepended
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            messages = call_kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "You are helpful."

    async def test_generate_json_mode(self):
        """json_mode=True sets response_format."""
        from agent1.reasoning.providers._openrouter import OpenRouterProvider

        mock_message = MagicMock()
        mock_message.content = '{"key": "value"}'
        mock_message.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 5
        mock_usage.completion_tokens = 3

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("agent1.reasoning.providers._openrouter.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai_cls.return_value = mock_client

            provider = OpenRouterProvider(api_key="test-key")
            result = await provider.generate(
                model="anthropic/claude-sonnet-4",
                messages=[{"role": "user", "content": "give json"}],
                json_mode=True,
            )

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["response_format"] == {"type": "json_object"}
            assert result.text == '{"key": "value"}'


# ===========================================================================
# OpenRouter message building tests
# ===========================================================================


class TestOpenRouterMessages:
    def test_build_openai_messages_simple(self):
        from agent1.reasoning.providers._openrouter import _build_openai_messages

        messages = [{"role": "user", "content": "hello"}]
        result = _build_openai_messages(messages, system=None)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "hello"}

    def test_build_openai_messages_with_system(self):
        from agent1.reasoning.providers._openrouter import _build_openai_messages

        messages = [{"role": "user", "content": "hello"}]
        result = _build_openai_messages(messages, system="Be helpful")
        assert len(result) == 2
        assert result[0] == {"role": "system", "content": "Be helpful"}

    def test_build_openai_messages_with_tool_calls(self):
        from agent1.reasoning.providers._openrouter import _build_openai_messages

        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "name": "search", "arguments": {"q": "test"}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"result": "found"}'},
        ]
        result = _build_openai_messages(messages, system=None)
        assert len(result) == 2
        assert result[0]["tool_calls"][0]["function"]["arguments"] == '{"q": "test"}'
        assert result[1]["tool_call_id"] == "c1"

    def test_build_openai_tools(self):
        from agent1.reasoning.providers._openrouter import _build_openai_tools

        tool_defs = [
            {
                "name": "search",
                "description": "Search things",
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
            }
        ]
        result = _build_openai_tools(tool_defs)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search"
        assert result[0]["function"]["parameters"]["type"] == "object"


# ===========================================================================
# Factory tests
# ===========================================================================


class TestFactory:
    def setup_method(self):
        reset_provider()

    def teardown_method(self):
        reset_provider()
        # Reset settings singleton
        import agent1.common.settings as s
        s._settings = None

    def test_default_provider_is_gemini(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        import agent1.common.settings as s
        s._settings = None

        assert provider_available()

    def test_openrouter_available(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        import agent1.common.settings as s
        s._settings = None

        assert provider_available()

    def test_missing_gemini_key_not_available(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        import agent1.common.settings as s
        s._settings = None

        assert not provider_available()

    def test_missing_openrouter_key_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        import agent1.common.settings as s
        s._settings = None

        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            get_provider()

    def test_missing_gemini_key_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "")
        import agent1.common.settings as s
        s._settings = None

        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            get_provider()

    def test_get_provider_returns_gemini(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        import agent1.common.settings as s
        s._settings = None

        from agent1.reasoning.providers._gemini import GeminiProvider

        p = get_provider()
        assert isinstance(p, GeminiProvider)

    def test_get_provider_returns_openrouter(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        import agent1.common.settings as s
        s._settings = None

        from agent1.reasoning.providers._openrouter import OpenRouterProvider

        p = get_provider()
        assert isinstance(p, OpenRouterProvider)

    def test_singleton_behavior(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        import agent1.common.settings as s
        s._settings = None

        p1 = get_provider()
        p2 = get_provider()
        assert p1 is p2

    def test_reset_clears_singleton(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        import agent1.common.settings as s
        s._settings = None

        p1 = get_provider()
        reset_provider()
        p2 = get_provider()
        assert p1 is not p2
