# Intelligence Upgrade Design

**Date:** 2026-02-20
**Status:** Approved
**Approach:** A — 3 New Subsystems in `intelligence/` package

## Goal

Make The Agent1 genuinely smarter: better decisions through contextual retrieval, qualitative learning from operator corrections, cross-system pattern correlation, adaptive thresholds, proactive solution building (scripts, tools, MCP integrations), and intelligence reporting — all gated by a universal proposal-and-approval workflow.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Approach | 3 new subsystems | Best modularity, testability, each deployable independently |
| Approval model | Keep current + fix gaps | All learning goes through proposals; guardrail blocks get notifications |
| Learning autonomy | Propose changes, operator approves | Nothing auto-applies; agent proposes, human decides |
| Analysis scope | Real-time correlation + periodic reports | Cross-system root cause + daily/weekly intelligence briefs |
| Cost strategy | Keep reasonable | Flash for pre-retrieval and analysis; Pro only for complex events |

---

## Architecture Overview

```
                    +----------------------------------+
                    |         Worker Loop              |
                    |                                  |
  Event ---------->|  Step 1: Classify                 |
                    |  Step 1.5: Context Engine <------+---- pgvector (incidents, knowledge, actions)
                    |  Step 2: Plan                    |
                    |  Step 3: Guardrails -------------+---- if blocked -> notify Chat + create proposal
                    |  Step 4: Reason + Tools          |
                    |  Step 5: Log                     |
                    |  Step 5.5: Post-Action Intel ----+---- correlation update, feedback trigger
                    |                                  |
                    +----------------------------------+
                                    |
                    +---------------+-------------------+
                    |               |                   |
              +-----v-----+  +-----v------+  +--------v--------+
              |  Context   |  |  Feedback   |  |   Analytics     |
              |  Engine    |  |  Intel      |  |   Engine        |
              +-----+-----+  +-----+------+  +--------+--------+
                    |               |                   |
                    +---------------+-------------------+
                                    |
                    +---------------v-------------------+
                    |         Proposals System          |
                    |   (universal approval workflow)   |
                    +----------------------------------+
                                    |
                    +---------------v-------------------+
                    |      Solution Factory             |
                    |  (scripts, tools, automations,    |
                    |   MCP discovery)                  |
                    +----------------------------------+
                                    |
                    +---------------v-------------------+
                    |    Dashboard + Google Chat        |
                    |    (review & approve)             |
                    +----------------------------------+
```

## New Package Structure

```
src/agent1/intelligence/
  __init__.py
  context_engine.py        # Pre-reasoning context retrieval
  feedback_intel.py        # Qualitative edit/rejection analysis
  analytics_engine.py      # Correlation, adaptive patterns, reports
  proposals.py             # Universal approval workflow
  solutions/
    __init__.py
    factory.py             # Solution proposal & creation orchestrator
    script_runner.py       # Sandboxed Python execution engine
    mcp_discovery.py       # Find & connect MCP servers from registries
    automation.py          # Create scheduled tasks, pollers, monitors
```

---

## 1. Context Engine (`context_engine.py`)

Runs as Step 1.5 after classification. Retrieves relevant context so the reasoning engine makes better decisions without relying on the model to call `memory_search`.

### Interface

```python
@dataclass
class EnrichedContext:
    similar_incidents: list[dict]      # Past incidents with resolution (max 3)
    sender_history: list[dict]         # Previous interactions with this sender (max 5)
    relevant_knowledge: list[dict]     # Knowledge rules by semantic relevance (max 5)
    related_recent_events: list[dict]  # Events from same source/topic in last 24h (max 5)
    context_summary: str               # Flash-generated 2-3 sentence summary (if needed)
    token_estimate: int                # Estimated tokens this context adds to prompt
```

### How `enrich()` works

1. **Extract search query** from event payload (subject, first 200 chars body, sender). Pure extraction, no AI.
2. **Parallel pgvector queries** (3 concurrent):
   - `search_incidents(query, limit=3, threshold=0.55)` — past incidents with resolutions
   - `search_knowledge(query, limit=5, threshold=0.5)` — rules by semantic relevance (NOT recency)
   - `search_actions(query, limit=5, threshold=0.5)` — past actions for similar events
3. **SQL queries** (2 concurrent):
   - `get_sender_history(sender_email)` — last 5 interactions from actions_log
   - `get_related_events(source, event_type, hours=24)` — recent events of same type
4. **Conditional summary**: If total context > 2000 tokens, use Flash to condense. Otherwise pass raw.
5. **Token budget**: Trim to 3000 tokens max, keeping highest-relevance items.

### How context is injected

In `engine.py`, the enriched context replaces the current "last 10 taught rules" injection:

```
## Relevant Context (auto-retrieved)
### Similar Past Incidents:
- [2024-11-15] Delivery delay in DE -> resolved by escalating to logistics (similarity: 0.87)

### Sender History:
- Last contact 3 days ago re: order DE-45123 (resolved, 2 interactions)

### Relevant Rules:
- "For .de customers complaining about delivery, check parcel tracker first"

### Recent Related Events (last 24h):
- 2 other Freshdesk tickets about delivery delays (DE market)
```

### Cost per event
- DB queries: ~15ms total, $0
- Flash summary (only when context > 2000 tokens, ~10% of events): ~$0.0005
- **90% of events: $0 enrichment cost**

---

## 2. Feedback Intelligence (`feedback_intel.py`)

Replaces quantitative-only feedback with qualitative understanding of operator corrections.

### Triggers

**Draft edit analysis** — when operator approves with edits:
- Flash analyzes the diff between original and edited draft
- Extracts specific changes: tone, greeting, length, content, structure
- For each change, creates a `learned_rule` proposal with concrete actionable instruction
- Cost: ~$0.0005 per edit

**Draft rejection analysis** — when operator rejects:
- Flash analyzes what was wrong given the event context
- Creates a proposal with what the agent should do differently
- Cost: ~$0.0005 per rejection

**Pattern aggregation** — runs every 6 hours:
- Clusters similar pending proposals by embedding similarity (threshold 0.8)
- Clusters with 3+ similar proposals → merged into `strong_rule` with higher confidence
- Merged rule supersedes individual proposals

### Confidence scoring
- Single edit → 0.6 confidence
- 3+ consistent edits → 0.6 + 0.1 * count (capped at 0.95)
- Rejection → 0.7 confidence (explicit negative signal)

---

## 3. Analytics Engine (`analytics_engine.py`)

### 3a. Cross-System Correlation

Runs every 10 minutes. Links events across different systems that share a root cause.

**Method:**
1. Get all events from last 2 hours
2. Embed event summaries, cluster by cosine similarity > 0.7
3. Clusters spanning 2+ sources → Flash identifies root cause
4. Search memory for similar past correlations
5. Output: CRITICAL event with root cause analysis and suggested action

### 3b. Adaptive Baselines

Learn what's "normal" per (source, event_type, day_of_week, hour).

**Method:**
- Weekly SQL aggregation over 4 weeks of historical event data
- Store as `{mean, stddev}` per (source, event_type, weekday, hour)
- Anomaly = count > mean + 2*stddev (minimum threshold of 2)
- Replaces hard-coded "3 events = spike" with context-aware thresholds
- Cost: pure SQL, $0

### 3c. Intelligence Reports

**Enhanced morning brief** (6am daily, Flash):
- Overnight summary (events, errors, drafts)
- Active patterns and correlations
- Pending proposals with recommendations
- Unresolved issues from yesterday
- Agent self-assessment (approval rate trend)

**Weekly intelligence digest** (Friday 6pm, Pro):
- Week-over-week metrics comparison
- Pattern trends (improving/worsening)
- Agent performance assessment
- Cost breakdown by model tier
- Proposed improvements for next week

---

## 4. Proposals System (`proposals.py`)

Universal approval workflow. All learning, tools, and behavior changes flow through here.

### Proposal Types

| Type | Created by | On approval |
|------|-----------|-------------|
| `learned_rule` | Feedback Intel | Store in knowledge as `approved_rule` with embedding |
| `strong_rule` | Feedback Intel (aggregated) | Same, higher confidence, supersedes individual rules |
| `tool_creation` | Solution Factory | Script stored in solutions, registered as dynamic tool |
| `automation` | Solution Factory | Scheduled task activated |
| `mcp_server` | MCP Discovery | Config added, server connected |
| `guardrail_override` | Guardrails | One-time: event re-published to queue |
| `threshold_adjustment` | Analytics Engine | Baseline config updated |
| `playbook_suggestion` | Analytics Engine | Suggested ops_playbook.md edit for manual review |

### Approval channels

1. **Dashboard** — Proposals section with list, detail, approve/edit/reject buttons
2. **Google Chat** — Notification card with action buttons
3. **Chat command** — "override {event_id}" for guardrail overrides
4. **Auto-expiry** — 7 days (configurable)

### API endpoints

```
GET  /admin/proposals?status=pending&type=learned_rule&limit=20
GET  /admin/proposals/{id}
POST /admin/proposals/{id}/approve    { "notes": "...", "edited_description": "..." }
POST /admin/proposals/{id}/reject     { "reason": "..." }
GET  /admin/proposals/stats           # counts by type and status
```

---

## 5. Solution Factory (`intelligence/solutions/`)

Enterprise-level self-tooling. The agent identifies problems and builds solutions.

### Script Runner (`script_runner.py`)

Sandboxed Python execution for agent-created scripts.

**Sandbox rules:**
- Allowed imports: requests, httpx, json, csv, re, datetime, urllib.parse, math, statistics, collections, itertools, textwrap, string, html
- Blocked: os, sys, subprocess, shutil, pathlib, socket, asyncio, importlib, ctypes, pickle
- Max execution: 60 seconds
- Max memory: 128MB
- Max output: 50,000 chars
- Restricted builtins: no open, eval, compile
- Pre-injected helpers: `http_get(url)`, `http_post(url, data)`, `db_query(sql, params)` (read-only), `send_chat(space, message)`, `send_email(to, subject, body)`

**What the agent can build:**
- Data fetchers (check carrier API, scrape status pages)
- Report generators (aggregate data, format as markdown)
- Integration bridges (transform data between systems)
- Monitoring checks (query DB, check conditions, alert)

### MCP Discovery (`mcp_discovery.py`)

Find and propose MCP server connections to extend capabilities.

**Flow:**
1. Agent identifies capability gap (e.g., no Shopify tool)
2. Searches registries: Smithery.ai API, GitHub search (`topic:mcp-server`), curated list
3. Returns top 3 matches with name, description, auth requirements
4. Creates `mcp_server` proposal
5. On approval: updates `mcp_servers.json`, restarts MCP client manager
6. Operator provides any required API keys

### Automation Builder (`automation.py`)

Creates scheduled/triggered tasks that run inside the existing worker.

**Automation types:**
| Type | Example | Trigger |
|------|---------|---------|
| Scheduled check | "Check carrier API every Monday 7am" | Cron expression |
| Event trigger | "When ticket mentions 'refund', auto-check order" | Event keyword/source match |
| Monitor | "Alert if 5+ complaints about same product in 24h" | Pattern detector rule |
| Integration | "Sync Freshdesk status to StarInfinity" | Event-driven |

### Factory Orchestrator (`factory.py`)

Decides when to propose solutions.

**Triggers:**
1. Recurring pattern detected (analytics): same incident 3+ times in a week
2. Capability gap (reasoning): model asked for a tool that doesn't exist
3. Repeated manual work (action log): operator does same steps repeatedly
4. Direct request via Chat: "can you build something to check X?"

**Flow:** Trigger -> Flash analysis -> proposal with code/config -> Chat notification -> Dashboard review -> Approve/Reject -> If approved: activate

---

## 6. Guardrails Fix

**Current problem:** Rules 2 (financial) and 4 (legal) silently block events.

**Fix:** When any guardrail blocks an event:
1. Create `guardrail_override` proposal with event details and blocking reason
2. Post notification to Chat alerts space with explanation and override option
3. Event still blocked, but operator is informed and can approve override

**Chat override command:** Reply "override {event_id_prefix}" in Chat -> finds matching proposal -> approves -> re-publishes event (skipping the blocking rule).

---

## 7. Worker Loop Integration

Enhanced pipeline:

```
Step 0: Pause check (existing)
Step 1: Classify (existing)
Step 1b: Teachable rule / override command (existing + enhanced)
Step 1c: Scheduled summaries (enhanced with intelligence data)
Step 1.5: Context Engine enrichment (NEW)
Step 2: Plan (existing)
Step 3: Guardrails with notifications (enhanced)
Step 4: Reason with enriched context (enhanced)
Step 4b: Chat safety net (existing)
Step 4c: Dashboard conversation store (existing)
Step 5: Log action (existing)
Step 5.5: Post-action intelligence (NEW)
  - Track event in analytics (correlation)
  - Check for cross-system patterns
  - Trigger solution factory if recurring pattern
```

---

## Database Changes (migration 004)

```sql
CREATE TABLE proposals (
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

CREATE TABLE solutions (
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

CREATE TABLE automations (
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

CREATE TABLE baselines (
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

CREATE INDEX idx_proposals_status ON proposals(status);
CREATE INDEX idx_proposals_type ON proposals(type);
CREATE INDEX idx_solutions_status ON solutions(status);
CREATE INDEX idx_automations_active ON automations(active) WHERE active = true;
```

---

## Files Summary

### New files (10)

| File | Est. lines | Purpose |
|------|-----------|---------|
| `intelligence/__init__.py` | 5 | Package init |
| `intelligence/context_engine.py` | 150 | Pre-reasoning context retrieval |
| `intelligence/feedback_intel.py` | 200 | Qualitative edit analysis |
| `intelligence/analytics_engine.py` | 250 | Correlation, baselines, reports |
| `intelligence/proposals.py` | 200 | Universal approval workflow |
| `intelligence/solutions/__init__.py` | 5 | Package init |
| `intelligence/solutions/factory.py` | 200 | Solution orchestrator |
| `intelligence/solutions/script_runner.py` | 150 | Sandboxed Python execution |
| `intelligence/solutions/mcp_discovery.py` | 120 | MCP server discovery |
| `migrations/004_intelligence.sql` | 60 | DB schema changes |

### Modified files (8)

| File | Changes |
|------|---------|
| `worker/loop.py` | Steps 1.5, 5.5; enhanced reports; override command handling |
| `reasoning/engine.py` | Accept EnrichedContext, inject into prompt |
| `guardrails/engine.py` | Notification + proposal on block |
| `worker/pollers/scheduler.py` | Wire analytics, feedback aggregation, baselines, automation runner |
| `webhook/routes/admin.py` | Proposals CRUD, solutions list, automation management |
| `tools/registry.py` | Register solution factory meta-tools |
| `common/models.py` | New event types if needed |
| Dashboard (multiple files) | Proposals section, solution viewer |

### Total: ~1,400 lines new Python + ~300 lines frontend + migration

---

## Implementation Order

1. Migration 004 (DB tables)
2. Proposals system (foundation for everything else)
3. Context Engine + engine.py integration
4. Guardrails fix (notifications + override)
5. Feedback Intelligence
6. Analytics Engine (correlation, baselines)
7. Solution Factory (script runner, MCP discovery, automations)
8. Enhanced intelligence reports
9. Dashboard: proposals section
10. Dashboard: solutions viewer
11. Deploy + verify

## Cost Impact

| Component | Per-event cost | Frequency |
|-----------|---------------|-----------|
| Context Engine (DB queries) | $0 | Every event |
| Context Engine (Flash summary) | $0.0005 | ~10% of events |
| Feedback Intel (edit analysis) | $0.0005 | Per edit (few/day) |
| Correlation (Flash analysis) | $0.002 | Every 10 min |
| Morning brief (Flash) | $0.002 | Daily |
| Weekly digest (Pro) | $0.01 | Weekly |
| Baseline updates (SQL only) | $0 | Weekly |

**Estimated additional cost: ~$0.30-0.50/day** at current event volumes.
