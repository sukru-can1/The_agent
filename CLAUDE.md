# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose & Goal

GLAMIRA Ops Agent ("The Agent1") — an autonomous AI operations coordinator for GLAMIRA (jewelry e-commerce). It monitors emails, Freshdesk support tickets, StarInfinity project tasks, customer feedback surveys, Trustpilot reviews, and Google Chat 24/7. It classifies events, reasons with tools, drafts email replies (requiring human approval), posts to Chat, adds ticket notes, creates tasks, and learns from operator edits. The goal is to be an always-on ops assistant that handles routine work and escalates what matters.

**Primary user**: Sukru Can (sukru.can@glamira-group.com), GLAMIRA tech team lead.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12, uv package manager |
| Web framework | FastAPI 0.115+ (uvicorn) |
| Database | PostgreSQL 16 + pgvector 0.8.1 |
| DB driver | asyncpg 0.30+ |
| Queue/cache | Redis 5.0+ (hiredis) |
| AI models | Google Gemini (2.0-flash, 2.5-flash, 2.5-pro, 3-pro) |
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
- Consumer: dequeues events from Redis, processes through AI pipeline
- Pollers: background jobs that poll Gmail (5min), Freshdesk (2min), StarInfinity, Feedbacks, GChat (user mode)
- Scheduler: cron-like tasks — pattern detection (10min), feedback analysis (30min), morning brief (6am), daily summary (6pm)

Both use `entrypoint.sh` which runs migrations on startup and starts based on `SERVICE_MODE` env var.

### Event Processing Pipeline

```
Event source → Redis sorted set (scored by priority*1e12 + timestamp)
  → Worker consumer (ZPOPMIN + distributed lock)
    → Step 1: Classify (Gemini Flash → category, urgency, complexity, VIP, financial, language)
    → Step 1b: Teachable rules → store in knowledge, ack via Chat
    → Step 1c: Scheduled summaries → aggregate stats, post to Chat
    → Step 2: Plan (Gemini Flash/Pro for moderate/complex)
    → Step 3: Guardrails (business rules + rate limits)
    → Step 4: Reason + tools (Gemini Pro/3-Pro, multi-turn function calling, up to 10 turns)
    → Step 4b: Safety-net Chat reply if tools didn't post
    → Step 4c: Store conversation for dashboard events
    → Step 5: Log action (enriched details: event_summary, tools_called, agent_response)
    → Update event status to completed
```

### Model Routing (4-tier, `reasoning/router.py`)

| Tier | Model | When |
|------|-------|------|
| Flash | `gemini-2.0-flash` | Auto-responses, trivial Q&A |
| Fast | `gemini-2.5-flash` | Classification, planning, simple events |
| Default | `gemini-2.5-pro` | Moderate complexity, chat with tools |
| Pro | `gemini-3-pro` | Complex, VIP, financial, cross-system |

Selection: VIP/financial → always Pro. Chat needing response → Default (or Pro if complex). Otherwise by complexity.

### Queue System (`queue/`)

- **Redis sorted set** (`agent1:queue:events`): score = `priority.value * 1e12 + timestamp_ms`
- **Event hash** (`agent1:event:{uuid}`): JSON payload, 24h TTL
- **Distributed lock** (`agent1:lock:{resource}`): SET NX EX 30
- **Dedup** (`agent1:dedup:{source}:{id}`): prevents duplicate processing, configurable TTL
- **DLQ**: after `queue_max_retries` (default 3), moves to `dead_letter_events` table + alerts Chat

### Guardrails (`guardrails/`)

Five hardcoded business rules in `rules.py`:
1. Restricted contacts → block entirely
2. Financial topics → require approval
3. VIP contacts → escalate, require approval
4. Legal keywords → require approval
5. High-value orders (>5000 EUR) → require approval

Rate limits in `rate_limits.py`: per-source (gmail 100/hr, freshdesk 200/hr, gchat 300/hr), global 500/hr, per-tool limits.

## Database Schema

All in `migrations/001_initial_schema.sql` + `002_add_vector_columns.sql` + `003_dynamic_tools.sql`.

### events
`id UUID PK`, `source VARCHAR`, `event_type VARCHAR`, `priority INT`, `payload JSONB`, `idempotency_key VARCHAR (UNIQUE)`, `status VARCHAR`, `retry_count INT`, `error TEXT`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`, `processed_at TIMESTAMPTZ`

### dead_letter_events
`id UUID PK`, `original_event_id UUID`, `source`, `event_type`, `priority`, `payload JSONB`, `error_history JSONB`, `retry_count`, `created_at`, `resolved_at`, `resolved_by`

### actions_log
`id SERIAL PK`, `timestamp TIMESTAMPTZ`, `system VARCHAR`, `action_type VARCHAR`, `details JSONB`, `outcome VARCHAR`, `model_used VARCHAR`, `input_tokens INT`, `output_tokens INT`, `latency_ms INT`, `event_id VARCHAR`, `embedding vector(1024)`

### incidents
`id SERIAL PK`, `timestamp TIMESTAMPTZ`, `category VARCHAR`, `description TEXT`, `market VARCHAR`, `systems_involved TEXT[]`, `resolution TEXT`, `resolution_time_minutes INT`, `resolved_at`, `tags TEXT[]`, `metadata JSONB`, `embedding vector(1024)` — HNSW index on embedding

### knowledge
`id SERIAL PK`, `created_at`, `updated_at`, `category VARCHAR`, `content TEXT`, `source VARCHAR`, `confidence FLOAT`, `last_validated`, `active BOOLEAN`, `supersedes_id INT FK`, `embedding vector(1024)` — HNSW index on embedding

### conversations
`id SERIAL PK`, `timestamp TIMESTAMPTZ`, `platform VARCHAR`, `user_id VARCHAR`, `user_name VARCHAR`, `space_id VARCHAR`, `thread_id VARCHAR`, `message_in TEXT`, `message_out TEXT`, `context JSONB`

### email_drafts
`id SERIAL PK`, `created_at`, `gmail_message_id`, `gmail_thread_id`, `from_address`, `to_address`, `subject`, `original_body`, `draft_body`, `edited_body`, `status VARCHAR`, `classification VARCHAR`, `context_used JSONB`, `approved_at`, `sent_at`

### draft_feedback
`id SERIAL PK`, `draft_id INT FK→email_drafts`, `sender_domain`, `category`, `edit_distance INT`, `edit_ratio FLOAT`, `original_length INT`, `edited_length INT`, `created_at`

### agent_metrics
`id SERIAL PK`, `date DATE`, `metric_name VARCHAR`, `metric_value FLOAT`, `metadata JSONB` — UNIQUE(date, metric_name)

### config
`key VARCHAR PK`, `value JSONB`, `updated_at`, `description TEXT`

### dynamic_tools
`id UUID PK`, `name VARCHAR UNIQUE`, `description TEXT`, `input_schema JSONB`, `code TEXT`, `created_by VARCHAR`, `active BOOLEAN`, `created_at`

## Pydantic Domain Models (`common/models.py`)

- **Priority** (IntEnum): CRITICAL=1, HIGH=3, MEDIUM=5, LOW=7, BACKGROUND=9
- **EventStatus** (StrEnum): PENDING, PROCESSING, COMPLETED, FAILED, DEAD_LETTER
- **EventSource** (StrEnum): GMAIL, GCHAT, FRESHDESK, STARINFINITY, FEEDBACKS, SCHEDULER, ADMIN, DASHBOARD
- **EmailClassification** (StrEnum): URGENT, NEEDS_RESPONSE, FYI, SPAM
- **Complexity** (StrEnum): SIMPLE, MODERATE, COMPLEX
- **Event**: id, source, event_type, priority, payload, idempotency_key, created_at, status, retry_count, error
- **ClassificationResult**: category, urgency, complexity, involves_vip, involves_financial, needs_response, confidence, detected_language, is_teachable_rule
- **EmailDraft**: id, gmail_message_id, gmail_thread_id, from/to_address, subject, original/draft/edited_body, status, classification, context_used
- **ActionLog**: system, action_type, details, outcome, model_used, input/output_tokens, latency_ms
- **MemorySearchResult**: id, category, content, source, similarity, table

## Tool System

### BaseTool (`tools/base.py`)
Abstract class: `name` (property), `description` (property), `input_schema` (property), `execute(**kwargs)` (async). All tools extend this.

### Tool Registry (`tools/registry.py`)
- `register_tool(tool)` — add to global `_registry` dict
- `get_tool(name)` — lookup by name
- `get_tool_definitions()` — all tools as JSON Schema dicts for Gemini
- `execute_tool(name, params)` — dispatch to tool
- `register_all_tools()` — registers all 25+ native tools
- `register_mcp_tools()` — connect MCP servers, register adapters
- `register_dynamic_tools()` — load from DB

### Native Tools (27 tools)

**Gmail** (5 tools, `tools/gmail.py`):
- `gmail_get_new_emails` — fetch unread (max_results, label, query)
- `gmail_get_email` — full email with body/attachments (message_id)
- `gmail_draft_reply` — store draft in DB, post approval card to Chat (message_id, draft_body, classification)
- `gmail_send_approved` — send approved draft via Gmail API (draft_id)
- `gmail_label_email` — modify labels (message_id, add_labels, remove_labels)

**Google Chat — Agent mode** (3 tools, `tools/google_chat.py`):
- `gchat_post_message` — post to space (space, message, thread_key, cards)
- `gchat_reply_as_agent` — reply as bot (space, message, thread_key)
- `gchat_get_messages` — list recent messages (space, max_results)
- Helper: `_resolve_space()` maps friendly names ('alerts', 'log', 'summary', 'dm') to full space IDs

**Google Chat — User mode** (2 tools, `tools/google_chat_user.py`):
- `gchat_reply_as_user` — send as Sukru via OAuth (space_id, text, thread_id)
- `gchat_list_my_spaces` — list all spaces user is in

**Google Drive** (2 tools, `tools/google_drive.py`):
- `drive_search` — search files (query, file_type, max_results)
- `drive_read_document` — read content: Docs→text, Sheets→CSV, PDFs→extracted text (file_id, max_length)

**Freshdesk** (4 tools, `tools/freshdesk.py`):
- `freshdesk_get_tickets` — filtered list (status, priority, updated_since, per_page)
- `freshdesk_get_ticket` — full ticket + conversations (ticket_id)
- `freshdesk_add_note` — internal note (ticket_id, body, private)
- `freshdesk_update_ticket` — update properties (ticket_id, priority, status, tags)

**StarInfinity** (4 tools, `tools/starinfinity.py`):
- `starinfinity_list_boards` — list all boards
- `starinfinity_get_tasks` — items from board (board_id, limit, after cursor)
- `starinfinity_create_task` — create item (board_id, folder_id, values)
- `starinfinity_update_task` — update item (board_id, item_id, values)

**Feedbacks** (4 tools, `tools/feedbacks.py`, reads from separate feedbacks DB):
- `feedbacks_get_customer_responses` — survey responses by email
- `feedbacks_get_recent_complaints` — negative sentiment (country_code, days, limit)
- `feedbacks_get_csat_summary` — aggregate CSAT by country (days, country_code)
- `feedbacks_get_trustpilot_reviews` — low-star reviews (max_stars, status, defendable_only, limit)

**Memory** (3 tools, `tools/memory.py`):
- `memory_search` — semantic search via pgvector (query, category: incidents/knowledge/actions/all, limit, threshold=0.6)
- `memory_store_incident` — store with embedding (category, description, resolution, market, systems_involved, tags)
- `memory_store_knowledge` — store with embedding (category, content, source)

**Chat Cards** (`tools/chat_cards.py`):
- `build_draft_approval_card()` — Chat Card V2 with Approve/Edit/Reject buttons
- `build_alert_card()` — alert notification card with Acknowledge button

### MCP Integration (`tools/mcp/`)

- **config.py**: `MCPServerConfig` dataclass, `load_mcp_config(path)` loads `mcp_servers.json`, resolves `${ENV_VAR}` in values
- **client_manager.py**: `MCPClientManager` — connects to servers (stdio/SSE), caches sessions, `call_tool(server, tool, args)`, `get_all_tools()`, `stop()`
- **adapter.py**: `MCPToolAdapter(BaseTool)` — wraps MCP tool as native tool, namespaced `{server}__{tool}`
- **builder.py**: `DynamicTool(BaseTool)` — executes user-created code in restricted scope. `DynamicToolBuilder` — `create_dynamic_tool` meta-tool (validates code: blocks os/subprocess/eval/exec/open, 30s timeout). `ListDynamicToolsTool` — `list_dynamic_tools` meta-tool

Configured servers in `mcp_servers.json` (all disabled by default): google_analytics, railway, filesystem, fetch.

### Reasoning Engine (`reasoning/engine.py`)

`reason_and_act(event, classification, plan)`:
1. Build context message: event info, payload JSON, classification, language instruction, plan, learned knowledge rules
2. Convert all tool definitions to Gemini FunctionDeclarations
3. Multi-turn loop (max 10 turns):
   - Call `client.aio.models.generate_content()` with tools
   - If no function calls → extract final text, return result
   - If function calls → execute each tool, build function response parts, feed back
4. Returns: `{model_used, input_tokens, output_tokens, result, turns, tools_called}`

System prompt loaded from `reasoning/prompts/ops_playbook.md`.

## Memory System (`memory/`)

- **manager.py**: `search_memory(query, category, limit, threshold)` — embeds query via Voyage, cosine search on incidents + knowledge via pgvector (1 - distance > threshold). `store_incident()` / `store_knowledge()` — stores with auto-generated embedding.
- **queries.py**: `get_recent_incidents()`, `get_active_knowledge()`, `get_sender_history(email)` — plain SQL queries for non-vector lookups.

## Feedback Learning (`feedback/`)

- **tracker.py**: `track_edit(draft_id, original, edited, sender_domain, category)` — computes Levenshtein distance/ratio, stores in `draft_feedback`
- **analyzer.py**: `analyze_edit_patterns(min_edits)` — finds consistent edit patterns (e.g. "always edited for domain X"), `get_edit_examples(sender_domain)`

The scheduler runs `_run_feedback_analysis()` every 30min: if patterns found, stores them as knowledge entries so future drafts improve.

## Worker Pollers (`worker/pollers/`)

- **gmail_poller.py**: `poll_gmail()` — fetches unread INBOX emails (max 20), dedups by message ID, publishes `new_email` events
- **freshdesk_poller.py**: `poll_freshdesk()` — tickets updated in last 10min, dedups, publishes `ticket_updated` events
- **feedbacks_poller.py**: `poll_feedbacks()` — new complaints (taskStatus='new', last 15min), new low-star Trustpilot reviews, spike detection (3+ negative reviews/hour → CRITICAL alert)
- **starinfinity_poller.py**: `poll_starinfinity()` — checks all boards for overdue items (due_date < now), publishes `task_overdue` events
- **gchat_poller.py**: `poll_gchat()` — polls configured spaces in user mode (OAuth), skips own/bot messages, publishes `chat_user_message` events
- **scheduler.py**: `run_scheduler()` — orchestrates all pollers on intervals, runs pattern detection + feedback analysis + morning brief (6 UTC) + daily summary (18 UTC)

### Pattern Detection (`worker/pattern_detector.py`)

- `detect_patterns()` — runs all checks
- `_detect_ticket_spikes()` — 3+ events of same type in 1 hour (2h cooldown between alerts)
- `_detect_csat_trends()` — 1.5x increase in negative sentiment vs previous 24h (needs 3+ complaints)
- `_detect_error_spikes()` — >30% error rate in last hour with 5+ events (1h cooldown)

## Webhook Routes (`webhook/routes/`)

### health.py
- `GET /health` → `{status: "ok", agent: name}`
- `GET /status` → checks DB + Redis connectivity

### gchat.py
- `POST /webhooks/gchat` — handles MESSAGE, ADDED_TO_SPACE, button actions (approve/reject/edit draft). `_normalize_body()` handles both legacy and Workspace Add-on formats. `_chat_response()` wraps in correct format.

### freshdesk.py
- `POST /webhooks/freshdesk` — receives ticket events, validates shared secret, publishes events

### gmail_push.py
- `POST /webhooks/gmail` — receives Gmail push notifications, triggers email polling

### oauth_callback.py
- `GET /admin/oauth/start` — initiates OAuth flow
- `GET /admin/oauth/callback` — handles callback, stores tokens

### admin.py (30+ endpoints)

**Status & Queue:**
- `GET /admin/status` → queue_depth, pending_drafts, dlq_count, is_paused, last_action
- `POST /admin/queue/pause` → set Redis pause flag
- `POST /admin/queue/resume` → clear pause flag

**Drafts:**
- `GET /admin/drafts?status=&limit=` → list email drafts
- `POST /admin/drafts/{id}/approve` → approve (optional edited_body triggers feedback learning)
- `POST /admin/drafts/{id}/reject` → reject

**Events:**
- `GET /admin/events?status=&limit=` → list events
- `GET /admin/events/{event_id}` → single event by UUID (for polling completion)

**Actions:**
- `GET /admin/actions?limit=&event_id=` → list actions (optional event_id filter)
- `GET /admin/actions/{action_id}` → single action with joined event data

**DLQ:**
- `GET /admin/dlq` → unresolved entries
- `POST /admin/dlq/{id}/retry` → re-publish
- `POST /admin/dlq/{id}/resolve` → mark resolved

**Knowledge:**
- `GET /admin/knowledge?limit=` → active knowledge entries
- `POST /admin/knowledge` → store operator instruction

**Config:**
- `GET /admin/config` → all runtime config
- `POST /admin/config/{key}` → upsert config value

**Chat:**
- `GET /admin/chat-history?limit=` → recent dashboard conversations
- `POST /admin/inject-event` → inject event (source=dashboard for chat, source=gchat for test)

**Integrations:**
- `GET /admin/integrations` → list configured integrations + active status

**Analytics:**
- `GET /admin/analytics/summary` → events/drafts/errors/tokens today + top event types
- `GET /admin/analytics/daily-costs?days=` → model cost breakdown per day
- `GET /admin/analytics/approval-rate?days=` → draft approval/rejection/edit rates
- `GET /admin/analytics/response-time?days=` → avg/max/p95 latency by system

## Google Auth (`google_auth/auth.py`)

- `_get_oauth_credentials()` → Credentials from refresh token (Gmail, Drive, Chat user scopes)
- `_get_service_account_credentials()` → service account creds from JSON (Chat bot scope)
- `get_gmail_service()` → Gmail API v1 service object (OAuth, cached)
- `get_drive_service()` → Drive API v3 service (OAuth, cached)
- `get_chat_service()` → Chat API v1 service (service account, bot)
- `get_chat_user_service()` → Chat API v1 service (OAuth, acts as Sukru)

## Dashboard (Next.js 15 + React 19 + TailwindCSS 4)

### Auth
- `auth.ts` — NextAuth config: Google OAuth provider, email whitelist (sukru.can@glamira-group.com)
- `middleware.ts` — protects all routes except `/login`, `/api/auth/*`, `/_next/*`
- `app/login/page.tsx` — Google sign-in button
- `app/api/auth/[...nextauth]/route.ts` — NextAuth route handler

### Layout
- `app/layout.tsx` — root: SessionProvider, Geist fonts, dark mode, metadata
- `app/(dashboard)/layout.tsx` — sidebar + topbar shell, fetches agent status (30s refresh), manages routing

### Pages
- **Command Center** (`page.tsx`) — metric tiles (queue, drafts, today, cost), pause/resume button, collapsible chat widget (with file upload + clipboard paste), draft approval cards, alert events, DLQ entries, activity feed sidebar
- **Activity** (`activity/page.tsx`) — merged timeline of events + actions, filter by type, expandable action rows (event summary, tools used, agent response, model/tokens/latency, external links)
- **Analytics** (`analytics/page.tsx`) — 7-day cost breakdown, approval rate, response time (p95), token usage, top event types
- **Knowledge** (`knowledge/page.tsx`) — browse/filter rules by category, teach new instructions
- **Settings** (`settings/page.tsx`) — integration status, runtime config, test event injection

### Components
- `DecisionCard` — draft/alert/DLQ card with priority indicator, expandable body, action buttons, comment input
- `MetricTile` — icon + label + value display
- `IntegrationCard` — integration status (icon, active/inactive)
- `Sidebar` — fixed 56px nav (Command Center, Activity, Knowledge, Analytics, Settings), pause button, user profile
- `Topbar` — page title, connection dot, status pills (Queue/Drafts/Errors), category filter, refresh
- `CategoryBadge` — color-coded category chip
- `CommentInput` — text input that stores operator instructions as knowledge
- `EditModal` — modal for editing email draft body before approval
- `EmptyState` — encouraging message when no pending work

### Types (`lib/types.ts`)
- Interfaces: `AgentStatus`, `Draft`, `AgentEvent`, `DlqEntry`, `AgentAction`, `Integration`, `KnowledgeEntry`, `ActionSummary`
- Type: `Category = "cs" | "finance" | "operations" | "website" | "marketing" | "system"`
- Constants: `CATEGORY_CONFIG` — label + color + bg per category
- Functions: `getCategory(source, eventType)`, `extractDetail(source, payload)`, `extractActionSummary(action)`, `timeAgo(ts)`

### API Client (`lib/api.ts`)
All functions for dashboard API calls: `fetchStatus`, `fetchDrafts`, `fetchEvents`, `fetchDlq`, `fetchActions`, `fetchKnowledge`, `fetchIntegrations`, `fetchConfig`, `updateConfig`, `storeKnowledge`, `approveDraft`, `rejectDraft`, `retryDlqEntry`, `resolveDlqEntry`, `pauseQueue`, `resumeQueue`, `injectEvent`

### API Proxy (`next.config.ts`)
- `/api/admin/:path*` → `${AGENT_API_URL}/admin/:path*`
- `/api/health` → `${AGENT_API_URL}/health`

### Design System (`globals.css`)
Dark theme: bg `#0a0a0f`, surface `#12121a`, text `#e4e4ef`, muted `#8585a0`, dim `#6e6e88`, accent `#818cf8` (indigo). Category colors: CS=cyan, Finance=amber, Ops=indigo, Website=emerald, Marketing=purple, System=slate.

## Configuration (`common/settings.py`)

All fields with defaults — loaded from env vars:

| Field | Default | Purpose |
|-------|---------|---------|
| `gemini_api_key` | "" | Gemini API key |
| `gemini_model_default` | "gemini-2.5-pro" | Moderate tasks |
| `gemini_model_fast` | "gemini-2.5-flash" | Classifier/planner |
| `gemini_model_pro` | "gemini-3-pro" | Complex/VIP/financial |
| `gemini_model_flash` | "gemini-2.0-flash" | Auto-response |
| `voyage_api_key` | "" | Embedding API key |
| `voyage_model` | "voyage-3" | Embedding model |
| `embedding_dim` | 1024 | Vector dimension |
| `database_url` | "" | PostgreSQL DSN |
| `db_pool_min` / `db_pool_max` | 2 / 10 | Connection pool |
| `feedbacks_database_url` | "" | Feedbacks DB (read-only) |
| `redis_url` | "" | Redis DSN |
| `google_service_account_json` | "" | Chat bot service account |
| `google_client_id` / `secret` / `refresh_token` | "" | OAuth credentials |
| `gmail_user_email` | "sukru.can@glamira-group.com" | Gmail to monitor |
| `gchat_space_alerts` / `log` / `summary` | "" | Chat space IDs |
| `gchat_dm_sukru` | "" | DM space for direct messages |
| `gchat_poll_spaces` | [] | Spaces to poll in user mode |
| `gchat_user_email` | "" | Filter own messages |
| `google_project_number` | "" | JWT audience verification |
| `freshdesk_domain` | "glmr.freshdesk.com" | Freshdesk tenant |
| `freshdesk_api_key` | "" | Freshdesk auth |
| `freshdesk_webhook_secret` | "" | Webhook validation |
| `starinfinity_base_url` / `api_key` | "" | StarInfinity API |
| `langfuse_public_key` / `secret_key` / `host` | "" | Observability |
| `mcp_config_path` | "mcp_servers.json" | MCP server config |
| `dynamic_tools_enabled` | true | Allow agent to create tools |
| `agent_name` | "The Agent1" | Display name |
| `log_level` | "INFO" | Logging level |
| `environment` | "development" | Dev/staging/production |
| `webhook_host` / `port` | "0.0.0.0" / 8080 | Server bind |
| `heartbeat_interval_seconds` | 300 | Poller interval |
| `queue_max_retries` | 3 | Before DLQ |
| `dedup_ttl_seconds` | 3600 | Dedup key expiry |
| `lock_ttl_seconds` | 30 | Distributed lock TTL |
| `rate_limit_emails_per_hour` | 10 | Gmail send limit |
| `rate_limit_chat_messages_per_minute` | 30 | Chat post limit |
| `restricted_contacts` | [] | Blocked email addresses |

## Deployment

| Service | Platform | ID | URL |
|---------|----------|----|-----|
| Webhook | Railway | f010e3b6 | https://webhook-production-50a3.up.railway.app |
| Worker | Railway | 72952308 | (internal) |
| pgvector-db-v2 | Railway | ab8d2171 | internal:5432/agent1 |
| Redis | Railway | a8fe9ab7 | (internal) |
| Dashboard | Vercel | — | https://dashboard-alpha-lovat-14.vercel.app |

### Docker

Two Dockerfiles, identical except CMD:
- `Dockerfile.webhook` → runs `entrypoint.sh` (default: webhook mode)
- `Dockerfile.worker` → runs `uv run python -m agent1.worker.main`

`entrypoint.sh`: runs migrations, then starts webhook or worker based on `SERVICE_MODE`.

## Python Conventions

- Python 3.12 — use `datetime.now(UTC)` not `datetime.utcnow()` (deprecated)
- `uv` uses `[dependency-groups]` for dev deps, not `[project.optional-dependencies]`
- Windows: no `loop.add_signal_handler` — guard with `sys.platform != "win32"`
- `pyproject.toml` wheel: `packages = ["src/agent1"]`
- DB columns: `active` (not `is_active`), `confidence` (not `version`) on knowledge table
- Ruff: target py312, line-length 100, select E/F/I/N/W/UP
- mypy: strict mode
- pytest: asyncio_mode=auto, testpaths=["tests"]

## Adding New Functionality

**New tool**: Subclass `BaseTool` in `tools/`, implement `name`, `description`, `input_schema`, `execute()`. Add to `register_all_tools()` in `tools/registry.py`.

**New event source**: Add to `EventSource` enum in `common/models.py`. Add webhook route in `webhook/routes/`. Register in `webhook/app.py`.

**New poller**: Create `poll_X()` in `worker/pollers/`. Wire into `scheduler.py`.

**New admin endpoint**: Add to `webhook/routes/admin.py`. Dashboard proxy handles automatically via wildcard rewrite.

**New dashboard page**: Create in `dashboard/app/(dashboard)/your-page/page.tsx`. Add nav entry in `components/shell/Sidebar.tsx`.
