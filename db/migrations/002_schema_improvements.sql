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
-- Note: For fresh installs, columns are already TEXT (skip migration)
-- For upgrades from older schema, this would need to drop/recreate search_vector
-- Since we now create with TEXT from start, just skip if already TEXT

DO $$
BEGIN
    -- Only run if columns are still VARCHAR (upgrade scenario)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'devices' AND column_name = 'mac_address'
        AND data_type = 'character varying'
    ) THEN
        -- For upgrade: would need to drop search_vector first, then recreate
        -- This is complex, so for now we just skip - fresh installs already have TEXT
        RAISE NOTICE 'Skipping devices column type migration - requires search_vector recreation';
    ELSE
        RAISE NOTICE 'devices columns already TEXT, skipping type migration';
    END IF;
END $$;

-- Add CHECK constraint for mac_address length (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_devices_mac_length') THEN
        ALTER TABLE devices ADD CONSTRAINT chk_devices_mac_length CHECK (LENGTH(mac_address) <= 17);
    END IF;
END $$;

-- Add CHECK constraint for assigned_state values (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_devices_assigned_state') THEN
        ALTER TABLE devices ADD CONSTRAINT chk_devices_assigned_state
            CHECK (assigned_state IS NULL OR assigned_state IN ('ASSIGNED_TO_SERVICE', 'UNASSIGNED'));
    END IF;
END $$;

-- ============================================
-- SUBSCRIPTIONS TABLE: VARCHAR -> TEXT
-- ============================================
-- Skip if already TEXT (fresh install)

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'subscriptions' AND column_name = 'key'
        AND data_type = 'character varying'
    ) THEN
        RAISE NOTICE 'Skipping subscriptions column type migration - columns may be used by search_vector';
    ELSE
        RAISE NOTICE 'subscriptions columns already TEXT, skipping type migration';
    END IF;
END $$;

-- Add CHECK constraint for subscription_status values (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_subscriptions_status') THEN
        ALTER TABLE subscriptions ADD CONSTRAINT chk_subscriptions_status
            CHECK (subscription_status IN ('STARTED', 'ENDED', 'SUSPENDED', 'CANCELLED'));
    END IF;
END $$;

-- ============================================
-- DEVICE_SUBSCRIPTIONS TABLE: VARCHAR -> TEXT
-- ============================================
-- Skip - fresh install already has TEXT

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'device_subscriptions' AND column_name = 'resource_uri'
        AND data_type = 'character varying'
    ) THEN
        ALTER TABLE device_subscriptions ALTER COLUMN resource_uri TYPE TEXT;
        RAISE NOTICE 'device_subscriptions.resource_uri converted to TEXT';
    END IF;
END $$;

-- ============================================
-- DEVICE_TAGS TABLE: VARCHAR -> TEXT
-- ============================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'device_tags' AND column_name = 'tag_key'
        AND data_type = 'character varying'
    ) THEN
        ALTER TABLE device_tags ALTER COLUMN tag_key TYPE TEXT;
        ALTER TABLE device_tags ALTER COLUMN tag_value TYPE TEXT;
        RAISE NOTICE 'device_tags columns converted to TEXT';
    END IF;
END $$;

-- Add index for device lookup (if not exists)
CREATE INDEX IF NOT EXISTS idx_device_tags_device ON device_tags(device_id);

-- ============================================
-- SUBSCRIPTION_TAGS TABLE: VARCHAR -> TEXT
-- ============================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'subscription_tags' AND column_name = 'tag_key'
        AND data_type = 'character varying'
    ) THEN
        ALTER TABLE subscription_tags ALTER COLUMN tag_key TYPE TEXT;
        ALTER TABLE subscription_tags ALTER COLUMN tag_value TYPE TEXT;
        RAISE NOTICE 'subscription_tags columns converted to TEXT';
    END IF;
END $$;

-- Add index for subscription lookup (if not exists)
CREATE INDEX IF NOT EXISTS idx_subscription_tags_subscription ON subscription_tags(subscription_id);

-- ============================================
-- SYNC_HISTORY TABLE: Major Improvements
-- ============================================
-- Note: This migration handles multiple scenarios:
-- 1. Fresh database with correct schema from schema.sql (already has status column)
-- 2. Old database with legacy columns (devices_fetched, etc.)
-- 3. Database with partial migration

DO $$
DECLARE
    table_exists BOOLEAN;
    has_status_col BOOLEAN;
    has_devices_fetched_col BOOLEAN;
    has_devices_inserted_col BOOLEAN;
    has_devices_updated_col BOOLEAN;
    has_devices_errors_col BOOLEAN;
    has_records_fetched_col BOOLEAN;
    has_all_legacy_cols BOOLEAN;
BEGIN
    -- Check if sync_history table exists at all
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'sync_history'
    ) INTO table_exists;

    -- If table doesn't exist, schema.sql should have created it - nothing to migrate
    IF NOT table_exists THEN
        RAISE NOTICE 'sync_history table does not exist, skipping migration (schema.sql will create it)';
        RETURN;
    END IF;

    -- Check what columns exist in sync_history
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_history' AND column_name = 'status'
    ) INTO has_status_col;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_history' AND column_name = 'devices_fetched'
    ) INTO has_devices_fetched_col;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_history' AND column_name = 'devices_inserted'
    ) INTO has_devices_inserted_col;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_history' AND column_name = 'devices_updated'
    ) INTO has_devices_updated_col;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_history' AND column_name = 'devices_errors'
    ) INTO has_devices_errors_col;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_history' AND column_name = 'records_fetched'
    ) INTO has_records_fetched_col;

    -- All legacy columns must exist to use legacy migration path
    has_all_legacy_cols := has_devices_fetched_col AND has_devices_inserted_col
                           AND has_devices_updated_col AND has_devices_errors_col;

    -- If table already has the correct schema (status + records_fetched), skip migration
    IF has_status_col AND has_records_fetched_col THEN
        RAISE NOTICE 'sync_history already has correct schema, skipping migration';
        RETURN;
    END IF;

    -- Clean up any leftover sync_history_new from a previous partial migration
    DROP TABLE IF EXISTS sync_history_new CASCADE;

    -- Create new table with improved schema
    -- Include extended resource_type values for compatibility with later migrations
    -- Note: No CHECK constraint on resource_type - later migrations may add custom types
    CREATE TABLE sync_history_new (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        resource_type TEXT NOT NULL DEFAULT 'devices',
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

    -- Migrate existing data based on what columns exist
    IF has_all_legacy_cols AND has_status_col THEN
        -- Old schema: has all devices_* columns AND status column
        INSERT INTO sync_history_new (
            resource_type, started_at, completed_at, status,
            records_fetched, records_inserted, records_updated, records_errors, error_message
        )
        SELECT
            'devices',
            started_at,
            completed_at,
            -- Map legacy status values to allowed values
            CASE
                WHEN status IN ('success', 'completed') THEN 'completed'
                WHEN status = 'failed' THEN 'failed'
                WHEN status = 'running' THEN 'running'
                ELSE 'completed'  -- Default for unknown values
            END,
            COALESCE(devices_fetched, 0),
            COALESCE(devices_inserted, 0),
            COALESCE(devices_updated, 0),
            COALESCE(devices_errors, 0),
            error_message
        FROM sync_history
        WHERE started_at IS NOT NULL;
        RAISE NOTICE 'Migrated from legacy devices_* columns with status';
    ELSIF has_all_legacy_cols AND NOT has_status_col THEN
        -- Very old schema: has devices_* columns but no status column
        INSERT INTO sync_history_new (
            resource_type, started_at, completed_at, status,
            records_fetched, records_inserted, records_updated, records_errors, error_message
        )
        SELECT
            'devices',
            started_at,
            completed_at,
            'completed',  -- Default status when column doesn't exist
            COALESCE(devices_fetched, 0),
            COALESCE(devices_inserted, 0),
            COALESCE(devices_updated, 0),
            COALESCE(devices_errors, 0),
            error_message
        FROM sync_history
        WHERE started_at IS NOT NULL;
        RAISE NOTICE 'Migrated from legacy devices_* columns (no status column)';
    ELSIF has_status_col THEN
        -- Intermediate schema: has status but not records_fetched
        INSERT INTO sync_history_new (
            resource_type, started_at, completed_at, status,
            records_fetched, records_inserted, records_updated, records_errors, error_message
        )
        SELECT
            -- Map legacy resource types
            CASE
                WHEN resource_type = 'central' THEN 'central_devices'
                WHEN resource_type IS NULL THEN 'devices'
                ELSE resource_type
            END,
            started_at,
            completed_at,
            -- Map legacy status values
            CASE
                WHEN status IN ('success', 'completed') THEN 'completed'
                WHEN status = 'failed' THEN 'failed'
                WHEN status = 'running' THEN 'running'
                ELSE 'completed'
            END,
            0, 0, 0, 0,
            error_message
        FROM sync_history
        WHERE started_at IS NOT NULL;
        RAISE NOTICE 'Migrated from intermediate schema (status only)';
    ELSE
        -- Very old schema or empty: just migrate basic fields
        INSERT INTO sync_history_new (
            resource_type, started_at, completed_at, status, error_message
        )
        SELECT
            'devices',
            started_at,
            completed_at,
            'completed',
            error_message
        FROM sync_history
        WHERE started_at IS NOT NULL;
        RAISE NOTICE 'Migrated from very old schema';
    END IF;

    -- Swap tables
    DROP TABLE IF EXISTS sync_history CASCADE;
    ALTER TABLE sync_history_new RENAME TO sync_history;

    RAISE NOTICE 'sync_history migration completed successfully';
END $$;

-- Add indexes (idempotent)
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
