-- Migration 002: PostgreSQL Best Practices Improvements
-- Applied: 2026-01-09
--
-- This migration applies PostgreSQL best practices to existing databases:
-- - VARCHAR(n) -> TEXT (no performance difference, removes arbitrary limits)
-- - SERIAL -> IDENTITY (SQL-standard, cleaner sequence ownership)
-- - Add CHECK constraints for status columns
-- - Add NOT NULL with defaults to sync_history
-- - Add new indexes for performance
-- - Enhance sync_history for subscription tracking

-- ============================================
-- DEVICES TABLE: VARCHAR -> TEXT
-- ============================================
-- Note: PostgreSQL allows changing VARCHAR to TEXT without rewriting data

ALTER TABLE devices ALTER COLUMN mac_address TYPE TEXT;
ALTER TABLE devices ALTER COLUMN serial_number TYPE TEXT;
ALTER TABLE devices ALTER COLUMN part_number TYPE TEXT;
ALTER TABLE devices ALTER COLUMN device_type TYPE TEXT;
ALTER TABLE devices ALTER COLUMN model TYPE TEXT;
ALTER TABLE devices ALTER COLUMN region TYPE TEXT;
ALTER TABLE devices ALTER COLUMN device_name TYPE TEXT;
ALTER TABLE devices ALTER COLUMN secondary_name TYPE TEXT;
ALTER TABLE devices ALTER COLUMN assigned_state TYPE TEXT;
ALTER TABLE devices ALTER COLUMN resource_type TYPE TEXT;
ALTER TABLE devices ALTER COLUMN application_resource_uri TYPE TEXT;
ALTER TABLE devices ALTER COLUMN location_name TYPE TEXT;
ALTER TABLE devices ALTER COLUMN location_city TYPE TEXT;
ALTER TABLE devices ALTER COLUMN location_state TYPE TEXT;
ALTER TABLE devices ALTER COLUMN location_country TYPE TEXT;
ALTER TABLE devices ALTER COLUMN location_postal_code TYPE TEXT;
ALTER TABLE devices ALTER COLUMN location_street_address TYPE TEXT;
ALTER TABLE devices ALTER COLUMN location_source TYPE TEXT;

-- Add CHECK constraint for mac_address length
ALTER TABLE devices ADD CONSTRAINT chk_devices_mac_length
    CHECK (LENGTH(mac_address) <= 17);

-- Add CHECK constraint for assigned_state values
ALTER TABLE devices ADD CONSTRAINT chk_devices_assigned_state
    CHECK (assigned_state IS NULL OR assigned_state IN ('ASSIGNED_TO_SERVICE', 'UNASSIGNED'));

-- ============================================
-- SUBSCRIPTIONS TABLE: VARCHAR -> TEXT
-- ============================================

ALTER TABLE subscriptions ALTER COLUMN key TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN resource_type TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN subscription_type TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN subscription_status TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN sku TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN tier TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN product_type TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN contract TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN quote TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN po TYPE TEXT;
ALTER TABLE subscriptions ALTER COLUMN reseller_po TYPE TEXT;

-- Add CHECK constraint for subscription_status values
ALTER TABLE subscriptions ADD CONSTRAINT chk_subscriptions_status
    CHECK (subscription_status IN ('STARTED', 'ENDED', 'SUSPENDED', 'CANCELLED'));

-- ============================================
-- DEVICE_SUBSCRIPTIONS TABLE: VARCHAR -> TEXT
-- ============================================

ALTER TABLE device_subscriptions ALTER COLUMN resource_uri TYPE TEXT;

-- ============================================
-- DEVICE_TAGS TABLE: VARCHAR -> TEXT
-- ============================================

ALTER TABLE device_tags ALTER COLUMN tag_key TYPE TEXT;
ALTER TABLE device_tags ALTER COLUMN tag_value TYPE TEXT;

-- Add index for device lookup (if not exists)
CREATE INDEX IF NOT EXISTS idx_device_tags_device ON device_tags(device_id);

-- ============================================
-- SUBSCRIPTION_TAGS TABLE: VARCHAR -> TEXT
-- ============================================

ALTER TABLE subscription_tags ALTER COLUMN tag_key TYPE TEXT;
ALTER TABLE subscription_tags ALTER COLUMN tag_value TYPE TEXT;

-- Add index for subscription lookup (if not exists)
CREATE INDEX IF NOT EXISTS idx_subscription_tags_subscription ON subscription_tags(subscription_id);

-- ============================================
-- SYNC_HISTORY TABLE: Major Improvements
-- ============================================
-- Note: This requires recreating the table due to SERIAL -> IDENTITY change

-- Create new table with improved schema
CREATE TABLE IF NOT EXISTS sync_history_new (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_type TEXT NOT NULL DEFAULT 'devices' CHECK (resource_type IN ('devices', 'subscriptions', 'all')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    records_fetched INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    records_errors INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    duration_ms INTEGER GENERATED ALWAYS AS (
        CASE WHEN completed_at IS NOT NULL
             THEN (EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000)::INTEGER
        END
    ) STORED
);

-- Migrate existing data (map old column names to new)
INSERT INTO sync_history_new (
    resource_type,
    started_at,
    completed_at,
    status,
    records_fetched,
    records_inserted,
    records_updated,
    records_errors,
    error_message
)
SELECT
    'devices',
    started_at,
    completed_at,
    COALESCE(status, 'running'),
    COALESCE(devices_fetched, 0),
    COALESCE(devices_inserted, 0),
    COALESCE(devices_updated, 0),
    COALESCE(devices_errors, 0),
    error_message
FROM sync_history
WHERE started_at IS NOT NULL;

-- Swap tables
DROP TABLE IF EXISTS sync_history CASCADE;
ALTER TABLE sync_history_new RENAME TO sync_history;

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_sync_history_resource_type ON sync_history(resource_type);
CREATE INDEX IF NOT EXISTS idx_sync_history_started ON sync_history(started_at DESC);

-- ============================================
-- QUERY_EXAMPLES TABLE: Improvements
-- ============================================
-- Note: Recreate with better schema if it exists

DO $$
BEGIN
    -- Check if table exists and has old schema
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'query_examples'
        AND column_name = 'category'
        AND data_type = 'character varying'
    ) THEN
        -- Create new table
        CREATE TABLE query_examples_new (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            category TEXT NOT NULL CHECK (category IN ('search', 'filter', 'expiring', 'summary', 'join', 'tags')),
            description TEXT NOT NULL,
            sql_query TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (category, description)
        );

        -- Migrate data
        INSERT INTO query_examples_new (category, description, sql_query)
        SELECT category, description, sql_query
        FROM query_examples
        ON CONFLICT (category, description) DO NOTHING;

        -- Swap tables
        DROP TABLE query_examples CASCADE;
        ALTER TABLE query_examples_new RENAME TO query_examples;
    END IF;
END $$;

-- ============================================
-- NEW INDEXES FOR PERFORMANCE
-- ============================================

-- Covering index for expiring subscriptions view
CREATE INDEX IF NOT EXISTS idx_subscriptions_expiring_covering
ON subscriptions(end_time)
INCLUDE (key, subscription_type, tier, sku, quantity, available_quantity)
WHERE subscription_status = 'STARTED';

-- ============================================
-- UPDATE FUNCTION RETURN TYPES
-- ============================================

-- Recreate search_devices function with TEXT return types
CREATE OR REPLACE FUNCTION search_devices(
    search_query TEXT,
    max_results INTEGER DEFAULT 50
) RETURNS TABLE (
    id UUID,
    serial_number TEXT,
    device_name TEXT,
    device_type TEXT,
    model TEXT,
    region TEXT,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.serial_number,
        d.device_name,
        d.device_type,
        d.model,
        d.region,
        ts_rank(d.search_vector, websearch_to_tsquery('english', search_query)) as rank
    FROM devices d
    WHERE d.search_vector @@ websearch_to_tsquery('english', search_query)
        AND NOT d.archived
    ORDER BY rank DESC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- UPDATE COMMENTS
-- ============================================

COMMENT ON TABLE sync_history IS 'Tracks sync operations from GreenLake API for both devices and subscriptions. Shows when data was last updated, sync statistics, and duration.';
COMMENT ON COLUMN sync_history.resource_type IS 'Type of sync: devices, subscriptions, or all';
COMMENT ON COLUMN sync_history.records_fetched IS 'Number of records fetched from API';
COMMENT ON COLUMN sync_history.records_inserted IS 'Number of new records inserted';
COMMENT ON COLUMN sync_history.records_updated IS 'Number of existing records updated';
COMMENT ON COLUMN sync_history.records_errors IS 'Number of records that failed to process';
COMMENT ON COLUMN sync_history.duration_ms IS 'Sync duration in milliseconds (computed from started_at and completed_at)';
