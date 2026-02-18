-- GLAMIRA Ops Agent — Initial Schema (core tables, no pgvector dependency)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Events (persistent queue backing)
-- ============================================================
CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50)  NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    priority        INTEGER      NOT NULL DEFAULT 5,
    payload         JSONB        NOT NULL DEFAULT '{}',
    idempotency_key VARCHAR(255) NOT NULL DEFAULT '',
    status          VARCHAR(50)  NOT NULL DEFAULT 'pending',
    retry_count     INTEGER      NOT NULL DEFAULT 0,
    error           TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_priority_created ON events(priority, created_at);
CREATE UNIQUE INDEX idx_events_idempotency ON events(idempotency_key) WHERE idempotency_key != '';

-- ============================================================
-- Dead-letter events
-- ============================================================
CREATE TABLE dead_letter_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    original_event_id UUID NOT NULL,
    source          VARCHAR(50)  NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    priority        INTEGER      NOT NULL,
    payload         JSONB        NOT NULL DEFAULT '{}',
    error_history   JSONB        NOT NULL DEFAULT '[]',
    retry_count     INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolved_by     VARCHAR(255)
);

CREATE INDEX idx_dlq_resolved ON dead_letter_events(resolved_at) WHERE resolved_at IS NULL;

-- ============================================================
-- Actions log (audit trail)
-- ============================================================
CREATE TABLE actions_log (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    system          VARCHAR(50)  NOT NULL,
    action_type     VARCHAR(100) NOT NULL,
    details         JSONB        NOT NULL DEFAULT '{}',
    outcome         VARCHAR(50)  DEFAULT 'success',
    model_used      VARCHAR(100) DEFAULT '',
    input_tokens    INTEGER      DEFAULT 0,
    output_tokens   INTEGER      DEFAULT 0,
    latency_ms      INTEGER      DEFAULT 0,
    event_id        UUID
);

CREATE INDEX idx_actions_timestamp ON actions_log(timestamp DESC);
CREATE INDEX idx_actions_system ON actions_log(system);

-- ============================================================
-- Incidents (past incidents — embedding column added in 002)
-- ============================================================
CREATE TABLE incidents (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    category        VARCHAR(100) NOT NULL,
    description     TEXT         NOT NULL,
    market          VARCHAR(10),
    systems_involved TEXT[]       DEFAULT '{}',
    resolution      TEXT,
    resolution_time_minutes INTEGER,
    resolved_at     TIMESTAMPTZ,
    tags            TEXT[]       DEFAULT '{}',
    metadata        JSONB        DEFAULT '{}'
);

CREATE INDEX idx_incidents_category ON incidents(category);
CREATE INDEX idx_incidents_market ON incidents(market);

-- ============================================================
-- Knowledge (learned rules — embedding column added in 002)
-- ============================================================
CREATE TABLE knowledge (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    category        VARCHAR(100) NOT NULL,
    content         TEXT         NOT NULL,
    source          VARCHAR(50)  DEFAULT 'configured',
    confidence      FLOAT        DEFAULT 1.0,
    last_validated  TIMESTAMPTZ,
    active          BOOLEAN      DEFAULT TRUE,
    supersedes_id   INTEGER      REFERENCES knowledge(id)
);

CREATE INDEX idx_knowledge_category ON knowledge(category);
CREATE INDEX idx_knowledge_active ON knowledge(active) WHERE active = TRUE;

-- ============================================================
-- Conversations (chat history)
-- ============================================================
CREATE TABLE conversations (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    platform        VARCHAR(50)  NOT NULL,
    user_id         VARCHAR(255),
    user_name       VARCHAR(255),
    space_id        VARCHAR(255),
    thread_id       VARCHAR(255),
    message_in      TEXT,
    message_out     TEXT,
    context         JSONB        DEFAULT '{}'
);

CREATE INDEX idx_conversations_timestamp ON conversations(timestamp DESC);
CREATE INDEX idx_conversations_user ON conversations(user_id);

-- ============================================================
-- Email drafts (with edited_body for feedback learning)
-- ============================================================
CREATE TABLE email_drafts (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    gmail_message_id VARCHAR(255),
    gmail_thread_id VARCHAR(255),
    from_address    VARCHAR(255),
    to_address      VARCHAR(255),
    subject         VARCHAR(500),
    original_body   TEXT,
    draft_body      TEXT,
    edited_body     TEXT,
    status          VARCHAR(50)  DEFAULT 'pending',
    classification  VARCHAR(50),
    context_used    JSONB        DEFAULT '{}',
    approved_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ
);

CREATE INDEX idx_email_drafts_status ON email_drafts(status);

-- ============================================================
-- Draft feedback (tracks edits as learning signals)
-- ============================================================
CREATE TABLE draft_feedback (
    id              SERIAL PRIMARY KEY,
    draft_id        INTEGER      NOT NULL REFERENCES email_drafts(id),
    sender_domain   VARCHAR(255),
    category        VARCHAR(100),
    edit_distance   INTEGER      NOT NULL DEFAULT 0,
    edit_ratio      FLOAT        NOT NULL DEFAULT 0.0,
    original_length INTEGER      NOT NULL DEFAULT 0,
    edited_length   INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_draft_feedback_domain ON draft_feedback(sender_domain);
CREATE INDEX idx_draft_feedback_category ON draft_feedback(category);

-- ============================================================
-- Agent metrics (daily aggregated)
-- ============================================================
CREATE TABLE agent_metrics (
    id              SERIAL PRIMARY KEY,
    date            DATE         NOT NULL,
    metric_name     VARCHAR(100) NOT NULL,
    metric_value    FLOAT        NOT NULL,
    metadata        JSONB        DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(date, metric_name)
);

-- ============================================================
-- Config (runtime configuration)
-- ============================================================
CREATE TABLE config (
    key             VARCHAR(255) PRIMARY KEY,
    value           JSONB        NOT NULL,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    description     TEXT
);
