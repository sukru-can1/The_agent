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
