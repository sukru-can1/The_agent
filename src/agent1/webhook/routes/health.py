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


@router.get("/diag/pgvector")
async def diag_pgvector():
    """Temporary diagnostic: check pgvector extension and vector columns."""
    results: dict = {}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check extension
            ext = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            results["extension"] = ext or "NOT INSTALLED"

            # Check vector columns
            cols = await conn.fetch(
                """
                SELECT table_name, column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE udt_name = 'vector'
                ORDER BY table_name, column_name
                """
            )
            results["vector_columns"] = [dict(r) for r in cols]

            # Check tables exist
            tables = await conn.fetch(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            results["tables"] = [r["tablename"] for r in tables]

            # Check HNSW indexes
            indexes = await conn.fetch(
                """
                SELECT indexname, tablename
                FROM pg_indexes
                WHERE indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%vector%'
                ORDER BY tablename
                """
            )
            results["vector_indexes"] = [dict(r) for r in indexes]

            # Try a simple vector operation
            try:
                await conn.execute("SELECT '[1,2,3]'::vector(3)")
                results["vector_cast_test"] = "OK"
            except Exception as e:
                results["vector_cast_test"] = f"FAILED: {e}"

    except Exception as exc:
        results["error"] = str(exc)

    return results
