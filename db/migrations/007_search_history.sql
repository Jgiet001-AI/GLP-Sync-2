-- Migration: 007_search_history.sql
-- Description: Add search_history table for persistent search queries and suggestions
-- Created: 2026-01-13
-- Version: 7.0

-- ============================================
-- EXTENSIONS
-- ============================================

-- pgcrypto for UUID generation (if not already enabled)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- SEARCH HISTORY TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS search_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    search_type TEXT NOT NULL CHECK (search_type IN ('device', 'subscription')),
    result_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

COMMENT ON TABLE search_history IS 'Persistent search history for dashboard search functionality. Stores user search queries with tenant/user isolation.';
COMMENT ON COLUMN search_history.tenant_id IS 'Tenant identifier for multi-tenancy isolation';
COMMENT ON COLUMN search_history.user_id IS 'User who performed the search';
COMMENT ON COLUMN search_history.query IS 'Search query text entered by the user';
COMMENT ON COLUMN search_history.search_type IS 'Type of search: device or subscription';
COMMENT ON COLUMN search_history.result_count IS 'Number of results returned for this search (optional)';
COMMENT ON COLUMN search_history.metadata IS 'Additional metadata (filters applied, search duration, etc.)';

-- ============================================
-- INDEXES
-- ============================================

-- Primary index for listing user's recent searches
CREATE INDEX IF NOT EXISTS idx_search_history_tenant_user
    ON search_history(tenant_id, user_id, created_at DESC);

-- Index for filtering by search type
CREATE INDEX IF NOT EXISTS idx_search_history_search_type
    ON search_history(tenant_id, user_id, search_type, created_at DESC);

-- Index for prefix matching suggestions (case-insensitive)
-- Using text_pattern_ops for LIKE/ILIKE queries
CREATE INDEX IF NOT EXISTS idx_search_history_query_prefix
    ON search_history(tenant_id, user_id, search_type, query text_pattern_ops);

-- Index for finding recent searches (cleanup/analytics)
CREATE INDEX IF NOT EXISTS idx_search_history_created_at
    ON search_history(created_at DESC);
