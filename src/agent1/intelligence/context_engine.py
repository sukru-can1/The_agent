"""Context engine -- pre-reasoning retrieval of relevant history and knowledge."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from agent1.common.db import get_pool
from agent1.common.embeddings import embed_text
from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event

log = get_logger(__name__)

TOKEN_BUDGET = 3000


@dataclass
class EnrichedContext:
    """Context retrieved before reasoning to improve decision quality."""

    similar_incidents: list[dict] = field(default_factory=list)
    sender_history: list[dict] = field(default_factory=list)
    relevant_knowledge: list[dict] = field(default_factory=list)
    related_recent_events: list[dict] = field(default_factory=list)
    context_summary: str = ""
    token_estimate: int = 0


def _extract_search_query(event: Event) -> str:
    """Build a search query string from event payload. No AI call needed."""
    p = event.payload
    parts: list[str] = []

    src = event.source.value
    if src == "gmail":
        if p.get("from_address"):
            parts.append(str(p["from_address"]))
        if p.get("subject"):
            parts.append(str(p["subject"]))
        if p.get("body"):
            parts.append(str(p["body"])[:200])
    elif src == "freshdesk":
        if p.get("ticket_id"):
            parts.append(f"ticket {p['ticket_id']}")
        if p.get("subject"):
            parts.append(str(p["subject"]))
        if p.get("description"):
            parts.append(str(p["description"])[:200])
    elif src == "gchat":
        if p.get("text"):
            parts.append(str(p["text"])[:200])
    elif src == "feedbacks":
        if p.get("customer_email"):
            parts.append(str(p["customer_email"]))
        if p.get("comment"):
            parts.append(str(p["comment"])[:200])
    elif src == "dashboard":
        if p.get("text"):
            parts.append(str(p["text"])[:200])
    else:
        # Generic fallback
        for key in ("subject", "text", "description", "body"):
            if p.get(key):
                parts.append(str(p[key])[:200])
                break

    return " ".join(parts) if parts else event.event_type


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def _format_context(ctx: EnrichedContext) -> str:
    """Format enriched context as markdown for injection into the reasoning prompt."""
    sections: list[str] = []

    if ctx.similar_incidents:
        lines = []
        for inc in ctx.similar_incidents:
            sim = f" (similarity: {inc.get('similarity', 0):.2f})" if inc.get("similarity") else ""
            res = f" -> resolved: {inc.get('resolution', 'unknown')}" if inc.get("resolution") else ""
            lines.append(f"- {inc.get('content', inc.get('description', ''))[:200]}{res}{sim}")
        sections.append("### Similar Past Incidents:\n" + "\n".join(lines))

    if ctx.sender_history:
        lines = []
        for h in ctx.sender_history:
            lines.append(
                f"- [{h.get('timestamp', '')}] {h.get('action_type', '')} — {h.get('outcome', '')}"
            )
        sections.append("### Sender History:\n" + "\n".join(lines))

    if ctx.relevant_knowledge:
        lines = []
        for k in ctx.relevant_knowledge:
            conf = f" (confidence: {k.get('confidence', 0):.1f})" if k.get("confidence") else ""
            lines.append(f"- {k.get('content', '')[:200]}{conf}")
        sections.append("### Relevant Rules:\n" + "\n".join(lines))

    if ctx.related_recent_events:
        lines = []
        for e in ctx.related_recent_events:
            lines.append(f"- [{e.get('source', '')}] {e.get('event_type', '')} — {e.get('created_at', '')}")
        sections.append("### Recent Related Events (last 24h):\n" + "\n".join(lines))

    if ctx.context_summary:
        sections.append(f"### Summary:\n{ctx.context_summary}")

    if not sections:
        return ""

    return "## Relevant Context (auto-retrieved)\n" + "\n\n".join(sections)


async def _search_similar_incidents(
    embedding_str: str, limit: int = 3, threshold: float = 0.55,
) -> list[dict]:
    """Vector search for similar past incidents."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, category, description, resolution, market,
                   1 - (embedding <=> $1::vector) as similarity
            FROM incidents
            WHERE embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) > $2
            ORDER BY similarity DESC
            LIMIT $3
            """,
            embedding_str,
            threshold,
            limit,
        )
    return [
        {
            "id": r["id"],
            "content": r["description"],
            "resolution": r["resolution"],
            "market": r["market"],
            "similarity": float(r["similarity"]),
        }
        for r in rows
    ]


async def _search_relevant_knowledge(
    embedding_str: str, limit: int = 5, threshold: float = 0.5,
) -> list[dict]:
    """Vector search for relevant knowledge rules (by semantic relevance, NOT recency)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, category, content, source, confidence,
                   1 - (embedding <=> $1::vector) as similarity
            FROM knowledge
            WHERE active = true
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) > $2
            ORDER BY similarity DESC
            LIMIT $3
            """,
            embedding_str,
            threshold,
            limit,
        )
    return [
        {
            "id": r["id"],
            "category": r["category"],
            "content": r["content"],
            "confidence": float(r["confidence"]) if r["confidence"] else 0,
            "similarity": float(r["similarity"]),
        }
        for r in rows
    ]


async def _search_similar_actions(
    embedding_str: str, limit: int = 5, threshold: float = 0.5,
) -> list[dict]:
    """Vector search on actions_log for similar past actions."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, timestamp, system, action_type, outcome, details,
                   1 - (embedding <=> $1::vector) as similarity
            FROM actions_log
            WHERE embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) > $2
            ORDER BY similarity DESC
            LIMIT $3
            """,
            embedding_str,
            threshold,
            limit,
        )
    return [dict(r) for r in rows]


async def _get_sender_history(event: Event, limit: int = 5) -> list[dict]:
    """Get past interactions with the sender from this event."""
    sender = (
        event.payload.get("from_address")
        or event.payload.get("sender_email")
        or event.payload.get("requester_email")
    )
    if not sender:
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, timestamp, system, action_type, outcome, details
            FROM actions_log
            WHERE details::text ILIKE $1
            ORDER BY timestamp DESC
            LIMIT $2
            """,
            f"%{sender}%",
            limit,
        )
    return [dict(r) for r in rows]


async def _get_related_events(event: Event, hours: int = 24, limit: int = 5) -> list[dict]:
    """Get recent events of the same type from the same source."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source, event_type, priority, status, created_at
            FROM events
            WHERE source = $1
              AND event_type = $2
              AND created_at >= NOW() - make_interval(hours => $3)
              AND id != $4
            ORDER BY created_at DESC
            LIMIT $5
            """,
            event.source.value,
            event.event_type,
            hours,
            event.id,
            limit,
        )
    return [dict(r) for r in rows]


async def enrich(event: Event, classification: ClassificationResult) -> EnrichedContext:
    """Retrieve relevant context for an event before reasoning.

    Runs parallel DB queries: vector search for incidents/knowledge/actions,
    plus SQL for sender history and related events. Trims to TOKEN_BUDGET.
    """
    ctx = EnrichedContext()

    query = _extract_search_query(event)
    if not query or query == event.event_type:
        # Nothing meaningful to search for
        return ctx

    try:
        # Embed the search query
        embedding = await embed_text(query)
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        # Run all 4 queries concurrently
        results = await asyncio.gather(
            _search_similar_incidents(embedding_str),
            _search_relevant_knowledge(embedding_str),
            _get_sender_history(event),
            _get_related_events(event),
            return_exceptions=True,
        )

        if not isinstance(results[0], BaseException):
            ctx.similar_incidents = results[0]
        if not isinstance(results[1], BaseException):
            ctx.relevant_knowledge = results[1]
        if not isinstance(results[2], BaseException):
            ctx.sender_history = results[2]
        if not isinstance(results[3], BaseException):
            ctx.related_recent_events = results[3]

        # Estimate total tokens
        formatted = _format_context(ctx)
        ctx.token_estimate = _estimate_tokens(formatted)

        # Trim if over budget (drop lowest-relevance items)
        while ctx.token_estimate > TOKEN_BUDGET:
            # Remove items with lowest relevance, starting from actions
            if ctx.related_recent_events:
                ctx.related_recent_events.pop()
            elif ctx.sender_history:
                ctx.sender_history.pop()
            elif ctx.relevant_knowledge:
                ctx.relevant_knowledge.pop()
            elif ctx.similar_incidents:
                ctx.similar_incidents.pop()
            else:
                break
            formatted = _format_context(ctx)
            ctx.token_estimate = _estimate_tokens(formatted)

    except Exception:
        log.exception("context_enrichment_failed")

    return ctx
