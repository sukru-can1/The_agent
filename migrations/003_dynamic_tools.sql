-- Dynamic tools — agent-created tools persisted for reuse
CREATE TABLE IF NOT EXISTS dynamic_tools (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    input_schema JSONB NOT NULL,
    code        TEXT NOT NULL,
    created_by  TEXT NOT NULL DEFAULT 'agent',
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dynamic_tools_active ON dynamic_tools(active) WHERE active = true;
