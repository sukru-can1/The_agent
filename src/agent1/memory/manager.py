"""Memory manager — semantic search and storage via pgvector."""

from __future__ import annotations

from typing import Any

from agent1.common.db import get_pool
from agent1.common.embeddings import embed_text
from agent1.common.logging import get_logger

log = get_logger(__name__)


async def search_memory(
    query: str,
    category: str = "all",
    limit: int = 5,
    threshold: float = 0.6,
) -> dict[str, Any]:
    """Semantic search across incidents and knowledge tables."""
    pool = await get_pool()
    embedding = await embed_text(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    results = []

    async with pool.acquire() as conn:
        if category in ("incidents", "all"):
            rows = await conn.fetch(
                """
                SELECT id, category, description, resolution, market, tags,
                       1 - (embedding <=> $1::vector) as similarity
                FROM incidents
                WHERE 1 - (embedding <=> $1::vector) > $2
                ORDER BY similarity DESC
                LIMIT $3
                """,
                embedding_str,
                threshold,
                limit,
            )
            for row in rows:
                results.append({
                    "table": "incidents",
                    "id": row["id"],
                    "category": row["category"],
                    "content": row["description"],
                    "resolution": row["resolution"],
                    "market": row["market"],
                    "similarity": float(row["similarity"]),
                })

        if category in ("knowledge", "all"):
            rows = await conn.fetch(
                """
                SELECT id, category, content, source, confidence,
                       1 - (embedding <=> $1::vector) as similarity
                FROM knowledge
                WHERE active = true
                  AND 1 - (embedding <=> $1::vector) > $2
                ORDER BY similarity DESC
                LIMIT $3
                """,
                embedding_str,
                threshold,
                limit,
            )
            for row in rows:
                results.append({
                    "table": "knowledge",
                    "id": row["id"],
                    "category": row["category"],
                    "content": row["content"],
                    "source": row["source"],
                    "confidence": float(row["confidence"]),
                    "similarity": float(row["similarity"]),
                })

    # Sort by similarity and limit
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return {"results": results[:limit], "query": query}


async def store_incident(**kwargs: Any) -> dict:
    """Store a new incident with its embedding."""
    pool = await get_pool()

    description = kwargs["description"]
    embedding = await embed_text(description)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO incidents (category, description, resolution, market, systems_involved, tags, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
            RETURNING id
            """,
            kwargs["category"],
            description,
            kwargs.get("resolution"),
            kwargs.get("market"),
            kwargs.get("systems_involved", []),
            kwargs.get("tags", []),
            embedding_str,
        )

    log.info("incident_stored", id=row["id"], category=kwargs["category"])
    return {"id": row["id"], "status": "stored"}


async def store_knowledge(**kwargs: Any) -> dict:
    """Store a new piece of knowledge with its embedding."""
    pool = await get_pool()

    content = kwargs["content"]
    embedding = await embed_text(content)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO knowledge (category, content, source, embedding)
            VALUES ($1, $2, $3, $4::vector)
            RETURNING id
            """,
            kwargs["category"],
            content,
            kwargs.get("source", "configured"),
            embedding_str,
        )

    log.info("knowledge_stored", id=row["id"], category=kwargs["category"])
    return {"id": row["id"], "status": "stored"}
