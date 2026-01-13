-- Migration: 004_agent_chatbot.sql
-- Description: Add agent chatbot tables with pgvector for semantic memory
-- Created: 2026-01-11
-- Version: 4.0 (Codex-validated)

-- ============================================
-- EXTENSIONS
-- ============================================

-- pgvector for semantic embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- pgcrypto for UUID generation (if not already enabled)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- AGENT CONVERSATIONS TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS agent_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    summary TEXT,  -- Auto-generated summary for long conversations
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

COMMENT ON TABLE agent_conversations IS 'Chat conversations for the agent chatbot. Each conversation belongs to a user within a tenant.';
COMMENT ON COLUMN agent_conversations.tenant_id IS 'Tenant identifier for multi-tenancy isolation';
COMMENT ON COLUMN agent_conversations.user_id IS 'User who owns this conversation';
COMMENT ON COLUMN agent_conversations.summary IS 'Auto-generated summary for context in long conversations';

CREATE INDEX IF NOT EXISTS idx_agent_conversations_tenant_user
    ON agent_conversations(tenant_id, user_id, created_at DESC);

-- ============================================
-- AGENT MESSAGES TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,

    -- Chain of Thought: ONLY redacted summary, never raw reasoning
    thinking_summary TEXT,

    -- Tool calls with correlation IDs
    -- Format: [{tool_call_id, name, arguments, result}]
    tool_calls JSONB,

    -- Embeddings with model tracking for multi-provider support
    embedding vector(3072),  -- Max dimension to support multiple models
    embedding_model TEXT,    -- e.g., 'text-embedding-3-large', 'claude-3-embed'
    embedding_dimension INTEGER,  -- Actual dimension used
    embedding_status TEXT DEFAULT 'pending'
        CHECK (embedding_status IN ('pending', 'processing', 'completed', 'failed')),

    -- Model and performance metadata
    model_used TEXT,
    tokens_used INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE agent_messages IS 'Individual messages within agent conversations. Stores both user and assistant messages.';
COMMENT ON COLUMN agent_messages.thinking_summary IS 'Redacted CoT summary for UI display. Raw CoT is NEVER stored.';
COMMENT ON COLUMN agent_messages.embedding IS 'Vector embedding for semantic search. Dimension varies by model.';
COMMENT ON COLUMN agent_messages.embedding_model IS 'Model used to generate embedding (required for search filtering)';

-- Basic indexes
CREATE INDEX IF NOT EXISTS idx_agent_messages_conversation
    ON agent_messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_agent_messages_embedding_status
    ON agent_messages(embedding_status)
    WHERE embedding_status IN ('pending', 'failed');

-- Per-model partial indexes for embedding search
-- NOTE: pgvector HNSW/IVFFlat indexes only support up to 2000 dimensions
-- Our embedding column is vector(3072) to support multiple models
-- Since the column dimension > 2000, we cannot create vector indexes
-- Searches will use sequential scan which is fine for moderate data sizes
-- For production with millions of messages, consider using a separate 2000-dim column

-- ============================================
-- AGENT MEMORY TABLE (Long-term + Semantic)
-- ============================================

CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('fact', 'preference', 'entity', 'procedure')),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,  -- SHA-256 hash for deduplication

    -- Embeddings with model tracking
    embedding vector(3072),
    embedding_model TEXT,
    embedding_dimension INTEGER,

    -- Usage and relevance tracking
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,

    -- Source tracking (nullable for manually added memories)
    source_conversation_id UUID REFERENCES agent_conversations(id) ON DELETE SET NULL,
    source_message_id UUID REFERENCES agent_messages(id) ON DELETE SET NULL,

    -- Lifecycle management
    valid_from TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,  -- NULL = forever valid
    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    is_invalidated BOOLEAN DEFAULT FALSE,  -- Soft delete

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',

    -- Tenant + user scoped deduplication
    UNIQUE(tenant_id, user_id, content_hash)
);

COMMENT ON TABLE agent_memory IS 'Long-term memory storage with semantic search. Stores facts, preferences, entities extracted from conversations.';
COMMENT ON COLUMN agent_memory.memory_type IS 'fact=objective info, preference=user pref, entity=named entity, procedure=how-to';
COMMENT ON COLUMN agent_memory.content_hash IS 'SHA-256 hash of content for deduplication within user scope';
COMMENT ON COLUMN agent_memory.confidence IS 'Confidence score 0-1, decays over time for unused memories';
COMMENT ON COLUMN agent_memory.is_invalidated IS 'Soft delete flag. True = excluded from searches, pending hard delete';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_agent_memory_tenant_user
    ON agent_memory(tenant_id, user_id, memory_type)
    WHERE NOT is_invalidated;

CREATE INDEX IF NOT EXISTS idx_agent_memory_ttl
    ON agent_memory(valid_until)
    WHERE valid_until IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_memory_confidence
    ON agent_memory(tenant_id, user_id, confidence DESC)
    WHERE NOT is_invalidated;

CREATE INDEX IF NOT EXISTS idx_agent_memory_invalidated
    ON agent_memory(is_invalidated, updated_at)
    WHERE is_invalidated = TRUE;

CREATE INDEX IF NOT EXISTS idx_agent_memory_last_accessed
    ON agent_memory(last_accessed_at)
    WHERE last_accessed_at IS NOT NULL;

-- Per-model partial indexes for embedding search
-- NOTE: pgvector indexes only support up to 2000 dimensions
-- Column is vector(3072), so we skip creating vector indexes
-- Sequential scan will be used for similarity searches

-- ============================================
-- EMBEDDING JOBS QUEUE
-- ============================================

CREATE TABLE IF NOT EXISTS agent_embedding_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    target_table TEXT NOT NULL CHECK (target_table IN ('agent_messages', 'agent_memory')),
    target_id UUID NOT NULL,
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead')),
    retries INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    locked_at TIMESTAMPTZ,  -- For SKIP LOCKED pattern
    locked_by TEXT,  -- Worker ID for debugging
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,

    -- Prevent duplicate jobs for same target
    UNIQUE(target_table, target_id)
);

COMMENT ON TABLE agent_embedding_jobs IS 'Queue for background embedding generation. Uses SKIP LOCKED for concurrent workers.';
COMMENT ON COLUMN agent_embedding_jobs.status IS 'pending=waiting, processing=in progress, completed=done, failed=retry, dead=give up';
COMMENT ON COLUMN agent_embedding_jobs.locked_by IS 'Worker ID that claimed this job, for debugging stalled jobs';

CREATE INDEX IF NOT EXISTS idx_agent_embedding_jobs_pending
    ON agent_embedding_jobs(tenant_id, status, created_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_agent_embedding_jobs_status
    ON agent_embedding_jobs(status, created_at)
    WHERE status IN ('pending', 'failed');

CREATE INDEX IF NOT EXISTS idx_agent_embedding_jobs_locked
    ON agent_embedding_jobs(locked_at, locked_by)
    WHERE locked_at IS NOT NULL;

-- ============================================
-- AUDIT LOG FOR WRITE OPERATIONS
-- ============================================

CREATE TABLE IF NOT EXISTS agent_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- e.g., 'add_device', 'assign_subscription'
    resource_type TEXT,    -- e.g., 'device', 'subscription'
    resource_id TEXT,      -- ID of affected resource
    payload JSONB,         -- Request payload
    result JSONB,          -- Response/result
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed', 'conflict')),
    error_message TEXT,
    idempotency_key TEXT,  -- For retry safety
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Tenant-scoped idempotency
    UNIQUE(tenant_id, idempotency_key)
);

COMMENT ON TABLE agent_audit_log IS 'Audit log for all write operations performed by the agent chatbot.';
COMMENT ON COLUMN agent_audit_log.idempotency_key IS 'Client-provided key to prevent duplicate operations on retries';

CREATE INDEX IF NOT EXISTS idx_agent_audit_tenant_user
    ON agent_audit_log(tenant_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_audit_idempotency
    ON agent_audit_log(tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_audit_status
    ON agent_audit_log(status, created_at)
    WHERE status = 'pending';

-- ============================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================

-- Enable RLS on all tenant-scoped tables
ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_embedding_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_audit_log ENABLE ROW LEVEL SECURITY;

-- Conversations: tenant isolation
CREATE POLICY agent_conversations_tenant_isolation ON agent_conversations
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Memory: tenant isolation
CREATE POLICY agent_memory_tenant_isolation ON agent_memory
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Embedding jobs: tenant isolation
CREATE POLICY agent_embedding_jobs_tenant_isolation ON agent_embedding_jobs
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Audit log: tenant isolation
CREATE POLICY agent_audit_log_tenant_isolation ON agent_audit_log
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================
-- MEMORY LIFECYCLE MANAGEMENT FUNCTION
-- ============================================

CREATE OR REPLACE FUNCTION agent_memory_cleanup(p_tenant_id TEXT DEFAULT NULL)
RETURNS TABLE(invalidated_count INTEGER, decayed_count INTEGER, deleted_count INTEGER) AS $$
DECLARE
    v_invalidated INTEGER;
    v_decayed INTEGER;
    v_deleted INTEGER;
BEGIN
    -- 1. Invalidate expired memories (valid_until has passed)
    WITH invalidated AS (
        UPDATE agent_memory
        SET is_invalidated = TRUE, updated_at = NOW()
        WHERE valid_until IS NOT NULL
          AND valid_until < NOW()
          AND NOT is_invalidated
          AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id)
        RETURNING id
    )
    SELECT COUNT(*) INTO v_invalidated FROM invalidated;

    -- 2. Decay confidence for unused memories (30+ days without access)
    WITH decayed AS (
        UPDATE agent_memory
        SET confidence = confidence * 0.9, updated_at = NOW()
        WHERE (last_accessed_at IS NULL OR last_accessed_at < NOW() - INTERVAL '30 days')
          AND confidence > 0.1
          AND NOT is_invalidated
          AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id)
        RETURNING id
    )
    SELECT COUNT(*) INTO v_decayed FROM decayed;

    -- 3. Hard delete very old invalidated memories (90+ days)
    WITH deleted AS (
        DELETE FROM agent_memory
        WHERE is_invalidated = TRUE
          AND updated_at < NOW() - INTERVAL '90 days'
          AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id)
        RETURNING id
    )
    SELECT COUNT(*) INTO v_deleted FROM deleted;

    RETURN QUERY SELECT v_invalidated, v_decayed, v_deleted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION agent_memory_cleanup IS 'Lifecycle management for agent memory. Invalidates expired, decays unused, deletes old invalidated.';

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Update conversation message count trigger
CREATE OR REPLACE FUNCTION agent_update_conversation_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE agent_conversations
        SET message_count = message_count + 1, updated_at = NOW()
        WHERE id = NEW.conversation_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE agent_conversations
        SET message_count = message_count - 1, updated_at = NOW()
        WHERE id = OLD.conversation_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_messages_count_trigger
    AFTER INSERT OR DELETE ON agent_messages
    FOR EACH ROW
    EXECUTE FUNCTION agent_update_conversation_count();

-- Auto-create embedding job on message insert
CREATE OR REPLACE FUNCTION agent_queue_embedding_job()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.embedding IS NULL THEN
        INSERT INTO agent_embedding_jobs (tenant_id, target_table, target_id)
        SELECT
            c.tenant_id,
            'agent_messages',
            NEW.id
        FROM agent_conversations c
        WHERE c.id = NEW.conversation_id
        ON CONFLICT (target_table, target_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_messages_embedding_trigger
    AFTER INSERT ON agent_messages
    FOR EACH ROW
    EXECUTE FUNCTION agent_queue_embedding_job();

-- Auto-create embedding job on memory insert
CREATE OR REPLACE FUNCTION agent_queue_memory_embedding_job()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.embedding IS NULL THEN
        INSERT INTO agent_embedding_jobs (tenant_id, target_table, target_id)
        VALUES (NEW.tenant_id, 'agent_memory', NEW.id)
        ON CONFLICT (target_table, target_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_memory_embedding_trigger
    AFTER INSERT ON agent_memory
    FOR EACH ROW
    EXECUTE FUNCTION agent_queue_memory_embedding_job();

-- Update memory access tracking
CREATE OR REPLACE FUNCTION agent_track_memory_access(p_memory_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE agent_memory
    SET access_count = access_count + 1,
        last_accessed_at = NOW()
    WHERE id = p_memory_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VIEWS FOR COMMON QUERIES
-- ============================================

-- Active conversations with message count
CREATE OR REPLACE VIEW agent_active_conversations AS
SELECT
    c.id,
    c.tenant_id,
    c.user_id,
    c.title,
    c.summary,
    c.message_count,
    c.created_at,
    c.updated_at,
    (SELECT content FROM agent_messages m
     WHERE m.conversation_id = c.id
     ORDER BY m.created_at DESC LIMIT 1) as last_message
FROM agent_conversations c
WHERE c.updated_at > NOW() - INTERVAL '30 days'
ORDER BY c.updated_at DESC;

-- Memory statistics per user
CREATE OR REPLACE VIEW agent_memory_stats AS
SELECT
    tenant_id,
    user_id,
    memory_type,
    COUNT(*) as total_count,
    COUNT(*) FILTER (WHERE NOT is_invalidated) as active_count,
    AVG(confidence) FILTER (WHERE NOT is_invalidated) as avg_confidence,
    MAX(last_accessed_at) as last_accessed
FROM agent_memory
GROUP BY tenant_id, user_id, memory_type;

-- Embedding job queue status
CREATE OR REPLACE VIEW agent_embedding_queue_status AS
SELECT
    tenant_id,
    target_table,
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest_job,
    MAX(created_at) as newest_job
FROM agent_embedding_jobs
GROUP BY tenant_id, target_table, status
ORDER BY tenant_id, target_table, status;

-- ============================================
-- GRANTS (adjust role names as needed)
-- ============================================

-- Grant usage to application role
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_role;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_role;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_role;

-- ============================================
-- MIGRATION METADATA
-- ============================================

-- Record this migration in sync_history if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'sync_history') THEN
        INSERT INTO sync_history (resource_type, started_at, completed_at, status, records_fetched)
        VALUES ('agent_migration_004', NOW(), NOW(), 'completed', 5);
    END IF;
END $$;
