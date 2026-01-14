-- Migration: 007_custom_reports.sql
-- Description: Add custom_reports table for report builder feature
-- Created: 2026-01-13
-- Version: 7.0

-- ============================================
-- EXTENSIONS
-- ============================================

-- pgcrypto for UUID generation (if not already enabled)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- CUSTOM REPORTS TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS custom_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    created_by TEXT NOT NULL,

    -- Report configuration (fields, filters, grouping, sorting)
    -- Format: {
    --   "fields": [{"table": "devices", "field": "serial_number", "alias": "Serial"}],
    --   "filters": [{"field": "device_type", "operator": "equals", "value": "SWITCH", "logic": "AND"}],
    --   "grouping": [{"field": "region", "aggregation": "COUNT"}],
    --   "sorting": [{"field": "created_at", "direction": "DESC"}]
    -- }
    config JSONB NOT NULL,

    -- Sharing and permissions
    is_shared BOOLEAN DEFAULT FALSE,
    shared_with JSONB DEFAULT '[]',  -- Array of user IDs or tenant IDs

    -- Lifecycle management
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,  -- Soft delete for audit trail

    -- Additional metadata
    metadata JSONB DEFAULT '{}',

    -- Execution statistics
    last_executed_at TIMESTAMPTZ,
    execution_count INTEGER DEFAULT 0
);

COMMENT ON TABLE custom_reports IS 'Custom report templates created by users. Stores report configuration for drag-and-drop report builder.';
COMMENT ON COLUMN custom_reports.name IS 'User-defined report template name';
COMMENT ON COLUMN custom_reports.description IS 'Optional description of what the report shows';
COMMENT ON COLUMN custom_reports.created_by IS 'User ID of the report creator/owner';
COMMENT ON COLUMN custom_reports.config IS 'JSONB configuration containing field selections, filters, grouping, and sorting';
COMMENT ON COLUMN custom_reports.is_shared IS 'Whether this report is shared with other users';
COMMENT ON COLUMN custom_reports.shared_with IS 'Array of user/tenant IDs who have access to this report';
COMMENT ON COLUMN custom_reports.deleted_at IS 'Soft delete timestamp for audit trail. NULL = active report';

-- ============================================
-- INDEXES
-- ============================================

-- Query by owner
CREATE INDEX IF NOT EXISTS idx_custom_reports_created_by
    ON custom_reports(created_by, created_at DESC)
    WHERE deleted_at IS NULL;

-- Active reports only (exclude soft-deleted)
CREATE INDEX IF NOT EXISTS idx_custom_reports_active
    ON custom_reports(created_at DESC)
    WHERE deleted_at IS NULL;

-- Shared reports
CREATE INDEX IF NOT EXISTS idx_custom_reports_shared
    ON custom_reports(is_shared, created_at DESC)
    WHERE deleted_at IS NULL AND is_shared = TRUE;

-- Search by name (for autocomplete/search)
CREATE INDEX IF NOT EXISTS idx_custom_reports_name
    ON custom_reports USING GIN(to_tsvector('english', name))
    WHERE deleted_at IS NULL;

-- JSONB config index for advanced queries
CREATE INDEX IF NOT EXISTS idx_custom_reports_config
    ON custom_reports USING GIN(config jsonb_path_ops);

-- Recently executed reports
CREATE INDEX IF NOT EXISTS idx_custom_reports_last_executed
    ON custom_reports(last_executed_at DESC NULLS LAST)
    WHERE deleted_at IS NULL;

-- Popular reports (by execution count)
CREATE INDEX IF NOT EXISTS idx_custom_reports_execution_count
    ON custom_reports(execution_count DESC)
    WHERE deleted_at IS NULL;

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Update updated_at timestamp on row modification
CREATE OR REPLACE FUNCTION custom_reports_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER custom_reports_update_timestamp_trigger
    BEFORE UPDATE ON custom_reports
    FOR EACH ROW
    EXECUTE FUNCTION custom_reports_update_timestamp();

-- Increment execution count and update last_executed_at
CREATE OR REPLACE FUNCTION custom_reports_track_execution(p_report_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE custom_reports
    SET execution_count = execution_count + 1,
        last_executed_at = NOW()
    WHERE id = p_report_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION custom_reports_track_execution IS 'Track report execution statistics. Call this when a report is executed.';

-- ============================================
-- VIEWS
-- ============================================

-- Active reports (exclude soft-deleted)
CREATE OR REPLACE VIEW custom_reports_active AS
SELECT
    id,
    name,
    description,
    created_by,
    config,
    is_shared,
    shared_with,
    created_at,
    updated_at,
    last_executed_at,
    execution_count,
    metadata
FROM custom_reports
WHERE deleted_at IS NULL
ORDER BY updated_at DESC;

COMMENT ON VIEW custom_reports_active IS 'Active custom reports excluding soft-deleted ones';

-- Popular reports (by execution count)
CREATE OR REPLACE VIEW custom_reports_popular AS
SELECT
    id,
    name,
    description,
    created_by,
    execution_count,
    last_executed_at,
    created_at
FROM custom_reports
WHERE deleted_at IS NULL
  AND execution_count > 0
ORDER BY execution_count DESC, last_executed_at DESC
LIMIT 100;

COMMENT ON VIEW custom_reports_popular IS 'Top 100 most frequently executed reports';

-- Recently executed reports
CREATE OR REPLACE VIEW custom_reports_recent AS
SELECT
    id,
    name,
    description,
    created_by,
    last_executed_at,
    execution_count,
    created_at
FROM custom_reports
WHERE deleted_at IS NULL
  AND last_executed_at IS NOT NULL
ORDER BY last_executed_at DESC
LIMIT 100;

COMMENT ON VIEW custom_reports_recent IS 'Top 100 most recently executed reports';

-- ============================================
-- MIGRATION METADATA
-- ============================================

-- Record this migration in sync_history if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'sync_history') THEN
        INSERT INTO sync_history (resource_type, started_at, completed_at, status, records_fetched)
        VALUES ('custom_reports_migration_007', NOW(), NOW(), 'completed', 1);
    END IF;
END $$;
