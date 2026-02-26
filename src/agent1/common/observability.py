"""LangFuse observability setup with trace propagation, generation spans, and tool spans."""

from __future__ import annotations

import contextvars
import functools
import time
from collections.abc import Callable
from typing import Any

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

_langfuse: Any = None
_langfuse_init_failed = False

# Context var holds the current Langfuse trace/span for nesting.
_current_trace: contextvars.ContextVar[Any] = contextvars.ContextVar("_current_trace", default=None)


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


def _create_trace(lf: Any, name: str, **kwargs: Any) -> Any:
    """Create a LangFuse trace, handling API differences across versions."""
    try:
        if hasattr(lf, "trace"):
            return lf.trace(name=name, **kwargs)
        return None
    except Exception as exc:
        log.debug("langfuse_trace_failed", error=str(exc))
        return None


def _create_span(parent: Any, name: str) -> Any:
    """Create a span under a parent trace/span. Returns None on failure."""
    if parent is None:
        return None
    try:
        if hasattr(parent, "span"):
            return parent.span(name=name)
        return None
    except Exception as exc:
        log.debug("langfuse_span_failed", error=str(exc))
        return None


def trace_operation(name: str) -> Callable:
    """Decorator to trace an async function with LangFuse.

    If a parent trace exists in context, creates a span under it.
    Otherwise creates a new top-level trace and sets it in context.
    Never blocks actual work — LangFuse errors are logged and swallowed.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            lf = get_langfuse()
            start = time.monotonic()

            parent = _current_trace.get()
            trace: Any = None
            token: contextvars.Token | None = None

            if lf is not None:
                try:
                    if parent is not None:
                        # Nested call — create a span under the parent
                        trace = _create_span(parent, name)
                    else:
                        # Top-level — create a new trace and set in context
                        trace = _create_trace(lf, name)
                    if trace is not None:
                        token = _current_trace.set(trace)
                except Exception:
                    pass

            try:
                result = await func(*args, **kwargs)
                elapsed_ms = int((time.monotonic() - start) * 1000)

                if trace is not None:
                    try:
                        trace.update(
                            output=str(result)[:500] if result else None,
                            metadata={"latency_ms": elapsed_ms},
                        )
                        if hasattr(trace, "end"):
                            trace.end()
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
                        if hasattr(trace, "end"):
                            trace.end()
                    except Exception:
                        pass
                raise
            finally:
                if token is not None:
                    _current_trace.reset(token)

        return wrapper

    return decorator


def trace_generation(
    *,
    name: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an LLM call as a Langfuse generation under the current trace.

    Call explicitly after each provider.generate().
    Safe to call when Langfuse is not configured — silently returns.
    """
    parent = _current_trace.get()
    if parent is None:
        return
    try:
        if hasattr(parent, "generation"):
            gen = parent.generation(
                name=name,
                model=model,
                usage={"input": input_tokens, "output": output_tokens},
                metadata=metadata or {},
            )
            if gen is not None and hasattr(gen, "end"):
                gen.end()
    except Exception as exc:
        log.debug("langfuse_generation_failed", error=str(exc))


def trace_span(name: str) -> Any:
    """Create a span for tool execution under the current trace.

    Returns a span object (call span.end() when done) or None.
    """
    parent = _current_trace.get()
    return _create_span(parent, name)


def end_span(span: Any) -> None:
    """End a span safely. No-op if span is None."""
    if span is None:
        return
    try:
        if hasattr(span, "end"):
            span.end()
    except Exception:
        pass


def flush_langfuse() -> None:
    """Flush pending LangFuse events."""
    if _langfuse is not None:
        try:
            _langfuse.flush()
        except Exception:
            pass
