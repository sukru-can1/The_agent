"""Tests for the sandboxed script runner."""

from __future__ import annotations

import pytest

from agent1.intelligence.solutions.script_runner import (
    validate_code,
    run_script,
    ALLOWED_IMPORTS,
    BLOCKED_IMPORTS,
)


def test_validate_code_allows_clean_code():
    code = '''
async def run(*, city: str) -> str:
    import json
    return json.dumps({"city": city})
'''
    assert validate_code(code) is None


def test_validate_code_blocks_os():
    code = "import os\nos.system('rm -rf /')"
    error = validate_code(code)
    assert error is not None
    assert "os" in error.lower() or "blocked" in error.lower()


def test_validate_code_blocks_subprocess():
    code = "import subprocess\nsubprocess.run(['ls'])"
    error = validate_code(code)
    assert error is not None


def test_validate_code_blocks_eval():
    code = "result = eval('1+1')"
    error = validate_code(code)
    assert error is not None


def test_validate_code_blocks_open():
    code = "f = open('/etc/passwd')\nresult = f.read()"
    error = validate_code(code)
    assert error is not None


def test_validate_code_allows_requests():
    code = '''
async def run(*, url: str) -> str:
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.text
'''
    assert validate_code(code) is None


def test_validate_code_catches_syntax_error():
    code = "def broken(:\n  pass"
    error = validate_code(code)
    assert error is not None
    assert "syntax" in error.lower()


@pytest.mark.asyncio
async def test_run_script_simple():
    code = '''
async def run(*, name: str) -> str:
    return f"Hello, {name}!"
'''
    result = await run_script(code, {"name": "Agent"})
    assert result == "Hello, Agent!"


@pytest.mark.asyncio
async def test_run_script_timeout():
    code = '''
import asyncio
async def run() -> str:
    await asyncio.sleep(100)
    return "done"
'''
    result = await run_script(code, {}, timeout=1)
    assert "timed out" in str(result).lower() or "timeout" in str(result).lower()


@pytest.mark.asyncio
async def test_run_script_error_handled():
    code = '''
async def run() -> str:
    raise ValueError("test error")
'''
    result = await run_script(code, {})
    assert "error" in str(result).lower()
