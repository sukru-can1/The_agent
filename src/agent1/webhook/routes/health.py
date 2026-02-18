"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from agent1.common.db import get_pool
from agent1.common.redis_client import get_redis
from agent1.common.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Basic health check — returns 200 if the process is alive."""
    return {"status": "ok", "agent": get_settings().agent_name}


@router.get("/status")
async def status():
    """Detailed status check including DB and Redis connectivity."""
    checks = {"agent": get_settings().agent_name, "db": "unknown", "redis": "unknown"}

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["db"] = "connected"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "connected"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = checks["db"] == "connected" and checks["redis"] == "connected"
    return {"status": "ok" if all_ok else "degraded", **checks}
