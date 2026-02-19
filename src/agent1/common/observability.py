"""LangFuse observability setup and decorators."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

_langfuse: Any = None
_langfuse_init_failed = False


def get_langfuse() -> Any:
    """Get or create the LangFuse client. Returns None if not configured or broken."""
    global _langfuse, _langfuse_init_failed
    if _langfuse_init_failed:
        return None

    settings = get_settings()
    if not settings.langfuse_public_key:
        return None

    if _langfuse is None:
        try:
            from langfuse import Langfuse

            _langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            log.info("langfuse_initialized")
        except Exception as exc:
            log.warning("langfuse_init_failed", error=str(exc))
            _langfuse_init_failed = True
            return None
    return _langfuse


def _create_trace(lf: Any, name: str) -> Any:
    """Create a LangFuse trace, handling API differences across versions."""
    try:
        # v2+ API
        if hasattr(lf, "trace"):
            return lf.trace(name=name)
        # v3 decorators API — just skip
        return None
    except Exception as exc:
        log.debug("langfuse_trace_failed", error=str(exc))
        return None


def trace_operation(name: str) -> Callable:
    """Decorator to trace an async function with LangFuse.

    Never blocks actual work — LangFuse errors are logged and swallowed.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            lf = get_langfuse()
            start = time.monotonic()

            trace = _create_trace(lf, name) if lf is not None else None

            try:
                result = await func(*args, **kwargs)
                elapsed_ms = int((time.monotonic() - start) * 1000)

                if trace is not None:
                    try:
                        trace.update(
                            output=str(result)[:500] if result else None,
                            metadata={"latency_ms": elapsed_ms},
                        )
                    except Exception:
                        pass
                return result
            except Exception as exc:
                if trace is not None:
                    try:
                        trace.update(
                            level="ERROR",
                            status_message=str(exc),
                        )
                    except Exception:
                        pass
                raise

        return wrapper

    return decorator


def flush_langfuse() -> None:
    """Flush pending LangFuse events."""
    if _langfuse is not None:
        try:
            _langfuse.flush()
        except Exception:
            pass
