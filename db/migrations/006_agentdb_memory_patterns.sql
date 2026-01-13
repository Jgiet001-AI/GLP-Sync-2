-- Migration: 006_agentdb_memory_patterns.sql
-- Description: Add AgentDB memory pattern tables for persistent sessions, pattern learning, and memory versioning
-- Created: 2026-01-12
-- Version: 1.0

-- ============================================
-- PERSISTENT SESSIONS TABLE
-- ============================================
-- Stores operation state, pending confirmations, and context
-- that survives server restarts and supports multi-instance deployments.

CREATE TABLE IF NOT EXISTS agent_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_type TEXT NOT NULL CHECK (session_type IN ('confirmation', 'operation', 'context', 'cache')),
    key TEXT NOT NULL,  -- Unique key within session type (e.g., "conv-abc:op-123")
    data JSONB NOT NULL DEFAULT '{}',
    expires_at TIMESTAMPTZ,  -- NULL = no expiration
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Tenant + user + type + key scoped uniqueness
    UNIQUE(tenant_id, user_id, session_type, key)
);

COMMENT ON TABLE agent_sessions IS 'Persistent session storage for operation state, confirmations, and context. Replaces in-memory storage.';
COMMENT ON COLUMN agent_sessions.session_type IS 'confirmation=pending ops, operation=in-flight state, context=conversation context, cache=temp data';
COMMENT ON COLUMN agent_sessions.key IS 'Unique key within session type, e.g., conversation_id:operation_id';
COMMENT ON COLUMN agent_sessions.expires_at IS 'TTL expiration timestamp. NULL = no expiration.';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_agent_sessions_lookup
    ON agent_sessions(tenant_id, user_id, session_type, key);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_expiry
    ON agent_sessions(expires_at)
    WHERE expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_sessions_type
    ON agent_sessions(tenant_id, session_type, created_at DESC);

-- ============================================
-- LEARNED PATTERNS TABLE
-- ============================================
-- Stores successful interaction patterns for future retrieval and application.

CREATE TABLE IF NOT EXISTS agent_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL CHECK (pattern_type IN ('tool_success', 'query_response', 'error_recovery', 'workflow')),
    trigger_text TEXT NOT NULL,  -- What triggers this pattern
    trigger_hash TEXT NOT NULL,  -- SHA-256 for deduplication

    -- Embeddings for semantic search
    trigger_embedding vector(3072),
    embedding_model TEXT,
    embedding_dimension INTEGER,

    response TEXT NOT NULL,  -- Expected response/action
    context JSONB DEFAULT '{}',  -- Additional context

    -- Success tracking
    success_count INTEGER DEFAULT 1,
    failure_count INTEGER DEFAULT 0,
    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),

    -- Lifecycle
    last_used_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Tenant-scoped deduplication
    UNIQUE(tenant_id, trigger_hash)
);

COMMENT ON TABLE agent_patterns IS 'Learned interaction patterns. Captures successful tool calls, Q&A, error recovery, and workflows.';
COMMENT ON COLUMN agent_patterns.pattern_type IS 'tool_success=successful tool use, query_response=Q&A, error_recovery=error handling, workflow=multi-step';
COMMENT ON COLUMN agent_patterns.trigger_hash IS 'SHA-256 hash of (pattern_type:trigger_text) for deduplication';
COMMENT ON COLUMN agent_patterns.confidence IS 'success_count / (success_count + failure_count), decays with failures';

-- Indexes for pattern lookup
CREATE INDEX IF NOT EXISTS idx_agent_patterns_type_confidence
    ON agent_patterns(tenant_id, pattern_type, confidence DESC)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_agent_patterns_active
    ON agent_patterns(tenant_id, is_active, last_used_at DESC);

-- Per-model partial index for semantic pattern search
-- NOTE: pgvector indexes only support up to 2000 dimensions
-- Column is vector(3072), so we skip creating vector indexes
-- Sequential scan will be used for similarity searches

-- ============================================
-- MEMORY REVISIONS TABLE
-- ============================================
-- Tracks changes to memories over time for correction and audit.

CREATE TABLE IF NOT EXISTS agent_memory_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL REFERENCES agent_memory(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    version_state TEXT NOT NULL CHECK (version_state IN ('current', 'superseded', 'corrected', 'merged')),

    content TEXT NOT NULL,
    previous_content TEXT,  -- For diff display
    change_reason TEXT,  -- Why the change was made
    changed_by TEXT,  -- User who made the change (null = system)

    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Each memory can have only one current version (partial unique index)
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memory_revisions_unique_current
    ON agent_memory_revisions(memory_id)
    WHERE version_state = 'current';

COMMENT ON TABLE agent_memory_revisions IS 'Version history for agent memories. Enables corrections, rollback, and audit trails.';
COMMENT ON COLUMN agent_memory_revisions.version_state IS 'current=active version, superseded=replaced, corrected=user fix, merged=combined';
COMMENT ON COLUMN agent_memory_revisions.change_reason IS 'Human-readable reason for the change, for audit purposes';

-- Indexes for revision queries
CREATE INDEX IF NOT EXISTS idx_agent_memory_revisions_memory
    ON agent_memory_revisions(memory_id, version DESC);

CREATE INDEX IF NOT EXISTS idx_agent_memory_revisions_current
    ON agent_memory_revisions(memory_id, version_state)
    WHERE version_state = 'current';

CREATE INDEX IF NOT EXISTS idx_agent_memory_revisions_user
    ON agent_memory_revisions(tenant_id, user_id, created_at DESC);

-- ============================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================

-- Enable RLS on new tables
ALTER TABLE agent_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memory_revisions ENABLE ROW LEVEL SECURITY;

-- Sessions: tenant isolation
CREATE POLICY agent_sessions_tenant_isolation ON agent_sessions
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Patterns: tenant isolation
CREATE POLICY agent_patterns_tenant_isolation ON agent_patterns
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Memory revisions: tenant isolation
CREATE POLICY agent_memory_revisions_tenant_isolation ON agent_memory_revisions
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to clean up expired sessions
CREATE OR REPLACE FUNCTION agent_cleanup_expired_sessions(p_tenant_id TEXT DEFAULT NULL)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    WITH deleted AS (
        DELETE FROM agent_sessions
        WHERE expires_at IS NOT NULL
          AND expires_at < NOW()
          AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id)
        RETURNING id
    )
    SELECT COUNT(*) INTO v_count FROM deleted;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION agent_cleanup_expired_sessions IS 'Remove expired session data. Run periodically.';

-- Function to decay pattern confidence for unused patterns
CREATE OR REPLACE FUNCTION agent_decay_pattern_confidence(
    p_days_unused INTEGER DEFAULT 30,
    p_decay_factor FLOAT DEFAULT 0.9,
    p_tenant_id TEXT DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    WITH decayed AS (
        UPDATE agent_patterns
        SET confidence = confidence * p_decay_factor,
            updated_at = NOW()
        WHERE is_active = TRUE
          AND (last_used_at IS NULL OR last_used_at < NOW() - (p_days_unused || ' days')::INTERVAL)
          AND confidence > 0.1
          AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id)
        RETURNING id
    )
    SELECT COUNT(*) INTO v_count FROM decayed;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION agent_decay_pattern_confidence IS 'Decay confidence for unused patterns. Run periodically.';

-- Function to get pattern stats
CREATE OR REPLACE FUNCTION agent_pattern_stats(p_tenant_id TEXT)
RETURNS TABLE (
    pattern_type TEXT,
    total_count BIGINT,
    active_count BIGINT,
    avg_confidence FLOAT,
    total_successes BIGINT,
    total_failures BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.pattern_type,
        COUNT(*) as total_count,
        COUNT(*) FILTER (WHERE p.is_active) as active_count,
        AVG(p.confidence) FILTER (WHERE p.is_active) as avg_confidence,
        SUM(p.success_count) as total_successes,
        SUM(p.failure_count) as total_failures
    FROM agent_patterns p
    WHERE p.tenant_id = p_tenant_id
    GROUP BY p.pattern_type;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION agent_pattern_stats IS 'Get pattern learning statistics by type for a tenant.';

-- ============================================
-- VIEWS
-- ============================================

-- View: Active sessions with TTL remaining
CREATE OR REPLACE VIEW agent_active_sessions AS
SELECT
    id,
    tenant_id,
    user_id,
    session_type,
    key,
    data,
    expires_at,
    CASE
        WHEN expires_at IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (expires_at - NOW()))::INTEGER
    END as ttl_remaining_seconds,
    created_at,
    updated_at
FROM agent_sessions
WHERE expires_at IS NULL OR expires_at > NOW();

-- View: Pattern learning summary
CREATE OR REPLACE VIEW agent_pattern_summary AS
SELECT
    tenant_id,
    pattern_type,
    COUNT(*) as pattern_count,
    COUNT(*) FILTER (WHERE is_active) as active_count,
    AVG(confidence) FILTER (WHERE is_active) as avg_confidence,
    MAX(last_used_at) as last_pattern_used,
    SUM(success_count) as total_successes,
    SUM(failure_count) as total_failures
FROM agent_patterns
GROUP BY tenant_id, pattern_type;

-- View: Memory revision statistics
CREATE OR REPLACE VIEW agent_memory_revision_stats AS
SELECT
    tenant_id,
    user_id,
    COUNT(DISTINCT memory_id) as memories_with_revisions,
    COUNT(*) as total_revisions,
    COUNT(*) FILTER (WHERE version_state = 'corrected') as corrections,
    MAX(created_at) as last_revision
FROM agent_memory_revisions
GROUP BY tenant_id, user_id;

-- ============================================
-- MIGRATION METADATA
-- ============================================

-- Record this migration
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'sync_history') THEN
        INSERT INTO sync_history (resource_type, started_at, completed_at, status, records_fetched)
        VALUES ('agent_migration_006_agentdb', NOW(), NOW(), 'completed', 3);
    END IF;
END $$;
