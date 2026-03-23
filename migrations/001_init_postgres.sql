CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_sources (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    type VARCHAR(32) NOT NULL,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_masked_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    sync_mode VARCHAR(32) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_sync_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_sync_jobs (
    id VARCHAR(32) PRIMARY KEY,
    source_id VARCHAR(32) NOT NULL REFERENCES kb_sources(id) ON DELETE CASCADE,
    mode VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    triggered_by VARCHAR(64) NOT NULL,
    processed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT NULL,
    failure_stage VARCHAR(64) NULL,
    snapshot_path VARCHAR(255) NULL,
    checkpoint_before VARCHAR(255) NULL,
    checkpoint_after VARCHAR(255) NULL,
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_sync_checkpoints (
    id VARCHAR(32) PRIMARY KEY,
    source_id VARCHAR(32) NOT NULL REFERENCES kb_sources(id) ON DELETE CASCADE,
    checkpoint_key VARCHAR(64) NOT NULL,
    checkpoint_value VARCHAR(255) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_kb_sync_checkpoints_source_key UNIQUE (source_id, checkpoint_key)
);

CREATE TABLE IF NOT EXISTS kb_documents (
    id VARCHAR(32) PRIMARY KEY,
    source_id VARCHAR(32) NOT NULL REFERENCES kb_sources(id) ON DELETE CASCADE,
    external_doc_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content_text TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    doc_type VARCHAR(64) NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    acl_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_kb_documents_source_external UNIQUE (source_id, external_doc_id)
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id VARCHAR(32) PRIMARY KEY,
    document_id VARCHAR(32) NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR,
    embedding_status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_kb_chunks_document_chunk UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_kb_documents_source_status
    ON kb_documents (source_id, status);

CREATE INDEX IF NOT EXISTS idx_kb_sync_jobs_source_created_at
    ON kb_sync_jobs (source_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_document_id
    ON kb_chunks (document_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_kb_chunks_embedding_ivfflat'
    ) THEN
        EXECUTE 'CREATE INDEX idx_kb_chunks_embedding_ivfflat ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
    END IF;
END $$;
