-- Runs once when the pgvector container first boots.
CREATE EXTENSION IF NOT EXISTS vector;

-- Project 1 - generic doc corpus
CREATE TABLE IF NOT EXISTS docs (
    chunk_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding vector(1024)
);

CREATE INDEX IF NOT EXISTS docs_embedding_idx
    ON docs USING hnsw (embedding vector_cosine_ops);

-- Project 2 - runbooks per domain (created lazily by ingest scripts as needed)
-- runbooks_support, runbooks_it_helpdesk, runbooks_oncall

-- Project 2 - past resolutions (episodic memory)
CREATE TABLE IF NOT EXISTS past_resolutions (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    ticket_text TEXT NOT NULL,
    resolution_text TEXT NOT NULL,
    embedding vector(1024),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS past_resolutions_embedding_idx
    ON past_resolutions USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS past_resolutions_domain_idx
    ON past_resolutions (domain);

-- LangGraph stores its own checkpoint/store tables via Python on first use.
