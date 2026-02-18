"""LangFuse observability setup and decorators."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

from langfuse import Langfuse

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

_langfuse: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    """Get or create the LangFuse client. Returns None if not configured."""
    global _langfuse
    settings = get_settings()
    if not settings.langfuse_public_key:
        return None
    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        log.info("langfuse_initialized")
    return _langfuse


def trace_operation(name: str) -> Callable:
    """Decorator to trace an async function with LangFuse."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            lf = get_langfuse()
            start = time.monotonic()

            trace = None
            if lf is not None:
                trace = lf.trace(name=name)

            try:
                result = await func(*args, **kwargs)
                elapsed_ms = int((time.monotonic() - start) * 1000)

                if trace is not None:
                    trace.update(
                        output=str(result)[:500] if result else None,
                        metadata={"latency_ms": elapsed_ms},
                    )
                return result
            except Exception as exc:
                if trace is not None:
                    trace.update(
                        level="ERROR",
                        status_message=str(exc),
                    )
                raise

        return wrapper

    return decorator


def flush_langfuse() -> None:
    """Flush pending LangFuse events."""
    if _langfuse is not None:
        _langfuse.flush()
