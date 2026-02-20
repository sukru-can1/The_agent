# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

GLAMIRA Ops Agent ("The Agent1") — autonomous AI operations coordinator for GLAMIRA (jewelry e-commerce). Monitors Gmail, Freshdesk tickets, StarInfinity tasks, customer feedback, Trustpilot reviews, and Google Chat DMs 24/7. Classifies events, reasons with tools, drafts email replies (human approval required), posts to Chat, adds ticket notes, creates tasks, and learns from operator edits.

**Primary user**: Sukru Can (sukru.can@glamira-group.com), GLAMIRA tech team lead.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12, uv package manager |
| Web framework | FastAPI 0.115+ (uvicorn) |
| Database | PostgreSQL 16 + pgvector 0.8.1 |
| DB driver | asyncpg 0.30+ |
| Queue/cache | Redis 5.0+ (hiredis) |
| LLM | Switchable: Gemini or OpenRouter (runtime toggle via Redis) |
| Embeddings | Voyage AI (voyage-3, 1024-dim vectors) |
| Auth | Google OAuth 2.0, Google JWT, service accounts |
| Observability | LangFuse 2.0+, structlog JSON logging |
| MCP | mcp 1.7+ (Model Context Protocol for extensible tools) |
| Dashboard | Next.js 15, React 19, TailwindCSS 4, next-auth 5 |
| Deployment | Railway (backend + DB + Redis), Vercel (dashboard) |

## Commands

```bash
# Backend — install & run
uv sync                          # install deps (NOT pip/poetry)
uv run python migrations/migrate.py  # run DB migrations
PYTHONPATH=src uv run uvicorn agent1.webhook.app:create_app --factory --host 0.0.0.0 --port 8080 --reload  # webhook
PYTHONPATH=src uv run python -m agent1.worker.main  # worker (separate terminal)

# Backend — quality
uv run ruff check src/            # lint
uv run ruff check --fix src/      # lint + autofix
uv run ruff format src/           # format
uv run mypy src/agent1/ --strict  # type check
uv run pytest -v                  # tests (asyncio_mode=auto configured)

# Dashboard
cd dashboard && npm run dev       # dev server (Turbopack)
cd dashboard && npm run build     # production build
cd dashboard && npx tsc --noEmit  # type check
cd dashboard && npx vercel --prod # deploy to Vercel

# Railway deployment (Windows Git Bash)
MSYS_NO_PATHCONV=1 /c/Users/LENOVO/AppData/Roaming/npm/railway.cmd service webhook  # ALWAYS switch first
MSYS_NO_PATHCONV=1 /c/Users/LENOVO/AppData/Roaming/npm/railway.cmd up               # then deploy
# Repeat with `service worker` — deploying to wrong service breaks things
```

## Architecture

### Two-Process Design

**Webhook** (`src/agent1/webhook/`) — FastAPI on port 8080.
- Receives events: Google Chat webhooks, Freshdesk webhooks, Gmail push notifications
- Validates auth: Google JWT (Chat), shared secret (Freshdesk)
- Publishes events to Redis priority queue
- Serves admin API (30+ endpoints for dashboard)

**Worker** (`src/agent1/worker/`) — Asyncio event loop.
- Consumer: dequeues events from Redis, processes up to 5 concurrently through AI pipeline
- Pollers: background jobs — Gmail (5min), Freshdesk (2min), GChat DMs (5min), StarInfinity, Feedbacks
- Scheduler: cron-like tasks — pattern detection, feedback analysis, morning brief (06:00 UTC), daily summary (18:00 UTC)

Both use `entrypoint.sh` which runs migrations on startup and starts based on `SERVICE_MODE` env var.

### Event Processing Pipeline

```
Event source → Redis sorted set (scored by priority*1e12 + timestamp)
  → Worker consumer (ZPOPMIN + distributed lock, 5 concurrent workers)
    → Step 1: Classify (Flash model → category, urgency, complexity, VIP, financial, language)
    → Step 1b: Teachable rules → store in knowledge, ack via Chat
    → Step 1c: Scheduled summaries → aggregate stats, post to Chat
    → Step 2: Plan (for moderate/complex events)
    → Step 3: Guardrails (business rules + rate limits)
    → Step 4: Reason + tools (multi-turn function calling, up to 10 turns)
    → Step 5: Log action → Update event status → Post-action intelligence
```

### LLM Provider Abstraction (`reasoning/providers/`)

Swappable between Gemini and OpenRouter at runtime via Redis key (`agent1:llm_provider`). Both webhook and worker see the same override.

- `_base.py`: `LLMProvider` ABC with `generate()`, `LLMResponse`, `ToolCall`
- `_gemini.py`: Google Gemini native client
- `_openrouter.py`: OpenRouter API (supports any model)
- `_factory.py`: Singleton with Redis-backed override, `get_provider()`, `set_provider_override()`

### Model Routing (4-tier, `reasoning/router.py`)

| Tier | Gemini | OpenRouter | When |
|------|--------|-----------|------|
| Flash | gemini-2.0-flash | google/gemini-2.5-flash | Auto-responses, trivial |
| Fast | gemini-2.5-flash | google/gemini-2.5-flash | Classification, planning |
| Default | gemini-2.5-pro | moonshotai/kimi-k2.5 | Moderate, chat with tools |
| Pro | gemini-3-pro | moonshotai/kimi-k2-thinking | Complex, VIP, cross-system |

Selection logic: VIP/financial → Pro. Chat needing response → Default (Pro if complex). Otherwise by complexity.

### Queue System (`queue/`)

- **Redis sorted set** (`agent1:queue:events`): score = `priority.value * 1e12 + timestamp_ms`
- **Event hash** (`agent1:event:{uuid}`): JSON payload, 24h TTL
- **Distributed lock** (`agent1:lock:{resource}`): SET NX EX 30
- **Dedup** (`agent1:dedup:{source}:{id}`): prevents duplicate processing, configurable TTL
- **DLQ**: after `queue_max_retries` (default 3), moves to `dead_letter_events` table + alerts Chat
- **Consumer**: 5 concurrent workers via `asyncio.wait(FIRST_COMPLETED)`

### Guardrails (`guardrails/rules.py`)

Five hardcoded business rules:
1. Restricted contacts → block entirely
2. Financial topics → **allowed** (process normally, flag for approval on outbound actions)
3. VIP contacts → allowed, escalated, require approval
4. Legal keywords → block entirely
5. High-value orders (>5000 EUR) → allowed with extra care

Rate limits in `rate_limits.py`: per-source (gmail 100/hr, freshdesk 200/hr, gchat 300/hr), global 500/hr, per-tool limits.

### GChat DM Monitoring (`worker/pollers/gchat_poller.py`)

When `GCHAT_POLL_ALL_DMS=true`:
- Auto-discovers all DM spaces via OAuth (cached 1 hour)
- Maintains "active" set (spaces where messages were seen) → polled every tick
- Rotates through "cold" spaces in batches of 20 per tick
- Only processes messages arriving AFTER worker starts (no historical backfill)
- **Must poll sequentially** — `httplib2` (used by Google API client) is NOT thread-safe

## Database

Schema across 4 migrations in `migrations/`:
- `001_initial_schema.sql`: events, dead_letter_events, actions_log, incidents, knowledge, conversations, email_drafts, draft_feedback, agent_metrics, config
- `002_add_vector_columns.sql`: pgvector `vector(1024)` columns + HNSW indexes on actions_log, incidents, knowledge
- `003_dynamic_tools.sql`: dynamic_tools table for agent-created tools
- `004_intelligence.sql`: proposals, solutions, automations, baselines tables

Key column names: `active` (not `is_active`), `confidence` (not `version`) on knowledge table.

## Tool System

### Adding a New Tool
Subclass `BaseTool` in `tools/`, implement `name`, `description`, `input_schema`, `execute()`. Register in `register_all_tools()` in `tools/registry.py`.

### Native Tools (27+)
- **Gmail** (5): get_new_emails, get_email, draft_reply, send_approved, label_email
- **Google Chat Agent** (3): post_message, reply_as_agent, get_messages — `_resolve_space()` maps friendly names ('alerts', 'log', 'summary', 'dm') to IDs
- **Google Chat User** (2): reply_as_user, list_my_spaces — acts as Sukru via OAuth
- **Google Drive** (2): search, read_document (Docs→text, Sheets→CSV, PDFs→extracted)
- **Freshdesk** (4): get_tickets, get_ticket, add_note, update_ticket
- **StarInfinity** (4): list_boards, get_tasks, create_task, update_task
- **Feedbacks** (4): get_customer_responses, get_recent_complaints, get_csat_summary, get_trustpilot_reviews
- **Memory** (3): search (pgvector cosine), store_incident, store_knowledge
- **Chat Cards**: build_draft_approval_card, build_alert_card (Card V2 with action buttons)

### MCP Integration (`tools/mcp/`)
- Config loaded from `mcp_servers.json`, resolves `${ENV_VAR}` in values
- Tools namespaced as `{server}__{tool}` via `MCPToolAdapter(BaseTool)`
- Dynamic tools: `create_dynamic_tool` + `list_dynamic_tools` meta-tools (code sandboxed: blocks os/subprocess/eval/exec)

## Dashboard

### Pages
- **Command Center** (`page.tsx`): metrics, chat panel, draft approvals, alerts, DLQ, activity feed
- **Activity** (`activity/`): merged event+action timeline, expandable details
- **Analytics** (`analytics/`): costs, approval rate, response time, token usage
- **Knowledge** (`knowledge/`): browse/teach rules
- **Proposals** (`proposals/`): intelligence proposals review
- **Settings** (`settings/`): integrations, runtime config, test injection

### Key Components
- `ChatPanel.tsx`: floating pill (bottom-left, 3D mouse-reactive animation) + expandable chat panel
- `DraftRefineModal.tsx`: AI-assisted draft refinement with instruction input
- `DecisionCard.tsx`: draft/alert/DLQ cards with action buttons

### API Proxy (`next.config.ts`)
- `/api/admin/:path*` → `${AGENT_API_URL}/admin/:path*`
- `/api/health` → `${AGENT_API_URL}/health`

### Design System
Dark theme: bg `#0a0a0f`, surface `#12121a`, accent `#818cf8` (indigo). Categories: CS=cyan, Finance=amber, Ops=indigo, Website=emerald, Marketing=purple, System=slate.

## Deployment

| Service | Platform | ID | URL |
|---------|----------|----|-----|
| Webhook | Railway | f010e3b6 | https://webhook-production-50a3.up.railway.app |
| Worker | Railway | 72952308 | (internal) |
| pgvector-db-v2 | Railway | ab8d2171 | internal:5432/agent1 |
| Redis | Railway | a8fe9ab7 | (internal) |
| Dashboard | Vercel | — | https://dashboard-alpha-lovat-14.vercel.app |

Docker: `Dockerfile.webhook` + `Dockerfile.worker`, both use `entrypoint.sh` (runs migrations, then starts based on `SERVICE_MODE`).

## Gotchas

- **Railway deploy**: ALWAYS `railway service <name>` before `railway up` — deploying to wrong service is destructive
- **MSYS_NO_PATHCONV=1**: Required for Unix paths on Windows Git Bash with Railway CLI
- **httplib2 not thread-safe**: Google API client services (`get_chat_user_service()` etc.) cannot be used from concurrent threads — serialize calls
- **`datetime.now(UTC)`** not `datetime.utcnow()` (deprecated in 3.12)
- **`uv` dev deps**: Use `[dependency-groups]` not `[project.optional-dependencies]`
- **Windows signals**: No `loop.add_signal_handler` — guard with `sys.platform != "win32"`
- **`file_cache is only supported with oauth2client<4.0.0`**: Harmless warning from Google API discovery, safe to ignore
- **Ruff config**: target py312, line-length 100, select E/F/I/N/W/UP
- **mypy**: strict mode
- **pytest**: asyncio_mode=auto

## Adding New Functionality

**New event source**: Add to `EventSource` enum in `common/models.py`. Add webhook route in `webhook/routes/`. Register in `webhook/app.py`.

**New poller**: Create `poll_X()` in `worker/pollers/`. Wire into `scheduler.py`.

**New admin endpoint**: Add to `webhook/routes/admin.py`. Dashboard proxy handles automatically via wildcard rewrite.

**New dashboard page**: Create in `dashboard/app/(dashboard)/your-page/page.tsx`. Add nav entry in `components/shell/Sidebar.tsx`.
