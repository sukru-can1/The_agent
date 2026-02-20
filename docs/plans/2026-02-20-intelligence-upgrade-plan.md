# Intelligence Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 3 intelligence subsystems (context engine, feedback intelligence, analytics engine) plus a solution factory, proposals system, and guardrails fix to make The Agent1 genuinely smarter.

**Architecture:** New `src/agent1/intelligence/` package with 5 modules. Proposals system is the foundation — all learning/tool-creation flows through operator approval. Context engine enriches reasoning with relevant history. Feedback intel analyzes edits qualitatively. Analytics engine correlates patterns across systems. Solution factory lets the agent build its own scripts, tools, and automations.

**Tech Stack:** Python 3.12, asyncpg, pgvector, Voyage AI embeddings, Google Gemini (Flash for analysis, Pro for complex), Redis, FastAPI, Next.js dashboard.

---

## Task 1: Database Migration (004_intelligence.sql)

**Files:**
- Create: `migrations/004_intelligence.sql`

**Step 1: Write the migration**

```sql
-- Intelligence upgrade: proposals, solutions, automations, baselines

CREATE TABLE IF NOT EXISTS proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(50) NOT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    evidence TEXT,
    code TEXT,
    config JSONB,
    confidence FLOAT DEFAULT 0.5,
    status VARCHAR(50) DEFAULT 'pending',
    related_event_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(100),
    review_notes TEXT,
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);

CREATE TABLE IF NOT EXISTS solutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    solution_type VARCHAR(50) NOT NULL,
    code TEXT,
    config JSONB,
    trigger_pattern TEXT,
    status VARCHAR(50) DEFAULT 'proposed',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    approved_by VARCHAR(100),
    last_run TIMESTAMPTZ,
    run_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    active BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS automations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    solution_id UUID REFERENCES solutions(id),
    name VARCHAR(200) NOT NULL,
    trigger_type VARCHAR(50) NOT NULL,
    trigger_config JSONB NOT NULL,
    active BOOLEAN DEFAULT false,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    run_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS baselines (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    day_of_week INT NOT NULL,
    hour_of_day INT NOT NULL,
    mean_count FLOAT NOT NULL,
    stddev_count FLOAT NOT NULL,
    sample_weeks INT DEFAULT 4,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, event_type, day_of_week, hour_of_day)
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_type ON proposals(type);
CREATE INDEX IF NOT EXISTS idx_proposals_status_type ON proposals(status, type);
CREATE INDEX IF NOT EXISTS idx_solutions_status ON solutions(status);
CREATE INDEX IF NOT EXISTS idx_solutions_active ON solutions(active) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_automations_active ON automations(active) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_baselines_lookup ON baselines(source, event_type, day_of_week, hour_of_day);
```

**Step 2: Verify migration file is in the right place**

Run: `ls migrations/*.sql`
Expected: `001_initial_schema.sql`, `002_add_vector_columns.sql`, `003_dynamic_tools.sql`, `004_intelligence.sql`

**Step 3: Commit**

```bash
git add migrations/004_intelligence.sql
git commit -m "feat: add migration 004 for intelligence tables (proposals, solutions, automations, baselines)"
```

---

## Task 2: Intelligence Package Init + Proposals System

The proposals system is the foundation — everything else creates proposals.

**Files:**
- Create: `src/agent1/intelligence/__init__.py`
- Create: `src/agent1/intelligence/proposals.py`
- Test: `tests/test_proposals.py`

**Step 1: Write tests for proposals**

```python
"""Tests for the proposals system."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from agent1.intelligence.proposals import (
    create_proposal,
    approve_proposal,
    reject_proposal,
    get_pending_proposals,
    execute_approval,
    ProposalType,
)


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool."""
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.mark.asyncio
async def test_create_proposal_returns_id(mock_pool):
    pool, conn = mock_pool
    proposal_id = uuid4()
    conn.fetchval.return_value = proposal_id

    with patch("agent1.intelligence.proposals.get_pool", return_value=pool):
        result = await create_proposal(
            type=ProposalType.LEARNED_RULE,
            title="Casual tone for .de",
            description="Use first name greeting for German customers",
            evidence="Learned from draft #45",
            confidence=0.6,
        )

    assert result == proposal_id
    conn.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_create_proposal_with_code(mock_pool):
    pool, conn = mock_pool
    conn.fetchval.return_value = uuid4()

    with patch("agent1.intelligence.proposals.get_pool", return_value=pool):
        result = await create_proposal(
            type=ProposalType.TOOL_CREATION,
            title="Carrier status checker",
            description="Check DHL tracking API",
            code="async def run(*, tracking_id: str): ...",
            confidence=0.5,
        )

    assert result is not None
    call_args = conn.fetchval.call_args
    # Verify code was passed in the SQL params
    assert "async def run" in str(call_args)


@pytest.mark.asyncio
async def test_get_pending_proposals(mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [
        {"id": uuid4(), "type": "learned_rule", "title": "Test", "status": "pending",
         "description": "desc", "confidence": 0.6, "created_at": "2026-01-01T00:00:00"},
    ]

    with patch("agent1.intelligence.proposals.get_pool", return_value=pool):
        results = await get_pending_proposals()

    assert len(results) == 1
    assert results[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_approve_proposal_updates_status(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = {
        "id": uuid4(), "type": "learned_rule", "title": "Test",
        "description": "Use casual tone", "code": None, "config": None,
        "confidence": 0.8, "status": "pending",
    }
    conn.execute.return_value = "UPDATE 1"

    with patch("agent1.intelligence.proposals.get_pool", return_value=pool):
        with patch("agent1.intelligence.proposals.execute_approval", new_callable=AsyncMock):
            result = await approve_proposal(conn.fetchrow.return_value["id"])

    assert result is True


@pytest.mark.asyncio
async def test_reject_proposal_updates_status(mock_pool):
    pool, conn = mock_pool
    conn.execute.return_value = "UPDATE 1"

    with patch("agent1.intelligence.proposals.get_pool", return_value=pool):
        result = await reject_proposal(uuid4(), reason="Not applicable")

    assert result is True
```

**Step 2: Run tests to verify they fail**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_proposals.py -v`
Expected: ModuleNotFoundError (intelligence package doesn't exist yet)

**Step 3: Create the intelligence package init**

Create `src/agent1/intelligence/__init__.py`:

```python
"""Intelligence subsystems for The Agent1."""
```

**Step 4: Implement proposals.py**

Create `src/agent1/intelligence/proposals.py`:

```python
"""Proposals system -- universal approval workflow for all agent learning."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any
from uuid import UUID

from agent1.common.db import get_pool
from agent1.common.logging import get_logger

log = get_logger(__name__)


class ProposalType(StrEnum):
    LEARNED_RULE = "learned_rule"
    STRONG_RULE = "strong_rule"
    TOOL_CREATION = "tool_creation"
    AUTOMATION = "automation"
    MCP_SERVER = "mcp_server"
    GUARDRAIL_OVERRIDE = "guardrail_override"
    THRESHOLD_ADJUSTMENT = "threshold_adjustment"
    PLAYBOOK_SUGGESTION = "playbook_suggestion"


async def create_proposal(
    *,
    type: ProposalType,
    title: str,
    description: str,
    evidence: str | None = None,
    code: str | None = None,
    config: dict | None = None,
    confidence: float = 0.5,
    related_event_ids: list[UUID] | None = None,
) -> UUID:
    """Create a new proposal pending operator approval.

    Returns the proposal UUID.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        proposal_id = await conn.fetchval(
            """
            INSERT INTO proposals (type, title, description, evidence, code, config,
                                   confidence, related_event_ids)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            RETURNING id
            """,
            type.value,
            title,
            description,
            evidence,
            code,
            json.dumps(config) if config else None,
            confidence,
            related_event_ids,
        )

    log.info("proposal_created", id=str(proposal_id), type=type.value, title=title)
    return proposal_id


async def get_pending_proposals(
    type: ProposalType | None = None,
    limit: int = 20,
) -> list[dict]:
    """Get pending proposals, optionally filtered by type."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if type:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at
                FROM proposals
                WHERE status = 'pending' AND type = $1
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC, created_at DESC
                LIMIT $2
                """,
                type.value,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at
                FROM proposals
                WHERE status = 'pending'
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY confidence DESC, created_at DESC
                LIMIT $1
                """,
                limit,
            )
    return [dict(r) for r in rows]


async def get_proposal(proposal_id: UUID) -> dict | None:
    """Get a single proposal by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM proposals WHERE id = $1",
            proposal_id,
        )
    return dict(row) if row else None


async def approve_proposal(
    proposal_id: UUID,
    *,
    reviewed_by: str = "operator",
    notes: str | None = None,
    edited_description: str | None = None,
) -> bool:
    """Approve a proposal and execute its side effects.

    Returns True if approved, False if proposal not found or not pending.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM proposals WHERE id = $1 AND status = 'pending'",
            proposal_id,
        )
        if not row:
            return False

        final_description = edited_description or row["description"]

        await conn.execute(
            """
            UPDATE proposals
            SET status = 'approved', reviewed_at = NOW(), reviewed_by = $2,
                review_notes = $3, description = $4
            WHERE id = $1
            """,
            proposal_id,
            reviewed_by,
            notes,
            final_description,
        )

    proposal = dict(row)
    proposal["description"] = final_description
    await execute_approval(proposal)

    log.info("proposal_approved", id=str(proposal_id), type=row["type"])
    return True


async def reject_proposal(
    proposal_id: UUID,
    *,
    reason: str | None = None,
    reviewed_by: str = "operator",
) -> bool:
    """Reject a proposal. Returns True if rejected."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE proposals
            SET status = 'rejected', reviewed_at = NOW(), reviewed_by = $2, review_notes = $3
            WHERE id = $1 AND status = 'pending'
            """,
            proposal_id,
            reviewed_by,
            reason,
        )

    success = result != "UPDATE 0"
    if success:
        log.info("proposal_rejected", id=str(proposal_id), reason=reason)
    return success


async def get_proposal_stats() -> dict:
    """Get counts of proposals by type and status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT type, status, COUNT(*) as count
            FROM proposals
            GROUP BY type, status
            ORDER BY type, status
            """
        )
    stats: dict[str, dict[str, int]] = {}
    for r in rows:
        t = r["type"]
        if t not in stats:
            stats[t] = {}
        stats[t][r["status"]] = r["count"]
    return stats


async def execute_approval(proposal: dict) -> None:
    """Execute the side effect of an approved proposal."""
    ptype = proposal["type"]

    if ptype in (ProposalType.LEARNED_RULE, ProposalType.STRONG_RULE):
        from agent1.memory.manager import store_knowledge
        await store_knowledge(
            category="approved_rule",
            content=proposal["description"],
            source=f"proposal:{proposal['id']}",
        )
        log.info("approved_rule_stored", proposal_id=str(proposal["id"]))

    elif ptype == ProposalType.GUARDRAIL_OVERRIDE:
        config = proposal.get("config")
        if isinstance(config, str):
            config = json.loads(config)
        if config and config.get("event_id"):
            from agent1.queue.publisher import publish_event
            from agent1.common.models import Event, EventSource, Priority
            event = Event(
                source=EventSource.ADMIN,
                event_type="guardrail_override",
                priority=Priority.HIGH,
                payload={
                    "original_event_id": config["event_id"],
                    "rule_name": config.get("rule_name", ""),
                    "skip_guardrails": True,
                },
            )
            await publish_event(event)
            log.info("guardrail_override_published", event_id=config["event_id"])

    elif ptype == ProposalType.TOOL_CREATION:
        if proposal.get("code"):
            from agent1.intelligence.solutions.factory import activate_tool
            await activate_tool(proposal)

    elif ptype == ProposalType.AUTOMATION:
        if proposal.get("config"):
            from agent1.intelligence.solutions.factory import activate_automation
            await activate_automation(proposal)

    elif ptype == ProposalType.THRESHOLD_ADJUSTMENT:
        config = proposal.get("config")
        if isinstance(config, str):
            config = json.loads(config)
        if config:
            from agent1.intelligence.analytics_engine import update_threshold
            await update_threshold(config)

    # MCP_SERVER and PLAYBOOK_SUGGESTION are handled manually for now
```

**Step 5: Run tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_proposals.py -v`
Expected: All 5 tests pass

**Step 6: Commit**

```bash
git add src/agent1/intelligence/__init__.py src/agent1/intelligence/proposals.py tests/test_proposals.py
git commit -m "feat: add proposals system — universal approval workflow for agent learning"
```

---

## Task 3: Context Engine

**Files:**
- Create: `src/agent1/intelligence/context_engine.py`
- Modify: `src/agent1/reasoning/engine.py` (lines 65-75, add `context` param; lines 97-110, replace knowledge injection)
- Test: `tests/test_context_engine.py`

**Step 1: Write tests for context engine**

```python
"""Tests for the context engine."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent1.common.models import (
    ClassificationResult, Complexity, Event, EventSource, Priority,
)
from agent1.intelligence.context_engine import (
    EnrichedContext,
    enrich,
    _extract_search_query,
    _estimate_tokens,
)


@pytest.fixture
def email_event():
    return Event(
        source=EventSource.GMAIL,
        event_type="new_email",
        priority=Priority.MEDIUM,
        payload={
            "from_address": "customer@example.de",
            "subject": "Missing ring from order DE-45123",
            "body": "I ordered a ring 3 days ago and it arrived without the center diamond.",
        },
    )


@pytest.fixture
def classification():
    return ClassificationResult(
        category="customer_complaint",
        urgency=Priority.HIGH,
        complexity=Complexity.MODERATE,
        needs_response=True,
        confidence=0.9,
    )


def test_extract_search_query_gmail(email_event):
    query = _extract_search_query(email_event)
    assert "Missing ring" in query
    assert "customer@example.de" in query


def test_extract_search_query_freshdesk():
    event = Event(
        source=EventSource.FRESHDESK,
        event_type="ticket_updated",
        payload={"ticket_id": 4523, "subject": "Refund request"},
    )
    query = _extract_search_query(event)
    assert "Refund request" in query
    assert "4523" in query


def test_extract_search_query_chat():
    event = Event(
        source=EventSource.GCHAT,
        event_type="chat_message",
        payload={"text": "What tickets are open for DE market?", "sender": "Sukru"},
    )
    query = _extract_search_query(event)
    assert "What tickets are open" in query


def test_estimate_tokens():
    assert _estimate_tokens("hello world") > 0
    assert _estimate_tokens("a" * 1000) > _estimate_tokens("hello")


def test_enriched_context_dataclass():
    ctx = EnrichedContext(
        similar_incidents=[],
        sender_history=[],
        relevant_knowledge=[],
        related_recent_events=[],
        context_summary="",
        token_estimate=0,
    )
    assert ctx.token_estimate == 0


@pytest.mark.asyncio
async def test_enrich_returns_context(email_event, classification):
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_conn.fetch.return_value = []

    with patch("agent1.intelligence.context_engine.get_pool", return_value=mock_pool):
        with patch("agent1.intelligence.context_engine.embed_text", return_value=[0.0] * 1024):
            ctx = await enrich(email_event, classification)

    assert isinstance(ctx, EnrichedContext)
    assert ctx.token_estimate >= 0
```

**Step 2: Run tests to verify they fail**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_context_engine.py -v`
Expected: ModuleNotFoundError

**Step 3: Implement context_engine.py**

Create `src/agent1/intelligence/context_engine.py`:

```python
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

        # Run all 5 queries concurrently
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
```

**Step 4: Modify reasoning engine to accept enriched context**

In `src/agent1/reasoning/engine.py`, change the `reason_and_act` function signature (line 65) and the knowledge injection block (lines 97-112):

The function signature on line 65 changes from:
```python
async def reason_and_act(
    event: Event,
    classification: ClassificationResult,
    plan: dict | None = None,
) -> dict:
```

To:
```python
async def reason_and_act(
    event: Event,
    classification: ClassificationResult,
    plan: dict | None = None,
    enriched_context: "EnrichedContext | None" = None,
) -> dict:
```

Add import at top of file (after existing imports, around line 14):
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agent1.intelligence.context_engine import EnrichedContext
```

Replace the knowledge injection block (the `try: ... except: pass` block that fetches 10 taught rules from knowledge, approximately lines 97-112) with:

```python
    # Inject enriched context (replaces old "last 10 taught rules" approach)
    if enriched_context:
        from agent1.intelligence.context_engine import _format_context
        formatted_ctx = _format_context(enriched_context)
        if formatted_ctx:
            context_parts.append(f"\n{formatted_ctx}")
    else:
        # Fallback: inject recent taught rules (backwards compat)
        try:
            from agent1.common.db import get_pool as _get_pool
            pool = await _get_pool()
            async with pool.acquire() as conn:
                knowledge_rows = await conn.fetch(
                    """
                    SELECT content FROM knowledge
                    WHERE active = true
                      AND category IN ('taught_rule', 'edit_pattern', 'approved_rule')
                    ORDER BY created_at DESC
                    LIMIT 10
                    """
                )
                if knowledge_rows:
                    rules = "\n".join(f"- {r['content']}" for r in knowledge_rows)
                    context_parts.append(f"\n## Learned Rules\n{rules}")
        except Exception:
            pass
```

Note: the fallback also adds `'approved_rule'` to the IN clause so approved proposals are also picked up when enriched context isn't available.

**Step 5: Run tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_context_engine.py tests/test_proposals.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/agent1/intelligence/context_engine.py src/agent1/reasoning/engine.py tests/test_context_engine.py
git commit -m "feat: add context engine — pre-reasoning retrieval of relevant history and knowledge"
```

---

## Task 4: Guardrails Fix (Notifications + Override Proposals)

**Files:**
- Modify: `src/agent1/guardrails/engine.py` (entire file, ~40 lines -> ~80 lines)
- Modify: `src/agent1/worker/loop.py` (handle override commands in teachable rule path)
- Test: `tests/test_guardrails.py` (add 2 new tests)

**Step 1: Add tests for guardrails notification**

Append to `tests/test_guardrails.py`:

```python
@pytest.mark.asyncio
async def test_financial_block_creates_proposal(sample_freshdesk_event, financial_classification):
    """When a financial event is blocked, a guardrail_override proposal should be created."""
    with patch("agent1.guardrails.engine.check_business_rules") as mock_rules:
        mock_rules.return_value = {
            "allowed": False,
            "rule": "financial_topic",
            "reason": "Financial topics require manual approval",
        }
        with patch("agent1.guardrails.engine.check_rate_limits") as mock_rates:
            mock_rates.return_value = {"allowed": True}
            with patch("agent1.guardrails.engine._notify_block", new_callable=AsyncMock) as mock_notify:
                result = await check_guardrails(sample_freshdesk_event, financial_classification)

    assert result is False
    mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_allowed_event_no_notification(sample_email_event, sample_classification):
    """Normal events should not trigger block notifications."""
    with patch("agent1.guardrails.engine.check_business_rules") as mock_rules:
        mock_rules.return_value = {"allowed": True, "rule": None, "reason": None}
        with patch("agent1.guardrails.engine.check_rate_limits") as mock_rates:
            mock_rates.return_value = {"allowed": True}
            result = await check_guardrails(sample_email_event, sample_classification)

    assert result is True
```

**Step 2: Run new tests to verify they fail**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_guardrails.py::test_financial_block_creates_proposal -v`
Expected: Fail (no `_notify_block` function yet)

**Step 3: Update guardrails/engine.py**

Replace the entire content of `src/agent1/guardrails/engine.py`:

```python
"""Programmatic guardrails engine -- checks before any action execution."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.common.models import ClassificationResult, Event
from agent1.guardrails.rules import check_business_rules
from agent1.guardrails.rate_limits import check_rate_limits

log = get_logger(__name__)


async def check_guardrails(event: Event, classification: ClassificationResult) -> bool:
    """Run all guardrail checks before allowing an action.

    Returns True if the event is safe to process, False if blocked.
    When blocked, creates a proposal and notifies the operator.
    """
    # Check business rules
    rule_result = await check_business_rules(event, classification)
    if not rule_result["allowed"]:
        log.warning(
            "guardrails_rule_blocked",
            event_id=str(event.id),
            rule=rule_result["rule"],
            reason=rule_result["reason"],
        )
        await _notify_block(event, rule_result)
        return False

    # Check rate limits
    rate_result = await check_rate_limits(event)
    if not rate_result["allowed"]:
        log.warning(
            "guardrails_rate_limited",
            event_id=str(event.id),
            limit=rate_result["limit"],
        )
        return False

    return True


async def _notify_block(event: Event, rule_result: dict) -> None:
    """Create a guardrail_override proposal and notify via Chat."""
    from agent1.worker.loop import _extract_event_summary

    summary = _extract_event_summary(event)
    rule_name = rule_result.get("rule", "unknown")
    reason = rule_result.get("reason", "")

    # Create override proposal
    try:
        from agent1.intelligence.proposals import create_proposal, ProposalType
        await create_proposal(
            type=ProposalType.GUARDRAIL_OVERRIDE,
            title=f"Blocked: {event.source.value} — {rule_name}",
            description=(
                f"Event {event.id} was blocked by guardrail rule '{rule_name}'.\n"
                f"Reason: {reason}\n\n"
                f"Event: {summary}"
            ),
            config={"event_id": str(event.id), "rule_name": rule_name},
            confidence=0.0,
            related_event_ids=[event.id],
        )
    except Exception:
        log.exception("guardrail_proposal_creation_failed")

    # Notify via Chat (best effort)
    try:
        from agent1.tools.google_chat import GChatPostMessageTool
        chat = GChatPostMessageTool()
        await chat.execute(
            space="alerts",
            message=(
                f"**Event blocked by guardrails**\n"
                f"**Rule:** {rule_name}\n"
                f"**Reason:** {reason}\n"
                f"**Event:** {summary}\n\n"
                f"Reply `override {str(event.id)[:8]}` or approve in Dashboard."
            ),
        )
    except Exception:
        log.warning("guardrail_chat_notification_failed")
```

**Step 4: Run all guardrails tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_guardrails.py -v`
Expected: All tests pass (existing + new)

**Step 5: Commit**

```bash
git add src/agent1/guardrails/engine.py tests/test_guardrails.py
git commit -m "feat: guardrails now notify operator on block and create override proposals"
```

---

## Task 5: Feedback Intelligence

**Files:**
- Create: `src/agent1/intelligence/feedback_intel.py`
- Modify: `src/agent1/webhook/routes/admin.py` (add feedback intel trigger to approve_draft)
- Test: `tests/test_feedback_intel.py`

**Step 1: Write tests**

```python
"""Tests for feedback intelligence — qualitative edit analysis."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


from agent1.intelligence.feedback_intel import (
    analyze_edit,
    analyze_rejection,
    _parse_rules_from_response,
)


def test_parse_rules_from_response_extracts_rules():
    response = """Here are the changes:
RULE: Use first name instead of formal greeting for .de customers
RULE: Keep response under 3 paragraphs
RULE: Always reference the order number"""
    rules = _parse_rules_from_response(response)
    assert len(rules) == 3
    assert "first name" in rules[0]


def test_parse_rules_empty_response():
    rules = _parse_rules_from_response("")
    assert rules == []


def test_parse_rules_no_rules_in_response():
    rules = _parse_rules_from_response("The edits were minor formatting changes.")
    assert rules == []


@pytest.mark.asyncio
async def test_analyze_edit_creates_proposals():
    with patch("agent1.intelligence.feedback_intel._call_flash", new_callable=AsyncMock) as mock_flash:
        mock_flash.return_value = "RULE: Use casual tone for .de customers"
        with patch("agent1.intelligence.feedback_intel.create_proposal", new_callable=AsyncMock) as mock_create:
            from uuid import uuid4
            mock_create.return_value = uuid4()

            await analyze_edit(
                draft_id=1,
                original="Dear valued customer, we sincerely apologize...",
                edited="Hi Maria, sorry about this...",
                sender_domain="example.de",
                category="customer_complaint",
            )

    mock_flash.assert_called_once()
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_rejection_creates_proposal():
    with patch("agent1.intelligence.feedback_intel._call_flash", new_callable=AsyncMock) as mock_flash:
        mock_flash.return_value = "RULE: Never draft a response for legal inquiries"
        with patch("agent1.intelligence.feedback_intel.create_proposal", new_callable=AsyncMock) as mock_create:
            from uuid import uuid4
            mock_create.return_value = uuid4()

            await analyze_rejection(
                draft_id=2,
                draft_body="We can help with your legal question...",
                event_payload={"subject": "Legal inquiry about warranty"},
                rejection_reason="This should not have been drafted at all",
            )

    mock_create.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_feedback_intel.py -v`
Expected: ModuleNotFoundError

**Step 3: Implement feedback_intel.py**

Create `src/agent1/intelligence/feedback_intel.py`:

```python
"""Feedback intelligence -- qualitative analysis of operator corrections."""

from __future__ import annotations

import re

from google import genai
from google.genai import types

from agent1.common.logging import get_logger
from agent1.common.settings import get_settings
from agent1.intelligence.proposals import create_proposal, ProposalType

log = get_logger(__name__)


def _parse_rules_from_response(response: str) -> list[str]:
    """Extract RULE: lines from Flash response."""
    rules = []
    for line in response.strip().splitlines():
        line = line.strip()
        match = re.match(r"^RULE:\s*(.+)$", line, re.IGNORECASE)
        if match:
            rules.append(match.group(1).strip())
    return rules


async def _call_flash(prompt: str) -> str:
    """Call Gemini Flash for quick analysis. Returns response text."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return ""

    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=settings.gemini_model_flash,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=500),
    )
    return response.text.strip() if response.text else ""


async def analyze_edit(
    draft_id: int,
    original: str,
    edited: str,
    sender_domain: str | None = None,
    category: str | None = None,
) -> None:
    """Analyze a draft edit qualitatively and create rule proposals."""
    prompt = f"""Compare these two email drafts and identify specific patterns the agent should learn.

ORIGINAL (agent wrote):
{original[:2000]}

EDITED (operator corrected to):
{edited[:2000]}

Sender domain: {sender_domain or 'unknown'}
Category: {category or 'unknown'}

List each specific change as a concrete, actionable rule.
Format each rule on its own line starting with "RULE: "
Examples:
RULE: Use first name instead of formal greeting for .de customers
RULE: Keep response under 3 paragraphs
RULE: Always reference the order number in the subject"""

    try:
        response = await _call_flash(prompt)
        rules = _parse_rules_from_response(response)

        for rule in rules:
            domain_label = f" for {sender_domain}" if sender_domain else ""
            await create_proposal(
                type=ProposalType.LEARNED_RULE,
                title=f"Draft style rule{domain_label}",
                description=rule,
                evidence=f"Learned from edit of draft #{draft_id}. Domain: {sender_domain}, Category: {category}",
                confidence=0.6,
            )
            log.info("edit_rule_proposed", draft_id=draft_id, rule=rule[:80])

    except Exception:
        log.exception("analyze_edit_failed", draft_id=draft_id)


async def analyze_rejection(
    draft_id: int,
    draft_body: str,
    event_payload: dict | None = None,
    rejection_reason: str | None = None,
) -> None:
    """Analyze a draft rejection and propose rules to prevent recurrence."""
    payload_summary = ""
    if event_payload:
        payload_summary = f"\nEvent context: subject={event_payload.get('subject', '')}, " \
                         f"sender={event_payload.get('from_address', event_payload.get('sender_email', ''))}"

    prompt = f"""An email draft was REJECTED by the operator. Analyze why and suggest rules.

DRAFT (rejected):
{draft_body[:2000]}
{payload_summary}

OPERATOR'S REASON: {rejection_reason or 'Not specified'}

What was wrong? What rule should the agent follow to avoid this mistake?
Format each rule on its own line starting with "RULE: " """

    try:
        response = await _call_flash(prompt)
        rules = _parse_rules_from_response(response)

        for rule in rules:
            await create_proposal(
                type=ProposalType.LEARNED_RULE,
                title=f"Rejection learning (draft #{draft_id})",
                description=rule,
                evidence=f"Learned from rejection of draft #{draft_id}. Reason: {rejection_reason or 'not specified'}",
                confidence=0.7,
            )

    except Exception:
        log.exception("analyze_rejection_failed", draft_id=draft_id)
```

**Step 4: Wire feedback intel into draft approval/rejection in admin.py**

In `src/agent1/webhook/routes/admin.py`, in the `approve_draft` function (around line 202, after `track_edit` call), add:

```python
            # Qualitative analysis (async, best effort)
            try:
                from agent1.intelligence.feedback_intel import analyze_edit
                import asyncio
                asyncio.create_task(analyze_edit(
                    draft_id=draft_id,
                    original=draft["draft_body"],
                    edited=body.edited_body,
                    sender_domain=_extract_domain(draft["from_address"]),
                    category=draft["classification"],
                ))
            except Exception as exc:
                log.warning("feedback_intel_trigger_failed", error=str(exc))
```

In `reject_draft` (after status update, around line 240), add:

```python
    # Qualitative rejection analysis (async, best effort)
    try:
        pool2 = await get_pool()
        async with pool2.acquire() as conn2:
            draft_row = await conn2.fetchrow(
                "SELECT draft_body, classification FROM email_drafts WHERE id = $1",
                draft_id,
            )
        if draft_row:
            from agent1.intelligence.feedback_intel import analyze_rejection
            import asyncio
            asyncio.create_task(analyze_rejection(
                draft_id=draft_id,
                draft_body=draft_row["draft_body"],
                rejection_reason=None,
            ))
    except Exception as exc:
        log.warning("rejection_intel_trigger_failed", error=str(exc))
```

**Step 5: Run tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_feedback_intel.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/agent1/intelligence/feedback_intel.py src/agent1/webhook/routes/admin.py tests/test_feedback_intel.py
git commit -m "feat: add feedback intelligence — qualitative edit and rejection analysis"
```

---

## Task 6: Analytics Engine (Correlation + Adaptive Baselines)

**Files:**
- Create: `src/agent1/intelligence/analytics_engine.py`
- Test: `tests/test_analytics_engine.py`

**Step 1: Write tests**

```python
"""Tests for analytics engine — correlation, baselines, reports."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from agent1.intelligence.analytics_engine import (
    update_baselines,
    is_anomaly,
    update_threshold,
)


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def test_is_anomaly_no_baseline_uses_fallback():
    """Without a baseline, use the fixed threshold of 3."""
    assert is_anomaly("freshdesk", "ticket_updated", 5, baseline=None) is True
    assert is_anomaly("freshdesk", "ticket_updated", 2, baseline=None) is False


def test_is_anomaly_with_baseline():
    """With a baseline, anomaly is mean + 2*stddev."""
    baseline = {"mean": 8.0, "stddev": 2.0}
    # Threshold = 8 + 2*2 = 12
    assert is_anomaly("freshdesk", "ticket_updated", 13, baseline=baseline) is True
    assert is_anomaly("freshdesk", "ticket_updated", 11, baseline=baseline) is False


def test_is_anomaly_minimum_threshold():
    """Even with baseline, minimum threshold is 2."""
    baseline = {"mean": 0.1, "stddev": 0.05}
    # Threshold would be 0.2, but minimum is 2
    assert is_anomaly("freshdesk", "ticket_updated", 3, baseline=baseline) is True
    assert is_anomaly("freshdesk", "ticket_updated", 1, baseline=baseline) is False


@pytest.mark.asyncio
async def test_update_baselines_queries_4_weeks(mock_pool):
    pool, conn = mock_pool
    conn.fetch.return_value = [
        {"source": "freshdesk", "event_type": "ticket_updated",
         "dow": 1, "hod": 9, "mean_count": 8.2, "stddev_count": 2.1},
    ]

    with patch("agent1.intelligence.analytics_engine.get_pool", return_value=pool):
        await update_baselines()

    conn.fetch.assert_called_once()
    # Should have called execute for the upsert
    conn.execute.assert_called()


@pytest.mark.asyncio
async def test_update_threshold(mock_pool):
    pool, conn = mock_pool
    conn.execute.return_value = "UPDATE 1"

    config = {
        "source": "freshdesk",
        "event_type": "ticket_updated",
        "day_of_week": 1,
        "hour_of_day": 9,
        "mean_count": 10.0,
        "stddev_count": 3.0,
    }

    with patch("agent1.intelligence.analytics_engine.get_pool", return_value=pool):
        await update_threshold(config)

    conn.execute.assert_called_once()
```

**Step 2: Run tests to verify failure**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_analytics_engine.py -v`
Expected: ModuleNotFoundError

**Step 3: Implement analytics_engine.py**

Create `src/agent1/intelligence/analytics_engine.py`:

```python
"""Analytics engine -- cross-system correlation, adaptive baselines, intelligence reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.common.settings import get_settings

log = get_logger(__name__)

# In-memory cache of baselines (refreshed weekly)
_baselines_cache: dict[tuple[str, str, int, int], dict] = {}


def is_anomaly(
    source: str,
    event_type: str,
    current_count: int,
    baseline: dict | None = None,
) -> bool:
    """Check if current_count is anomalous for this (source, event_type) at this time.

    If no baseline is available, falls back to the old fixed threshold of 3.
    """
    if baseline is None:
        return current_count >= 3

    threshold = baseline["mean"] + 2 * baseline["stddev"]
    return current_count > max(threshold, 2)


def get_baseline(source: str, event_type: str, day_of_week: int, hour_of_day: int) -> dict | None:
    """Lookup cached baseline for a specific (source, event_type, day, hour)."""
    return _baselines_cache.get((source, event_type, day_of_week, hour_of_day))


async def update_baselines() -> None:
    """Recompute baselines from 4 weeks of historical data. Run weekly."""
    global _baselines_cache
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source, event_type,
                   EXTRACT(DOW FROM created_at)::int AS dow,
                   EXTRACT(HOUR FROM created_at)::int AS hod,
                   AVG(hourly_count) AS mean_count,
                   COALESCE(STDDEV(hourly_count), 0) AS stddev_count
            FROM (
                SELECT source, event_type,
                       DATE_TRUNC('hour', created_at) AS hour_bucket,
                       COUNT(*) AS hourly_count
                FROM events
                WHERE created_at >= NOW() - INTERVAL '28 days'
                  AND status != 'dead_letter'
                GROUP BY source, event_type, hour_bucket
            ) hourly
            GROUP BY source, event_type, dow, hod
            """
        )

        new_cache: dict[tuple[str, str, int, int], dict] = {}
        for r in rows:
            key = (r["source"], r["event_type"], r["dow"], r["hod"])
            baseline = {
                "mean": float(r["mean_count"]),
                "stddev": float(r["stddev_count"]),
            }
            new_cache[key] = baseline

            # Also persist to DB for visibility
            await conn.execute(
                """
                INSERT INTO baselines (source, event_type, day_of_week, hour_of_day,
                                       mean_count, stddev_count, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (source, event_type, day_of_week, hour_of_day) DO UPDATE
                SET mean_count = EXCLUDED.mean_count,
                    stddev_count = EXCLUDED.stddev_count,
                    updated_at = NOW()
                """,
                r["source"], r["event_type"], r["dow"], r["hod"],
                float(r["mean_count"]), float(r["stddev_count"]),
            )

    _baselines_cache = new_cache
    log.info("baselines_updated", count=len(new_cache))


async def load_baselines() -> None:
    """Load baselines from DB into memory cache. Called on startup."""
    global _baselines_cache
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM baselines")

    new_cache = {}
    for r in rows:
        key = (r["source"], r["event_type"], r["day_of_week"], r["hour_of_day"])
        new_cache[key] = {"mean": float(r["mean_count"]), "stddev": float(r["stddev_count"])}

    _baselines_cache = new_cache
    log.info("baselines_loaded", count=len(new_cache))


async def track_event(event_source: str, event_type: str, classification_category: str) -> None:
    """Track an event for correlation analysis. Lightweight -- just log for now."""
    # Correlation tracking will be enhanced in a future iteration
    pass


async def check_correlations(event_source: str, event_type: str) -> list[dict]:
    """Check if recent events form a cross-system pattern.

    Returns a list of correlations found, each with:
    - sources: set of involved systems
    - count: number of related events
    - summary: human-readable description
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get events from last 2 hours, grouped by source
        rows = await conn.fetch(
            """
            SELECT source, event_type, COUNT(*) as count
            FROM events
            WHERE created_at >= NOW() - INTERVAL '2 hours'
              AND status != 'dead_letter'
            GROUP BY source, event_type
            HAVING COUNT(*) >= 2
            ORDER BY count DESC
            """
        )

    if len(rows) < 2:
        return []

    # Find source-spanning patterns: multiple sources with elevated counts
    sources_with_activity = {r["source"] for r in rows}
    if len(sources_with_activity) < 2:
        return []

    total_events = sum(r["count"] for r in rows)
    if total_events < 5:
        return []

    return [{
        "sources": list(sources_with_activity),
        "total_events": total_events,
        "breakdown": [
            {"source": r["source"], "event_type": r["event_type"], "count": r["count"]}
            for r in rows
        ],
        "summary": (
            f"Cross-system activity: {total_events} events across "
            f"{', '.join(sources_with_activity)} in last 2 hours"
        ),
    }]


async def update_threshold(config: dict) -> None:
    """Update a single baseline entry from an approved threshold_adjustment proposal."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO baselines (source, event_type, day_of_week, hour_of_day,
                                   mean_count, stddev_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (source, event_type, day_of_week, hour_of_day) DO UPDATE
            SET mean_count = EXCLUDED.mean_count,
                stddev_count = EXCLUDED.stddev_count,
                updated_at = NOW()
            """,
            config["source"],
            config["event_type"],
            config["day_of_week"],
            config["hour_of_day"],
            config["mean_count"],
            config["stddev_count"],
        )

    # Update in-memory cache too
    key = (config["source"], config["event_type"], config["day_of_week"], config["hour_of_day"])
    _baselines_cache[key] = {"mean": config["mean_count"], "stddev": config["stddev_count"]}
    log.info("threshold_updated", key=str(key))


async def generate_morning_brief() -> str:
    """Generate an enhanced morning intelligence brief."""
    pool = await get_pool()
    now = datetime.now(UTC)

    async with pool.acquire() as conn:
        events_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )
        failed_24h = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE status = 'failed' AND created_at >= NOW() - INTERVAL '24 hours'"
        )
        pending_drafts = await conn.fetchval(
            "SELECT COUNT(*) FROM email_drafts WHERE status = 'pending'"
        )
        dlq_count = await conn.fetchval(
            "SELECT COUNT(*) FROM dead_letter_events WHERE resolved_at IS NULL"
        )

        # Pending proposals
        pending_proposals = await conn.fetchval(
            "SELECT COUNT(*) FROM proposals WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > NOW())"
        )
        proposal_types = await conn.fetch(
            """
            SELECT type, COUNT(*) as count FROM proposals
            WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > NOW())
            GROUP BY type ORDER BY count DESC
            """
        )

        # Approval rate trend (last 7 days)
        approval_stats = await conn.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE status = 'approved' OR status = 'sent') AS approved,
                   COUNT(*) FILTER (WHERE edited_body IS NOT NULL) AS edited,
                   COUNT(*) AS total
            FROM email_drafts
            WHERE created_at >= NOW() - INTERVAL '7 days'
              AND status != 'pending'
            """
        )

        # Top event sources
        top_sources = await conn.fetch(
            """
            SELECT source, COUNT(*) AS count FROM events
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY source ORDER BY count DESC LIMIT 5
            """
        )

    # Build brief
    sources_str = ", ".join(f"{r['source']}: {r['count']}" for r in top_sources) if top_sources else "none"
    proposals_str = ", ".join(f"{r['type']}: {r['count']}" for r in proposal_types) if proposal_types else "none"

    approval_rate = 0
    edit_rate = 0
    if approval_stats and approval_stats["total"]:
        approval_rate = round(approval_stats["approved"] / approval_stats["total"] * 100)
        if approval_stats["approved"]:
            edit_rate = round(approval_stats["edited"] / approval_stats["approved"] * 100)

    brief = (
        f"**Morning Intelligence Brief** -- {now.strftime('%Y-%m-%d')}\n\n"
        f"**Overnight Summary**\n"
        f"- {events_24h} events processed, {failed_24h} failed\n"
        f"- {pending_drafts} drafts pending approval\n"
        f"- {dlq_count} DLQ entries unresolved\n"
        f"- Top sources: {sources_str}\n\n"
    )

    if pending_proposals > 0:
        brief += (
            f"**Pending Proposals ({pending_proposals})**\n"
            f"- Types: {proposals_str}\n"
            f"- Review in Dashboard to approve/reject\n\n"
        )

    if approval_stats and approval_stats["total"] > 0:
        brief += (
            f"**Agent Performance (7-day)**\n"
            f"- Draft approval rate: {approval_rate}%\n"
            f"- Edit rate (of approved): {edit_rate}%\n"
        )

    if dlq_count > 0:
        brief += f"\n:warning: {dlq_count} events in dead-letter queue need attention."

    return brief
```

**Step 4: Run tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_analytics_engine.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/agent1/intelligence/analytics_engine.py tests/test_analytics_engine.py
git commit -m "feat: add analytics engine — adaptive baselines, correlation detection, morning brief"
```

---

## Task 7: Solution Factory (Script Runner + MCP Discovery + Automations)

**Files:**
- Create: `src/agent1/intelligence/solutions/__init__.py`
- Create: `src/agent1/intelligence/solutions/script_runner.py`
- Create: `src/agent1/intelligence/solutions/mcp_discovery.py`
- Create: `src/agent1/intelligence/solutions/factory.py`
- Test: `tests/test_script_runner.py`

**Step 1: Write tests for script runner**

```python
"""Tests for the sandboxed script runner."""

from __future__ import annotations

import pytest

from agent1.intelligence.solutions.script_runner import (
    validate_code,
    run_script,
    ALLOWED_IMPORTS,
    BLOCKED_IMPORTS,
)


def test_validate_code_allows_clean_code():
    code = '''
async def run(*, city: str) -> str:
    import json
    return json.dumps({"city": city})
'''
    assert validate_code(code) is None


def test_validate_code_blocks_os():
    code = "import os\nos.system('rm -rf /')"
    error = validate_code(code)
    assert error is not None
    assert "os" in error.lower() or "blocked" in error.lower()


def test_validate_code_blocks_subprocess():
    code = "import subprocess\nsubprocess.run(['ls'])"
    error = validate_code(code)
    assert error is not None


def test_validate_code_blocks_eval():
    code = "result = eval('1+1')"
    error = validate_code(code)
    assert error is not None


def test_validate_code_blocks_open():
    code = "f = open('/etc/passwd')\nresult = f.read()"
    error = validate_code(code)
    assert error is not None


def test_validate_code_allows_requests():
    code = '''
async def run(*, url: str) -> str:
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.text
'''
    assert validate_code(code) is None


def test_validate_code_catches_syntax_error():
    code = "def broken(:\n  pass"
    error = validate_code(code)
    assert error is not None
    assert "syntax" in error.lower()


@pytest.mark.asyncio
async def test_run_script_simple():
    code = '''
async def run(*, name: str) -> str:
    return f"Hello, {name}!"
'''
    result = await run_script(code, {"name": "Agent"})
    assert result == "Hello, Agent!"


@pytest.mark.asyncio
async def test_run_script_timeout():
    code = '''
import asyncio
async def run() -> str:
    await asyncio.sleep(100)
    return "done"
'''
    result = await run_script(code, {}, timeout=1)
    assert "timed out" in str(result).lower() or "timeout" in str(result).lower()


@pytest.mark.asyncio
async def test_run_script_error_handled():
    code = '''
async def run() -> str:
    raise ValueError("test error")
'''
    result = await run_script(code, {})
    assert "error" in str(result).lower()
```

**Step 2: Run tests to verify failure**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_script_runner.py -v`
Expected: ModuleNotFoundError

**Step 3: Implement solutions package**

Create `src/agent1/intelligence/solutions/__init__.py`:

```python
"""Solution factory — self-tooling, scripts, automations, MCP discovery."""
```

Create `src/agent1/intelligence/solutions/script_runner.py`:

```python
"""Sandboxed Python script execution for agent-created solutions."""

from __future__ import annotations

import asyncio
import re
import textwrap
from typing import Any

from agent1.common.logging import get_logger

log = get_logger(__name__)

ALLOWED_IMPORTS = frozenset({
    "requests", "httpx", "json", "csv", "re", "datetime", "urllib.parse",
    "math", "statistics", "collections", "itertools",
    "textwrap", "string", "html", "base64", "hashlib", "uuid", "decimal",
})

BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "importlib", "ctypes", "pickle",
})

BLOCKED_PATTERNS = [
    re.compile(r"\bimport\s+(" + "|".join(BLOCKED_IMPORTS) + r")\b"),
    re.compile(r"\bfrom\s+(" + "|".join(BLOCKED_IMPORTS) + r")\s+import\b"),
    re.compile(r"\b(eval|exec|compile|__import__)\s*\("),
    re.compile(r"\b(globals|locals|vars)\s*\("),
    re.compile(r"\bopen\s*\("),
    re.compile(r"\b__\w+__"),
]

MAX_EXECUTION_TIME = 60
MAX_OUTPUT_SIZE = 50_000


def validate_code(code: str) -> str | None:
    """Validate code safety. Returns error message or None if valid."""
    for pattern in BLOCKED_PATTERNS:
        match = pattern.search(code)
        if match:
            return f"Blocked pattern: {match.group()}"

    try:
        compile(code, "<solution_script>", "exec")
    except SyntaxError as e:
        return f"Syntax error: {e}"

    return None


async def run_script(
    code: str,
    params: dict[str, Any],
    timeout: int = MAX_EXECUTION_TIME,
) -> Any:
    """Execute a script in a restricted sandbox.

    The script must define an async function named 'run' that takes keyword arguments.
    Returns the function's return value, or an error dict.
    """
    import httpx
    import json as json_mod

    # Build restricted scope
    scope: dict[str, Any] = {
        "httpx": httpx,
        "json": json_mod,
        "re": re,
        "asyncio": asyncio,
        "math": __import__("math"),
        "datetime": __import__("datetime"),
        "statistics": __import__("statistics"),
        "collections": __import__("collections"),
        "params": params,
        "result": None,
    }

    wrapped = textwrap.dedent(code)

    try:
        exec(compile(wrapped, "<solution>", "exec"), scope)

        if callable(scope.get("run")):
            coro = scope["run"](**params)
            if asyncio.iscoroutine(coro):
                return await asyncio.wait_for(coro, timeout=timeout)
            return coro

        return scope.get("result", "Script executed (no 'run' function or result)")

    except asyncio.TimeoutError:
        return {"error": f"Script timed out after {timeout}s"}
    except Exception as exc:
        log.error("script_execution_error", error=str(exc))
        return {"error": str(exc)}
```

Create `src/agent1/intelligence/solutions/mcp_discovery.py`:

```python
"""MCP server discovery — find and propose new tool integrations."""

from __future__ import annotations

from agent1.common.logging import get_logger
from agent1.intelligence.proposals import create_proposal, ProposalType

log = get_logger(__name__)


async def search_mcp_registries(capability: str) -> list[dict]:
    """Search MCP registries for servers matching a capability description.

    Searches Smithery.ai and returns top matches.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Smithery.ai registry search
            response = await client.get(
                "https://registry.smithery.ai/servers",
                params={"q": capability, "limit": 5},
            )
            if response.status_code == 200:
                data = response.json()
                return [
                    {
                        "name": s.get("qualifiedName", s.get("name", "")),
                        "description": s.get("description", ""),
                        "url": s.get("homepage", ""),
                    }
                    for s in data.get("servers", [])[:3]
                ]
    except Exception:
        log.warning("mcp_registry_search_failed", capability=capability)

    return []


async def propose_mcp_server(
    name: str,
    description: str,
    config: dict,
    reason: str,
) -> None:
    """Create a proposal to connect a new MCP server."""
    await create_proposal(
        type=ProposalType.MCP_SERVER,
        title=f"Connect MCP: {name}",
        description=f"{description}\n\nReason: {reason}",
        config=config,
        confidence=0.5,
    )
    log.info("mcp_server_proposed", name=name)
```

Create `src/agent1/intelligence/solutions/factory.py`:

```python
"""Solution factory — orchestrates tool creation, script building, and automation proposals."""

from __future__ import annotations

import json

from agent1.common.db import get_pool
from agent1.common.logging import get_logger
from agent1.intelligence.proposals import create_proposal, ProposalType
from agent1.intelligence.solutions.script_runner import validate_code

log = get_logger(__name__)


async def propose_solution(
    *,
    name: str,
    description: str,
    solution_type: str,
    code: str | None = None,
    config: dict | None = None,
    trigger_pattern: str | None = None,
) -> None:
    """Create a solution proposal for operator review."""
    proposal_type = ProposalType.TOOL_CREATION
    if solution_type == "automation":
        proposal_type = ProposalType.AUTOMATION

    await create_proposal(
        type=proposal_type,
        title=f"Solution: {name}",
        description=description,
        code=code,
        config=config,
        evidence=f"Trigger: {trigger_pattern}" if trigger_pattern else None,
        confidence=0.5,
    )
    log.info("solution_proposed", name=name, type=solution_type)


async def activate_tool(proposal: dict) -> None:
    """Activate an approved tool_creation proposal."""
    code = proposal.get("code", "")
    if not code:
        log.warning("activate_tool_no_code", proposal_id=str(proposal["id"]))
        return

    # Validate code
    error = validate_code(code)
    if error:
        log.error("activate_tool_code_invalid", error=error)
        return

    # Store in solutions table
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO solutions (name, description, solution_type, code, status,
                                   approved_at, approved_by, active)
            VALUES ($1, $2, 'tool', $3, 'active', NOW(), $4, true)
            """,
            proposal.get("title", "unnamed_tool"),
            proposal.get("description", ""),
            code,
            proposal.get("reviewed_by", "operator"),
        )

    # Register as dynamic tool
    try:
        from agent1.tools.mcp.builder import DynamicTool
        from agent1.tools.registry import register_tool

        tool_name = f"solution__{proposal.get('title', 'tool').lower().replace(' ', '_')[:30]}"
        tool = DynamicTool(
            tool_name=tool_name,
            tool_description=proposal.get("description", ""),
            tool_input_schema=json.loads(proposal["config"]) if proposal.get("config") else {"type": "object", "properties": {}},
            tool_code=code,
        )
        register_tool(tool)
        log.info("solution_tool_activated", tool=tool_name)
    except Exception:
        log.exception("solution_tool_registration_failed")


async def activate_automation(proposal: dict) -> None:
    """Activate an approved automation proposal."""
    config = proposal.get("config")
    if isinstance(config, str):
        config = json.loads(config)
    if not config:
        log.warning("activate_automation_no_config", proposal_id=str(proposal["id"]))
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Store solution
        solution_id = await conn.fetchval(
            """
            INSERT INTO solutions (name, description, solution_type, code, config, status,
                                   approved_at, approved_by, active)
            VALUES ($1, $2, 'automation', $3, $4::jsonb, 'active', NOW(), $5, true)
            RETURNING id
            """,
            proposal.get("title", "unnamed_automation"),
            proposal.get("description", ""),
            proposal.get("code"),
            json.dumps(config),
            proposal.get("reviewed_by", "operator"),
        )

        # Create automation entry
        await conn.execute(
            """
            INSERT INTO automations (solution_id, name, trigger_type, trigger_config, active)
            VALUES ($1, $2, $3, $4::jsonb, true)
            """,
            solution_id,
            proposal.get("title", "unnamed"),
            config.get("trigger_type", "cron"),
            json.dumps(config.get("trigger_config", {})),
        )

    log.info("automation_activated", solution_id=str(solution_id))


async def get_active_solutions(solution_type: str | None = None) -> list[dict]:
    """Get all active solutions."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if solution_type:
            rows = await conn.fetch(
                "SELECT * FROM solutions WHERE active = true AND solution_type = $1 ORDER BY created_at DESC",
                solution_type,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM solutions WHERE active = true ORDER BY created_at DESC"
            )
    return [dict(r) for r in rows]
```

**Step 4: Run tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_script_runner.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/agent1/intelligence/solutions/ tests/test_script_runner.py
git commit -m "feat: add solution factory — script runner, MCP discovery, automation builder"
```

---

## Task 8: Wire Intelligence Into Worker Loop + Scheduler

**Files:**
- Modify: `src/agent1/worker/loop.py` (add Steps 1.5 and 5.5)
- Modify: `src/agent1/worker/pollers/scheduler.py` (wire baselines, enhanced reports)
- Modify: `src/agent1/worker/pattern_detector.py` (use adaptive baselines)

**Step 1: Add Step 1.5 (context enrichment) to worker loop**

In `src/agent1/worker/loop.py`, in the `process_event` function, after the Step 1c summary handling block (around line 113 which returns early for summaries), add before Step 2:

```python
    # Step 1.5: Context enrichment (NEW)
    enriched_context = None
    try:
        from agent1.intelligence.context_engine import enrich
        enriched_context = await enrich(event, classification)
        if enriched_context and enriched_context.token_estimate > 0:
            log.info(
                "context_enriched",
                event_id=str(event.id),
                tokens=enriched_context.token_estimate,
                incidents=len(enriched_context.similar_incidents),
                knowledge=len(enriched_context.relevant_knowledge),
            )
    except Exception:
        log.warning("context_enrichment_failed", event_id=str(event.id))
```

Then update the `reason_and_act` call (around line 130) to pass the enriched context:

Change:
```python
    result = await reason_and_act(event, classification, plan)
```
To:
```python
    result = await reason_and_act(event, classification, plan, enriched_context)
```

**Step 2: Add Step 5.5 (post-action intelligence) to worker loop**

After the Step 5 action logging block (after `_log_action` and the event status update), before the final `log.info("event_processed", ...)`, add:

```python
    # Step 5.5: Post-action intelligence (NEW)
    try:
        from agent1.intelligence.analytics_engine import track_event, check_correlations
        await track_event(event.source.value, event.event_type, classification.category)

        correlations = await check_correlations(event.source.value, event.event_type)
        if correlations:
            try:
                from agent1.tools.google_chat import GChatPostMessageTool
                chat = GChatPostMessageTool()
                for c in correlations:
                    await chat.execute(
                        space="alerts",
                        message=f"**Cross-system pattern:** {c['summary']}",
                    )
            except Exception:
                log.warning("correlation_alert_failed")
    except Exception:
        log.warning("post_action_intel_failed", event_id=str(event.id))
```

**Step 3: Wire baselines and reports into scheduler**

In `src/agent1/worker/pollers/scheduler.py`, add these new scheduler functions before `run_scheduler()`:

```python
async def _run_baseline_update() -> None:
    """Update adaptive baselines from historical data. Run weekly."""
    from agent1.intelligence.analytics_engine import update_baselines
    await update_baselines()


async def _run_load_baselines() -> None:
    """Load baselines from DB on startup."""
    try:
        from agent1.intelligence.analytics_engine import load_baselines
        await load_baselines()
    except Exception:
        pass  # Table may not exist yet
```

In the `run_scheduler()` function, add after the log.info("scheduler_started") line:

```python
    # Load baselines on startup
    await _run_load_baselines()
```

In the cron-like checks section inside the while loop, add after the daily_summary check:

```python
            # Weekly baseline update (Sunday midnight)
            if now.weekday() == 6 and now.hour == 0 and now.minute < (interval // 60 + 1):
                try:
                    await _run_baseline_update()
                except Exception:
                    log.exception("baseline_update_error")
```

**Step 4: Update pattern detector to use adaptive baselines**

In `src/agent1/worker/pattern_detector.py`, update `_detect_ticket_spikes()` to use the adaptive baseline:

Replace the `HAVING COUNT(*) >= 3` in the SQL with `HAVING COUNT(*) >= 2` (lower floor since baselines handle the real threshold), and add after the `for row in rows:` loop body:

After `if already_alerted: continue`, add:

```python
        # Check against adaptive baseline
        from agent1.intelligence.analytics_engine import get_baseline, is_anomaly
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        baseline = get_baseline(row["source"], row["event_type"], now.weekday(), now.hour)
        if not is_anomaly(row["source"], row["event_type"], row["count"], baseline):
            continue
```

**Step 5: Run all tests to verify nothing broke**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/agent1/worker/loop.py src/agent1/worker/pollers/scheduler.py src/agent1/worker/pattern_detector.py
git commit -m "feat: wire intelligence into worker loop (Steps 1.5 + 5.5), scheduler, and pattern detector"
```

---

## Task 9: Admin API — Proposals CRUD + Solutions Endpoints

**Files:**
- Modify: `src/agent1/webhook/routes/admin.py` (add ~80 lines for new endpoints)

**Step 1: Add proposal endpoints to admin.py**

Add these at the end of `src/agent1/webhook/routes/admin.py` (before the final closing), with these imports at the top:

```python
from uuid import UUID
```

New endpoints:

```python
# --- Proposals ---


@router.get("/proposals")
async def list_proposals(status: str = "pending", type: Optional[str] = None, limit: int = 20):
    """List proposals by status, optionally filtered by type."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if type:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at, reviewed_at, reviewed_by
                FROM proposals
                WHERE status = $1 AND type = $2
                ORDER BY confidence DESC, created_at DESC
                LIMIT $3
                """,
                status, type, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, type, title, description, evidence, code, config,
                       confidence, status, created_at, expires_at, reviewed_at, reviewed_by
                FROM proposals
                WHERE status = $1
                ORDER BY confidence DESC, created_at DESC
                LIMIT $2
                """,
                status, limit,
            )
    return [dict(r) for r in rows]


@router.get("/proposals/stats")
async def proposal_stats():
    """Get proposal counts by type and status."""
    from agent1.intelligence.proposals import get_proposal_stats
    return await get_proposal_stats()


@router.get("/proposals/{proposal_id}")
async def get_proposal_detail(proposal_id: str):
    """Get a single proposal by UUID."""
    from agent1.intelligence.proposals import get_proposal
    proposal = await get_proposal(UUID(proposal_id))
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


class ProposalApproveBody(BaseModel):
    notes: Optional[str] = None
    edited_description: Optional[str] = None


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal_endpoint(proposal_id: str, body: ProposalApproveBody = ProposalApproveBody()):
    """Approve a pending proposal."""
    from agent1.intelligence.proposals import approve_proposal
    success = await approve_proposal(
        UUID(proposal_id),
        notes=body.notes,
        edited_description=body.edited_description,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found or not pending")
    return {"status": "approved", "proposal_id": proposal_id}


class ProposalRejectBody(BaseModel):
    reason: Optional[str] = None


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal_endpoint(proposal_id: str, body: ProposalRejectBody = ProposalRejectBody()):
    """Reject a pending proposal."""
    from agent1.intelligence.proposals import reject_proposal
    success = await reject_proposal(UUID(proposal_id), reason=body.reason)
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found or not pending")
    return {"status": "rejected", "proposal_id": proposal_id}


# --- Solutions ---


@router.get("/solutions")
async def list_solutions(type: Optional[str] = None):
    """List active solutions (tools, automations, scripts)."""
    from agent1.intelligence.solutions.factory import get_active_solutions
    return await get_active_solutions(type)
```

**Step 2: Update status endpoint to include proposal count**

In the `admin_status` function, after the `dlq_count` query, add:

```python
        pending_proposals = 0
        try:
            pending_proposals = await conn.fetchval(
                "SELECT COUNT(*) FROM proposals WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > NOW())"
            ) or 0
        except Exception:
            pass  # Table may not exist yet
```

And add to the return dict:
```python
        "pending_proposals": pending_proposals,
```

**Step 3: Run relevant tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest tests/test_webhook_routes.py -v`
Expected: Existing tests pass

**Step 4: Commit**

```bash
git add src/agent1/webhook/routes/admin.py
git commit -m "feat: add proposals CRUD and solutions endpoints to admin API"
```

---

## Task 10: Dashboard — Proposals Section

**Files:**
- Create: `dashboard/app/(dashboard)/proposals/page.tsx`
- Modify: `dashboard/components/shell/Sidebar.tsx` (add nav entry)
- Modify: `dashboard/lib/types.ts` (add Proposal type)

**Step 1: Add Proposal type to types.ts**

Append to `dashboard/lib/types.ts`:

```typescript
export interface Proposal {
  id: string;
  type: string;
  title: string;
  description: string;
  evidence: string | null;
  code: string | null;
  config: Record<string, unknown> | null;
  confidence: number;
  status: string;
  created_at: string;
  expires_at: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export const PROPOSAL_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  learned_rule: { label: "Rule", color: "text-cyan-400" },
  strong_rule: { label: "Strong Rule", color: "text-cyan-300" },
  tool_creation: { label: "Tool", color: "text-amber-400" },
  automation: { label: "Automation", color: "text-purple-400" },
  mcp_server: { label: "MCP", color: "text-emerald-400" },
  guardrail_override: { label: "Override", color: "text-red-400" },
  threshold_adjustment: { label: "Threshold", color: "text-indigo-400" },
  playbook_suggestion: { label: "Playbook", color: "text-slate-400" },
};
```

**Step 2: Create proposals page**

Create `dashboard/app/(dashboard)/proposals/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { Lightbulb, Check, X, ChevronDown, ChevronRight, Code2, Clock } from "lucide-react";
import type { Proposal } from "@/lib/types";
import { PROPOSAL_TYPE_CONFIG, timeAgo } from "@/lib/types";

export default function ProposalsPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"pending" | "approved" | "rejected">("pending");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const fetchProposals = useCallback(async () => {
    try {
      const res = await fetch(`/api/admin/proposals?status=${filter}&limit=50`);
      if (res.ok) setProposals(await res.json());
    } catch {
      // API not available
    }
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    setLoading(true);
    fetchProposals();
    const interval = setInterval(fetchProposals, 15000);
    return () => clearInterval(interval);
  }, [fetchProposals]);

  const handleApprove = async (id: string) => {
    const res = await fetch(`/api/admin/proposals/${id}/approve`, { method: "POST" });
    if (res.ok) fetchProposals();
  };

  const handleReject = async (id: string) => {
    const res = await fetch(`/api/admin/proposals/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Rejected from dashboard" }),
    });
    if (res.ok) fetchProposals();
  };

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-2">
        {(["pending", "approved", "rejected"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              filter === f
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                : "bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : proposals.length === 0 ? (
        <p className="text-center text-[var(--color-text-muted)] py-20 text-sm">
          No {filter} proposals
        </p>
      ) : (
        <div className="space-y-2">
          {proposals.map((p) => {
            const typeConfig = PROPOSAL_TYPE_CONFIG[p.type] || { label: p.type, color: "text-[var(--color-text-muted)]" };
            const isExpanded = expandedIds.has(p.id);

            return (
              <div key={p.id} className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
                <div
                  onClick={() => toggleExpand(p.id)}
                  className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-[var(--color-surface-hover)] transition-colors"
                >
                  {isExpanded ? (
                    <ChevronDown size={14} className="text-[var(--color-text-muted)] shrink-0" />
                  ) : (
                    <ChevronRight size={14} className="text-[var(--color-text-dim)] shrink-0" />
                  )}

                  <Lightbulb size={14} className="text-amber-400 shrink-0" />

                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-hover)] ${typeConfig.color}`}>
                    {typeConfig.label}
                  </span>

                  <span className="flex-1 text-xs truncate">{p.title}</span>

                  <span className="text-[10px] text-[var(--color-text-dim)]">
                    {Math.round(p.confidence * 100)}%
                  </span>

                  <span className="text-[10px] text-[var(--color-text-dim)] font-mono flex items-center gap-1">
                    <Clock size={10} />
                    {timeAgo(p.created_at)}
                  </span>

                  {filter === "pending" && (
                    <div className="flex items-center gap-1 ml-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleApprove(p.id)}
                        className="p-1.5 rounded hover:bg-emerald-500/20 text-emerald-400 transition-colors"
                        title="Approve"
                      >
                        <Check size={14} />
                      </button>
                      <button
                        onClick={() => handleReject(p.id)}
                        className="p-1.5 rounded hover:bg-red-500/20 text-red-400 transition-colors"
                        title="Reject"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  )}
                </div>

                {isExpanded && (
                  <div className="px-4 py-3 border-t border-[var(--color-border)] space-y-2 text-xs">
                    <div>
                      <span className="text-[var(--color-text-muted)] font-medium">Description: </span>
                      <span className="whitespace-pre-wrap">{p.description}</span>
                    </div>

                    {p.evidence && (
                      <div>
                        <span className="text-[var(--color-text-muted)] font-medium">Evidence: </span>
                        <span className="text-[var(--color-text-dim)]">{p.evidence}</span>
                      </div>
                    )}

                    {p.code && (
                      <div>
                        <div className="flex items-center gap-1 text-[var(--color-text-muted)] font-medium mb-1">
                          <Code2 size={12} />
                          Code:
                        </div>
                        <pre className="p-2 rounded bg-[var(--color-bg)] text-[10px] font-mono overflow-x-auto max-h-48">
                          {p.code}
                        </pre>
                      </div>
                    )}

                    {p.reviewed_by && (
                      <div className="text-[10px] text-[var(--color-text-dim)]">
                        Reviewed by {p.reviewed_by} {p.reviewed_at ? timeAgo(p.reviewed_at) : ""}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

**Step 3: Add nav entry in Sidebar**

In `dashboard/components/shell/Sidebar.tsx`, add a nav entry for Proposals. Find the nav items array and add:

```tsx
{ href: "/proposals", icon: Lightbulb, label: "Proposals" },
```

Import `Lightbulb` from lucide-react at the top of the file.

**Step 4: Type check**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent/dashboard && npx tsc --noEmit`
Expected: No errors

**Step 5: Commit**

```bash
git add dashboard/app/\(dashboard\)/proposals/page.tsx dashboard/components/shell/Sidebar.tsx dashboard/lib/types.ts
git commit -m "feat: add proposals page to dashboard with approve/reject UI"
```

---

## Task 11: Update AgentStatus Type + Status Endpoint

**Files:**
- Modify: `dashboard/lib/types.ts` (add `pending_proposals` to AgentStatus)

**Step 1: Update AgentStatus interface**

In `dashboard/lib/types.ts`, add `pending_proposals: number;` to the `AgentStatus` interface (after `is_paused: boolean;`).

**Step 2: Type check**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent/dashboard && npx tsc --noEmit`
Expected: No errors (or fix any pages that destructure AgentStatus and need the new field)

**Step 3: Commit**

```bash
git add dashboard/lib/types.ts
git commit -m "feat: add pending_proposals to AgentStatus type"
```

---

## Task 12: Deploy and Verify

**Step 1: Run all Python tests**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent && uv run pytest -v`
Expected: All tests pass

**Step 2: Run dashboard type check**

Run: `cd C:/git-projects/the_agent/glamira-ops-agent/dashboard && npx tsc --noEmit`
Expected: No errors

**Step 3: Deploy backend to Railway**

```bash
MSYS_NO_PATHCONV=1 /c/Users/LENOVO/AppData/Roaming/npm/railway.cmd service webhook
MSYS_NO_PATHCONV=1 /c/Users/LENOVO/AppData/Roaming/npm/railway.cmd up
MSYS_NO_PATHCONV=1 /c/Users/LENOVO/AppData/Roaming/npm/railway.cmd service worker
MSYS_NO_PATHCONV=1 /c/Users/LENOVO/AppData/Roaming/npm/railway.cmd up
```

**Step 4: Deploy dashboard to Vercel**

```bash
cd C:/git-projects/the_agent/glamira-ops-agent/dashboard && npx vercel --prod
```

**Step 5: Verify**

1. Check health: `curl https://webhook-production-50a3.up.railway.app/health`
2. Check status: `curl https://webhook-production-50a3.up.railway.app/admin/status` — should include `pending_proposals: 0`
3. Check proposals endpoint: `curl https://webhook-production-50a3.up.railway.app/admin/proposals?status=pending` — should return `[]`
4. Open dashboard proposals page: `https://dashboard-alpha-lovat-14.vercel.app/proposals`
5. Test guardrails notification: inject a financial event and verify a proposal is created

---

## Summary

| Task | Description | New/Modified Files |
|------|-------------|-------------------|
| 1 | Migration 004 | 1 new |
| 2 | Proposals system | 2 new + 1 test |
| 3 | Context engine + engine.py integration | 1 new + 1 modified + 1 test |
| 4 | Guardrails fix | 1 modified + 1 test modified |
| 5 | Feedback intelligence | 1 new + 1 modified + 1 test |
| 6 | Analytics engine | 1 new + 1 test |
| 7 | Solution factory | 4 new + 1 test |
| 8 | Worker loop + scheduler + pattern detector wiring | 3 modified |
| 9 | Admin API proposals endpoints | 1 modified |
| 10 | Dashboard proposals page | 2 new + 1 modified |
| 11 | AgentStatus type update | 1 modified |
| 12 | Deploy + verify | 0 |

**Total: 12 new files, 8 modified files, 5 test files, 12 commits**
