"""MCP server configuration loading."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from agent1.common.logging import get_logger

log = get_logger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)}")


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    transport: str  # "stdio" or "sse"
    command: str = ""  # for stdio transport
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""  # for sse transport
    enabled: bool = False
    tool_filter: list[str] | None = None  # if set, only expose these tool names
    timeout_seconds: int = 30


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} with environment variable values."""

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        resolved = os.environ.get(var_name, "")
        if not resolved:
            log.warning("mcp_env_var_missing", var=var_name)
        return resolved

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_env_dict(env: dict[str, str]) -> dict[str, str]:
    """Resolve env var placeholders in a dict's values."""
    return {k: _resolve_env_vars(v) for k, v in env.items()}


def load_mcp_config(path: str) -> list[MCPServerConfig]:
    """Load MCP server configs from a JSON file.

    Returns an empty list if the file doesn't exist.
    """
    config_path = Path(path)
    if not config_path.exists():
        log.info("mcp_config_not_found", path=path)
        return []

    with open(config_path) as f:
        data = json.load(f)

    servers = data.get("servers", [])
    configs: list[MCPServerConfig] = []

    for entry in servers:
        config = MCPServerConfig(
            name=entry["name"],
            transport=entry.get("transport", "stdio"),
            command=entry.get("command", ""),
            args=entry.get("args", []),
            env=_resolve_env_dict(entry.get("env", {})),
            url=entry.get("url", ""),
            enabled=entry.get("enabled", False),
            tool_filter=entry.get("tool_filter"),
            timeout_seconds=entry.get("timeout_seconds", 30),
        )
        configs.append(config)
        log.debug(
            "mcp_config_loaded",
            server=config.name,
            transport=config.transport,
            enabled=config.enabled,
        )

    log.info("mcp_configs_loaded", total=len(configs), enabled=sum(1 for c in configs if c.enabled))
    return configs
