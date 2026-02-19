"""Tests for MCP client integration."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent1.tools.mcp.config import MCPServerConfig, load_mcp_config, _resolve_env_vars
from agent1.tools.mcp.adapter import MCPToolAdapter
from agent1.tools.mcp.builder import _validate_code, DynamicTool, DynamicToolBuilder


# ── Config Tests ────────────────────────────────────────────


class TestMCPServerConfig:
    def test_defaults(self):
        config = MCPServerConfig(name="test", transport="stdio")
        assert config.name == "test"
        assert config.transport == "stdio"
        assert config.enabled is False
        assert config.args == []
        assert config.env == {}
        assert config.tool_filter is None
        assert config.timeout_seconds == 30


class TestEnvVarResolution:
    def test_resolves_existing_var(self):
        with patch.dict(os.environ, {"MY_KEY": "secret123"}):
            assert _resolve_env_vars("${MY_KEY}") == "secret123"

    def test_resolves_missing_var_to_empty(self):
        result = _resolve_env_vars("${NONEXISTENT_VAR_XYZ}")
        assert result == ""

    def test_resolves_multiple_vars(self):
        with patch.dict(os.environ, {"A": "1", "B": "2"}):
            assert _resolve_env_vars("${A}-${B}") == "1-2"

    def test_no_vars_unchanged(self):
        assert _resolve_env_vars("plain text") == "plain text"


class TestLoadMCPConfig:
    def test_missing_file_returns_empty(self):
        configs = load_mcp_config("/nonexistent/path.json")
        assert configs == []

    def test_loads_valid_config(self, tmp_path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({
            "servers": [
                {
                    "name": "test_server",
                    "transport": "stdio",
                    "command": "echo",
                    "args": ["hello"],
                    "enabled": True,
                },
                {
                    "name": "disabled_server",
                    "transport": "sse",
                    "url": "http://localhost:8080",
                    "enabled": False,
                },
            ]
        }))

        configs = load_mcp_config(str(config_file))

        assert len(configs) == 2
        assert configs[0].name == "test_server"
        assert configs[0].transport == "stdio"
        assert configs[0].command == "echo"
        assert configs[0].args == ["hello"]
        assert configs[0].enabled is True

        assert configs[1].name == "disabled_server"
        assert configs[1].transport == "sse"
        assert configs[1].url == "http://localhost:8080"
        assert configs[1].enabled is False

    def test_resolves_env_in_config(self, tmp_path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({
            "servers": [
                {
                    "name": "test",
                    "transport": "stdio",
                    "command": "node",
                    "env": {"TOKEN": "${TEST_MCP_TOKEN}"},
                }
            ]
        }))

        with patch.dict(os.environ, {"TEST_MCP_TOKEN": "tok_abc"}):
            configs = load_mcp_config(str(config_file))

        assert configs[0].env["TOKEN"] == "tok_abc"

    def test_tool_filter(self, tmp_path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({
            "servers": [
                {
                    "name": "filtered",
                    "transport": "stdio",
                    "command": "node",
                    "tool_filter": ["read", "write"],
                }
            ]
        }))

        configs = load_mcp_config(str(config_file))
        assert configs[0].tool_filter == ["read", "write"]


# ── Adapter Tests ───────────────────────────────────────────


class TestMCPToolAdapter:
    def _make_adapter(self, tool_name="my_tool", tool_desc="does stuff", schema=None):
        mcp_tool = MagicMock()
        mcp_tool.name = tool_name
        mcp_tool.description = tool_desc
        mcp_tool.inputSchema = schema or {"type": "object", "properties": {"q": {"type": "string"}}}

        manager = MagicMock()
        manager.call_tool = AsyncMock(return_value="result text")

        return MCPToolAdapter(server_name="srv", mcp_tool=mcp_tool, manager=manager), manager

    def test_name_is_namespaced(self):
        adapter, _ = self._make_adapter()
        assert adapter.name == "srv__my_tool"

    def test_description_passthrough(self):
        adapter, _ = self._make_adapter(tool_desc="Search things")
        assert adapter.description == "Search things"

    def test_description_fallback(self):
        adapter, _ = self._make_adapter(tool_desc="")
        assert "srv" in adapter.description

    def test_input_schema_passthrough(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        adapter, _ = self._make_adapter(schema=schema)
        assert adapter.input_schema == schema

    def test_to_tool_definition(self):
        adapter, _ = self._make_adapter()
        defn = adapter.to_tool_definition()
        assert defn["name"] == "srv__my_tool"
        assert "description" in defn
        assert "input_schema" in defn

    @pytest.mark.asyncio
    async def test_execute_delegates_to_manager(self):
        adapter, manager = self._make_adapter()
        result = await adapter.execute(q="hello")
        manager.call_tool.assert_awaited_once_with("srv", "my_tool", {"q": "hello"})
        assert result == "result text"


# ── Builder / Code Validation Tests ─────────────────────────


class TestCodeValidation:
    def test_allows_safe_code(self):
        code = "async def run(*, city: str) -> str:\n    return f'Hello {city}'"
        assert _validate_code(code) is None

    def test_blocks_os_import(self):
        assert _validate_code("import os") is not None

    def test_blocks_subprocess_import(self):
        assert _validate_code("import subprocess") is not None

    def test_blocks_from_os_import(self):
        assert _validate_code("from os import path") is not None

    def test_blocks_eval(self):
        assert _validate_code("eval('1+1')") is not None

    def test_blocks_exec(self):
        assert _validate_code("exec('pass')") is not None

    def test_blocks_open(self):
        assert _validate_code("open('/etc/passwd')") is not None

    def test_blocks_dunder_access(self):
        assert _validate_code("x.__class__") is not None

    def test_blocks_compile(self):
        assert _validate_code("compile('pass', '', 'exec')") is not None

    def test_detects_syntax_error(self):
        assert _validate_code("def broken(") is not None

    def test_allows_httpx_import(self):
        code = "import httpx\nasync def run(): pass"
        assert _validate_code(code) is None

    def test_allows_json_import(self):
        code = "import json\nasync def run(): pass"
        assert _validate_code(code) is None


class TestDynamicTool:
    @pytest.mark.asyncio
    async def test_executes_simple_function(self):
        code = "async def run(*, x: int, y: int) -> int:\n    return x + y"
        tool = DynamicTool("test_add", "Adds numbers", {
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["x", "y"],
        }, code)

        result = await tool.execute(x=3, y=4)
        assert result == 7

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self):
        code = "async def run(**kwargs):\n    raise ValueError('boom')"
        tool = DynamicTool("test_err", "Fails", {"type": "object", "properties": {}}, code)

        result = await tool.execute()
        assert isinstance(result, dict)
        assert "error" in result

    def test_properties(self):
        tool = DynamicTool("my_tool", "desc", {"type": "object"}, "pass")
        assert tool.name == "my_tool"
        assert tool.description == "desc"
        assert tool.input_schema == {"type": "object"}


class TestDynamicToolBuilder:
    def test_builder_tool_definition(self):
        builder = DynamicToolBuilder()
        assert builder.name == "create_dynamic_tool"
        defn = builder.to_tool_definition()
        assert "name" in defn["input_schema"]["properties"]
        assert "code" in defn["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_rejects_unsafe_code(self):
        builder = DynamicToolBuilder()

        # Code validation happens before DB access, so only get_tool needs mocking
        with patch("agent1.tools.registry.get_tool", return_value=None):
            result = await builder.execute(
                name="evil",
                description="Bad tool",
                input_schema={"type": "object", "properties": {}},
                code="import os\nos.system('rm -rf /')",
            )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_rejects_duplicate_name(self):
        builder = DynamicToolBuilder()
        existing_tool = MagicMock()

        with patch("agent1.tools.registry.get_tool", return_value=existing_tool):
            result = await builder.execute(
                name="existing",
                description="Dup",
                input_schema={"type": "object", "properties": {}},
                code="async def run(): pass",
            )

        assert "error" in result
        assert "already exists" in result["error"]
