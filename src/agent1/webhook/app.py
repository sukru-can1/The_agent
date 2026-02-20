"""FastAPI webhook application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

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

    # Connect to DB and Redis on startup (retry-tolerant)
    try:
        await get_pool()
        log.info("database_connected")
    except Exception as exc:
        log.warning("database_connect_failed", error=str(exc))

    try:
        await get_redis()
        log.info("redis_connected")
    except Exception as exc:
        log.warning("redis_connect_failed", error=str(exc))

    # Register all tools (native + MCP + dynamic)
    from agent1.tools.registry import register_all_tools, register_dynamic_tools, register_mcp_tools

    register_all_tools()
    await register_mcp_tools()
    await register_dynamic_tools()

    log.info("webhook_started", agent=settings.agent_name)

    yield

    # Cleanup
    from agent1.tools.mcp import stop_mcp_servers

    await stop_mcp_servers()
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
    from agent1.webhook.routes.admin import router as admin_router
    from agent1.webhook.routes.freshdesk import router as freshdesk_router
    from agent1.webhook.routes.gchat import router as gchat_router
    from agent1.webhook.routes.gmail_push import router as gmail_router
    from agent1.webhook.routes.health import router as health_router
    from agent1.webhook.routes.oauth_callback import router as oauth_router

    app.include_router(health_router)
    app.include_router(gchat_router, prefix="/webhooks")
    app.include_router(freshdesk_router, prefix="/webhooks")
    app.include_router(gmail_router, prefix="/webhooks")
    app.include_router(admin_router, prefix="/admin")
    app.include_router(oauth_router, prefix="/admin")

    # Add middleware
    from agent1.webhook.middleware import add_middleware

    add_middleware(app)

    return app
