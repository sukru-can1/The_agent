"""FastAPI webhook application factory."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from agent1.common.db import close_pools, get_pool
from agent1.common.logging import get_logger, setup_logging
from agent1.common.redis_client import close_redis, get_redis
from agent1.common.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    settings = get_settings()
    setup_logging(settings.log_level)

    # Connect to DB and Redis on startup
    await get_pool()
    await get_redis()

    # Register all tools
    from agent1.tools.registry import register_all_tools

    register_all_tools()

    log.info("webhook_started", agent=settings.agent_name)

    yield

    # Cleanup
    await close_pools()
    await close_redis()
    log.info("webhook_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=f"{settings.agent_name} — GLAMIRA Ops Agent Webhook",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register routes
    from agent1.webhook.routes.health import router as health_router
    from agent1.webhook.routes.gchat import router as gchat_router
    from agent1.webhook.routes.freshdesk import router as freshdesk_router
    from agent1.webhook.routes.gmail_push import router as gmail_router
    from agent1.webhook.routes.admin import router as admin_router

    app.include_router(health_router)
    app.include_router(gchat_router, prefix="/webhooks")
    app.include_router(freshdesk_router, prefix="/webhooks")
    app.include_router(gmail_router, prefix="/webhooks")
    app.include_router(admin_router, prefix="/admin")

    # Add middleware
    from agent1.webhook.middleware import add_middleware

    add_middleware(app)

    return app
