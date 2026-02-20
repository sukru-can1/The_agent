"""Sandboxed Python script execution for agent-created solutions."""

from __future__ import annotations

import asyncio
import re
import textwrap
from typing import Any

from agent1.common.logging import get_logger

log = get_logger(__name__)

ALLOWED_IMPORTS = frozenset({
    "requests", "httpx", "json", "csv", "re", "datetime", "urllib.parse",
    "math", "statistics", "collections", "itertools",
    "textwrap", "string", "html", "base64", "hashlib", "uuid", "decimal",
})

BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "importlib", "ctypes", "pickle",
})

BLOCKED_PATTERNS = [
    re.compile(r"\bimport\s+(" + "|".join(BLOCKED_IMPORTS) + r")\b"),
    re.compile(r"\bfrom\s+(" + "|".join(BLOCKED_IMPORTS) + r")\s+import\b"),
    re.compile(r"\b(eval|exec|compile|__import__)\s*\("),
    re.compile(r"\b(globals|locals|vars)\s*\("),
    re.compile(r"\bopen\s*\("),
    re.compile(r"\b__\w+__"),
]

MAX_EXECUTION_TIME = 60
MAX_OUTPUT_SIZE = 50_000


def validate_code(code: str) -> str | None:
    """Validate code safety. Returns error message or None if valid."""
    for pattern in BLOCKED_PATTERNS:
        match = pattern.search(code)
        if match:
            return f"Blocked pattern: {match.group()}"

    try:
        compile(code, "<solution_script>", "exec")
    except SyntaxError as e:
        return f"Syntax error: {e}"

    return None


async def run_script(
    code: str,
    params: dict[str, Any],
    timeout: int = MAX_EXECUTION_TIME,
) -> Any:
    """Execute a script in a restricted sandbox.

    The script must define an async function named 'run' that takes keyword arguments.
    Returns the function's return value, or an error dict.
    """
    import json as json_mod

    import httpx

    # Build restricted scope
    scope: dict[str, Any] = {
        "httpx": httpx,
        "json": json_mod,
        "re": re,
        "asyncio": asyncio,
        "math": __import__("math"),
        "datetime": __import__("datetime"),
        "statistics": __import__("statistics"),
        "collections": __import__("collections"),
        "params": params,
        "result": None,
    }

    wrapped = textwrap.dedent(code)

    try:
        exec(compile(wrapped, "<solution>", "exec"), scope)

        if callable(scope.get("run")):
            coro = scope["run"](**params)
            if asyncio.iscoroutine(coro):
                return await asyncio.wait_for(coro, timeout=timeout)
            return coro

        return scope.get("result", "Script executed (no 'run' function or result)")

    except TimeoutError:
        return {"error": f"Script timed out after {timeout}s"}
    except Exception as exc:
        log.error("script_execution_error", error=str(exc))
        return {"error": str(exc)}
