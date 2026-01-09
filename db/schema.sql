-- HPE GreenLake Device Inventory Schema
-- PostgreSQL 18+
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
-- For fuzzy text search
-- Main devices table
CREATE TABLE IF NOT EXISTS devices (
    -- Primary identifier (UUID from GreenLake API)
    id UUID PRIMARY KEY,
    -- Core indexed fields for common queries
    mac_address VARCHAR(17),
    serial_number VARCHAR(100) NOT NULL,
    part_number VARCHAR(100),
    device_type VARCHAR(50),
    -- SWITCH, AP, COMPUTE, STORAGE, etc.
    model VARCHAR(100),
    region VARCHAR(50),
    archived BOOLEAN DEFAULT FALSE,
    device_name VARCHAR(255),
    secondary_name VARCHAR(255),
    assigned_state VARCHAR(50),
    -- ASSIGNED_TO_SERVICE, UNASSIGNED, etc.
    -- Timestamps from API
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    -- Our sync tracking
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    -- Full API response for flexibility
    -- Query nested fields: raw_data->'subscription', raw_data->'tags', etc.
    raw_data JSONB NOT NULL,
    -- Auto-generated full-text search vector
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('english', coalesce(serial_number, '')),
            'A'
        ) || setweight(
            to_tsvector('english', coalesce(device_name, '')),
            'A'
        ) || setweight(
            to_tsvector('english', coalesce(mac_address, '')),
            'B'
        ) || setweight(to_tsvector('english', coalesce(model, '')), 'B') || setweight(
            to_tsvector('english', coalesce(device_type, '')),
            'C'
        ) || setweight(
            to_tsvector('english', coalesce(region, '')),
            'C'
        )
    ) STORED
);
-- ============================================
-- INDEXES: Optimize for your query patterns
-- ============================================
-- Exact lookups
CREATE INDEX IF NOT EXISTS idx_devices_serial ON devices(serial_number);
CREATE INDEX IF NOT EXISTS idx_devices_mac ON devices(mac_address);
-- Filter queries (WHERE clauses)
CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(device_type);
CREATE INDEX IF NOT EXISTS idx_devices_region ON devices(region);
CREATE INDEX IF NOT EXISTS idx_devices_assigned ON devices(assigned_state);
CREATE INDEX IF NOT EXISTS idx_devices_archived ON devices(archived)
WHERE NOT archived;
-- Sorting/pagination
CREATE INDEX IF NOT EXISTS idx_devices_updated ON devices(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_devices_created ON devices(created_at DESC);
-- Full-text search (for search bars)
CREATE INDEX IF NOT EXISTS idx_devices_search ON devices USING GIN(search_vector);
-- JSONB queries (for nested data like subscriptions, tags)
CREATE INDEX IF NOT EXISTS idx_devices_raw ON devices USING GIN(raw_data jsonb_path_ops);
-- Subscription-specific index (for "expiring subscriptions" queries)
CREATE INDEX IF NOT EXISTS idx_devices_subscriptions ON devices USING GIN((raw_data->'subscription'));
-- Tags index
CREATE INDEX IF NOT EXISTS idx_devices_tags ON devices USING GIN((raw_data->'tags'));
-- ============================================
-- VIEWS: Pre-built queries for common needs
-- ============================================
-- Active devices only (excludes archived)
CREATE OR REPLACE VIEW active_devices AS
SELECT id,
    serial_number,
    mac_address,
    device_type,
    model,
    region,
    device_name,
    assigned_state,
    updated_at,
    raw_data->'subscription' as subscriptions,
    raw_data->'tags' as tags
FROM devices
WHERE NOT archived;
-- Devices with expiring subscriptions (next 90 days)
CREATE OR REPLACE VIEW devices_expiring_soon AS
SELECT d.id,
    d.serial_number,
    d.device_type,
    d.model,
    d.region,
    sub->>'key' as subscription_key,
    (sub->>'endTime')::timestamptz as subscription_end,
    (sub->>'endTime')::timestamptz - NOW() as time_remaining
FROM devices d,
    jsonb_array_elements(d.raw_data->'subscription') as sub
WHERE NOT d.archived
    AND (sub->>'endTime')::timestamptz < NOW() + INTERVAL '90 days'
    AND (sub->>'endTime')::timestamptz > NOW()
ORDER BY subscription_end ASC;
-- Device type summary
CREATE OR REPLACE VIEW device_summary AS
SELECT device_type,
    region,
    COUNT(*) as total,
    COUNT(*) FILTER (
        WHERE assigned_state = 'ASSIGNED_TO_SERVICE'
    ) as assigned,
    COUNT(*) FILTER (
        WHERE assigned_state = 'UNASSIGNED'
    ) as unassigned,
    COUNT(*) FILTER (
        WHERE archived
    ) as archived
FROM devices
GROUP BY device_type,
    region
ORDER BY device_type,
    region;
-- ============================================
-- FUNCTIONS: Useful queries as functions
-- ============================================
-- Search devices with ranking
CREATE OR REPLACE FUNCTION search_devices(
        search_query TEXT,
        max_results INTEGER DEFAULT 50
    ) RETURNS TABLE (
        id UUID,
        serial_number VARCHAR,
        device_name VARCHAR,
        device_type VARCHAR,
        model VARCHAR,
        region VARCHAR,
        rank REAL
    ) AS $$ BEGIN RETURN QUERY
SELECT d.id,
    d.serial_number,
    d.device_name,
    d.device_type,
    d.model,
    d.region,
    ts_rank(
        d.search_vector,
        websearch_to_tsquery('english', search_query)
    ) as rank
FROM devices d
WHERE d.search_vector @@ websearch_to_tsquery('english', search_query)
    AND NOT d.archived
ORDER BY rank DESC
LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
-- Get devices by tag
CREATE OR REPLACE FUNCTION get_devices_by_tag(
        tag_key TEXT,
        tag_value TEXT DEFAULT NULL
    ) RETURNS SETOF devices AS $$ BEGIN IF tag_value IS NULL THEN -- Just check if tag key exists
    RETURN QUERY
SELECT *
FROM devices
WHERE raw_data->'tags' ? tag_key
    AND NOT archived;
ELSE -- Check key and value
RETURN QUERY
SELECT *
FROM devices
WHERE raw_data->'tags'->>tag_key = tag_value
    AND NOT archived;
END IF;
END;
$$ LANGUAGE plpgsql;
-- ============================================
-- SYNC TRACKING TABLE (optional)
-- ============================================
CREATE TABLE IF NOT EXISTS sync_history (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running',
    -- running, completed, failed
    devices_fetched INTEGER,
    devices_inserted INTEGER,
    devices_updated INTEGER,
    devices_errors INTEGER,
    error_message TEXT
);
-- ============================================
-- SAMPLE QUERIES (for reference)
-- ============================================
-- These are examples you can run after data is loaded:
-- 1. Paginated list of switches
-- SELECT id, serial_number, model, region, device_name, updated_at
-- FROM devices
-- WHERE device_type = 'SWITCH' AND NOT archived
-- ORDER BY updated_at DESC
-- LIMIT 50 OFFSET 0;
-- 2. Full-text search
-- SELECT * FROM search_devices('aruba 6200');
-- 3. Devices with specific tag
-- SELECT * FROM get_devices_by_tag('MCOCY');
-- 4. Devices with subscriptions expiring soon
-- SELECT * FROM devices_expiring_soon;
-- 5. Count by type and region
-- SELECT * FROM device_summary;
-- 6. Find device by MAC address
-- SELECT * FROM devices WHERE mac_address = '5C:A4:7D:6D:25:C0';
-- 7. Devices updated in last 24 hours
-- SELECT * FROM devices 
-- WHERE updated_at > NOW() - INTERVAL '24 hours'
-- ORDER BY updated_at DESC;
-- 8. JSONB query: devices in specific subscription tier
-- SELECT id, serial_number, device_type
-- FROM devices
-- WHERE raw_data @> '{"subscription": [{"tier": "FOUNDATION_SWITCH_6200"}]}';