"""Worker process entry point — starts consumer + pollers."""

from __future__ import annotations

import asyncio
import signal

from agent1.common.db import close_pools, get_pool
from agent1.common.logging import get_logger, setup_logging
from agent1.common.observability import flush_langfuse
from agent1.common.redis_client import close_redis, get_redis
from agent1.common.settings import get_settings
from agent1.queue.consumer import run_consumer
from agent1.worker.loop import process_event
from agent1.worker.pollers.scheduler import run_scheduler

log = get_logger(__name__)

_shutdown = asyncio.Event()


def _handle_signal(sig: signal.Signals) -> None:
    log.info("shutdown_signal", signal=sig.name)
    _shutdown.set()


async def main() -> None:
    """Start the worker: consumer loop + pollers + scheduler."""
    settings = get_settings()
    setup_logging(settings.log_level)

    log.info("worker_starting", agent=settings.agent_name)

    # Connect to infrastructure
    await get_pool()
    await get_redis()

    # Register all tools
    from agent1.tools.registry import register_all_tools

    register_all_tools()

    # Register signal handlers (Unix only; Windows uses KeyboardInterrupt)
    import sys

    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s))

    # Start concurrent tasks
    consumer_task = asyncio.create_task(run_consumer(process_event))
    scheduler_task = asyncio.create_task(run_scheduler())

    log.info("worker_started", agent=settings.agent_name)

    # Wait for shutdown signal
    await _shutdown.wait()

    log.info("worker_shutting_down")
    consumer_task.cancel()
    scheduler_task.cancel()

    await asyncio.gather(consumer_task, scheduler_task, return_exceptions=True)

    flush_langfuse()
    await close_pools()
    await close_redis()

    log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
