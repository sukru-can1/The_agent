-- Conversation sessions: thread-based memory for GChat and Dashboard
-- Gives the LLM awareness of prior messages within the same thread/conversation.

CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_key     TEXT UNIQUE NOT NULL,
    platform        TEXT NOT NULL,
    user_id         TEXT,
    user_name       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT NOT NULL DEFAULT 'active',
    message_count   INT NOT NULL DEFAULT 0,
    summary         TEXT,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_key ON sessions(session_key);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active_at);

CREATE TABLE IF NOT EXISTS session_messages (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    tool_calls      JSONB,
    tool_call_id    TEXT,
    tool_name       TEXT,
    event_id        UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_messages_session_time ON session_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_messages_event ON session_messages(event_id);
