-- Add pgvector extension and embedding columns
-- Requires pgvector to be installed on the Postgres instance
-- If using Railway, deploy a custom Postgres image (pgvector/pgvector:pg16)

CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding columns
ALTER TABLE actions_log ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- HNSW indexes for fast similarity search
CREATE INDEX IF NOT EXISTS idx_incidents_embedding ON incidents USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding ON knowledge USING hnsw (embedding vector_cosine_ops);
