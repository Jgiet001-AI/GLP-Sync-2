-- HPE GreenLake Device Inventory Schema
-- PostgreSQL 16+
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
    
    -- NEW: Additional fields from API schema
    resource_type VARCHAR(50),              -- e.g., "devices/device"
    tenant_workspace_id UUID,               -- MSP tenant workspace
    
    -- Application reference
    application_id UUID,
    application_resource_uri VARCHAR(255),
    
    -- Dedicated platform workspace
    dedicated_platform_id UUID,
    
    -- Location (flattened for fast queries)
    location_id UUID,
    location_name VARCHAR(255),
    location_city VARCHAR(100),
    location_state VARCHAR(100),
    location_country VARCHAR(100),
    location_postal_code VARCHAR(20),
    location_street_address VARCHAR(255),
    location_latitude DOUBLE PRECISION,
    location_longitude DOUBLE PRECISION,
    location_source VARCHAR(50),
    
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
        ) || setweight(
            to_tsvector('english', coalesce(location_city, '')),
            'C'
        ) || setweight(
            to_tsvector('english', coalesce(location_country, '')),
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
-- New indexes for added columns
CREATE INDEX IF NOT EXISTS idx_devices_application ON devices(application_id);
CREATE INDEX IF NOT EXISTS idx_devices_location ON devices(location_id);
CREATE INDEX IF NOT EXISTS idx_devices_location_country ON devices(location_country);
CREATE INDEX IF NOT EXISTS idx_devices_location_city ON devices(location_city);
CREATE INDEX IF NOT EXISTS idx_devices_tenant ON devices(tenant_workspace_id);
CREATE INDEX IF NOT EXISTS idx_devices_dedicated_platform ON devices(dedicated_platform_id);
-- ============================================
-- SUBSCRIPTION TABLE: Normalized from API array
-- ============================================
CREATE TABLE IF NOT EXISTS device_subscriptions (
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    subscription_id UUID NOT NULL,
    resource_uri VARCHAR(255),
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (device_id, subscription_id)
);
CREATE INDEX IF NOT EXISTS idx_device_subscriptions_sub ON device_subscriptions(subscription_id);

-- Foreign key to subscriptions table (requires subscriptions_schema.sql to be loaded first)
-- Before adding this constraint, clean orphaned records:
--   DELETE FROM device_subscriptions ds
--   WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.id = ds.subscription_id);
-- Then add constraint:
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_device_subscriptions_sub'
    ) THEN
        ALTER TABLE device_subscriptions
        ADD CONSTRAINT fk_device_subscriptions_sub
        FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE;
    END IF;
EXCEPTION
    WHEN undefined_table THEN
        -- subscriptions table doesn't exist yet, skip constraint
        NULL;
    WHEN foreign_key_violation THEN
        -- orphaned records exist, skip constraint (clean them first)
        RAISE NOTICE 'Orphaned subscription_id records exist. Run cleanup before adding FK constraint.';
END;
$$;

-- ============================================
-- TAGS TABLE: Normalized from API key-value object
-- ============================================
CREATE TABLE IF NOT EXISTS device_tags (
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    tag_key VARCHAR(100) NOT NULL,
    tag_value VARCHAR(255),
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (device_id, tag_key)
);
CREATE INDEX IF NOT EXISTS idx_device_tags_key ON device_tags(tag_key);
CREATE INDEX IF NOT EXISTS idx_device_tags_key_value ON device_tags(tag_key, tag_value);
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
-- NOTE: Uses LATERAL join to safely handle devices with null/missing subscription arrays
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
    AND jsonb_typeof(d.raw_data->'subscription') = 'array'
    AND (sub->>'endTime')::timestamptz < NOW() + INTERVAL '90 days'
    AND (sub->>'endTime')::timestamptz > NOW()
ORDER BY subscription_end ASC;
-- Devices with full subscription details (joins devices + subscriptions tables)
CREATE OR REPLACE VIEW devices_with_subscriptions AS
SELECT
    -- Device fields
    d.id as device_id,
    d.serial_number,
    d.mac_address,
    d.device_type,
    d.model,
    d.region,
    d.device_name,
    d.assigned_state,
    d.archived,
    d.location_name,
    d.location_city,
    d.location_country,
    d.updated_at as device_updated_at,

    -- Subscription fields (from subscriptions table)
    s.id as subscription_id,
    s.key as subscription_key,
    s.subscription_type,
    s.subscription_status,
    s.quantity,
    s.available_quantity,
    s.start_time as subscription_start,
    s.end_time as subscription_end,
    s.tier,
    s.tier_description,
    s.sku,
    s.is_eval,

    -- Computed fields
    s.end_time - NOW() as time_remaining,
    DATE_PART('day', s.end_time - NOW()) as days_remaining

FROM devices d
LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
LEFT JOIN subscriptions s ON ds.subscription_id = s.id
WHERE NOT d.archived;

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
-- TABLE & COLUMN COMMENTS (for LLM understanding)
-- ============================================
COMMENT ON TABLE devices IS 'HPE GreenLake network devices (APs, switches, gateways). Primary key is device UUID (id). Each device has a serial_number and may be linked to subscriptions via device_subscriptions table.';
COMMENT ON TABLE device_subscriptions IS 'Many-to-many link between devices and subscriptions. Join devices.id to device_id, and subscriptions.id to subscription_id. To get subscription key for a device, join through this table to subscriptions.';
COMMENT ON TABLE device_tags IS 'Key-value tags attached to devices for categorization and filtering. Join on device_id to devices.id.';
COMMENT ON TABLE sync_history IS 'Tracks sync operations from GreenLake API. Shows when data was last updated and sync statistics.';

-- Device column comments
COMMENT ON COLUMN devices.id IS 'Device UUID - unique identifier for this specific device from GreenLake API. Use this to join with device_subscriptions.device_id';
COMMENT ON COLUMN devices.serial_number IS 'Unique device serial number (e.g., VNT9KWC01V). Human-readable device identifier';
COMMENT ON COLUMN devices.mac_address IS 'Device MAC address in format XX:XX:XX:XX:XX:XX';
COMMENT ON COLUMN devices.device_type IS 'Device category: IAP (access point), SWITCH, GATEWAY, AP';
COMMENT ON COLUMN devices.model IS 'Hardware model name (e.g., AP-565-US, 6200F-24G-4SFP+)';
COMMENT ON COLUMN devices.region IS 'Geographic region: us-west, us-east, eu-central, etc.';
COMMENT ON COLUMN devices.archived IS 'True if device is decommissioned/archived';
COMMENT ON COLUMN devices.assigned_state IS 'Assignment status: ASSIGNED_TO_SERVICE or UNASSIGNED';
COMMENT ON COLUMN devices.location_city IS 'City where device is located';
COMMENT ON COLUMN devices.location_country IS 'Country where device is located';
COMMENT ON COLUMN devices.raw_data IS 'Full JSON response from GreenLake API for advanced queries';

-- Device-Subscription relationship column comments
COMMENT ON COLUMN device_subscriptions.device_id IS 'Device UUID - references devices.id';
COMMENT ON COLUMN device_subscriptions.subscription_id IS 'Subscription UUID - references subscriptions.id. To get subscription key, join with subscriptions table';

-- ============================================
-- LLM HELPER VIEWS
-- ============================================
-- Schema documentation view - LLM can query this to understand the schema
CREATE OR REPLACE VIEW schema_info AS
SELECT
    t.table_name,
    obj_description((quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass) as table_description,
    c.column_name,
    c.data_type,
    c.is_nullable,
    col_description((quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass, c.ordinal_position) as column_description
FROM information_schema.tables t
JOIN information_schema.columns c ON t.table_name = c.table_name AND t.table_schema = c.table_schema
WHERE t.table_schema = 'public'
  AND t.table_type = 'BASE TABLE'
ORDER BY t.table_name, c.ordinal_position;

-- Valid values view - shows all valid values for categorical columns
CREATE OR REPLACE VIEW valid_column_values AS
SELECT 'devices' as table_name, 'device_type' as column_name, device_type as valid_value, COUNT(*) as occurrence_count
FROM devices WHERE device_type IS NOT NULL GROUP BY device_type
UNION ALL
SELECT 'devices', 'assigned_state', assigned_state, COUNT(*) FROM devices WHERE assigned_state IS NOT NULL GROUP BY assigned_state
UNION ALL
SELECT 'devices', 'region', region, COUNT(*) FROM devices WHERE region IS NOT NULL GROUP BY region
UNION ALL
SELECT 'subscriptions', 'subscription_type', subscription_type, COUNT(*) FROM subscriptions WHERE subscription_type IS NOT NULL GROUP BY subscription_type
UNION ALL
SELECT 'subscriptions', 'subscription_status', subscription_status, COUNT(*) FROM subscriptions WHERE subscription_status IS NOT NULL GROUP BY subscription_status
UNION ALL
SELECT 'subscriptions', 'tier', tier, COUNT(*) FROM subscriptions WHERE tier IS NOT NULL GROUP BY tier
UNION ALL
SELECT 'subscriptions', 'product_type', product_type, COUNT(*) FROM subscriptions WHERE product_type IS NOT NULL GROUP BY product_type
ORDER BY table_name, column_name, occurrence_count DESC;

-- ============================================
-- EXAMPLE QUERIES TABLE (for LLM learning)
-- ============================================
CREATE TABLE IF NOT EXISTS query_examples (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50),
    description TEXT NOT NULL,
    sql_query TEXT NOT NULL
);

-- Insert example queries (only if table is empty)
INSERT INTO query_examples (category, description, sql_query)
SELECT * FROM (VALUES
    ('search', 'Find device by serial number', 'SELECT * FROM devices WHERE serial_number = ''YOUR_SERIAL'';'),
    ('search', 'Find device by MAC address', 'SELECT * FROM devices WHERE mac_address = ''XX:XX:XX:XX:XX:XX'';'),
    ('search', 'Full-text search devices', 'SELECT * FROM search_devices(''aruba 6200'');'),
    ('filter', 'List all switches', 'SELECT serial_number, model, region FROM devices WHERE device_type = ''SWITCH'' AND NOT archived;'),
    ('filter', 'List all access points', 'SELECT serial_number, model, region FROM devices WHERE device_type = ''IAP'' AND NOT archived;'),
    ('filter', 'Devices in a specific region', 'SELECT * FROM devices WHERE region = ''us-west'' AND NOT archived;'),
    ('expiring', 'Subscriptions expiring in 30 days', 'SELECT * FROM subscriptions_expiring_soon WHERE days_remaining < 30;'),
    ('expiring', 'Devices with expiring subscriptions', 'SELECT * FROM devices_expiring_soon;'),
    ('summary', 'Count devices by type', 'SELECT device_type, COUNT(*) FROM devices WHERE NOT archived GROUP BY device_type;'),
    ('summary', 'Subscription utilization', 'SELECT subscription_type, SUM(quantity) as total, SUM(available_quantity) as available FROM subscriptions WHERE subscription_status = ''STARTED'' GROUP BY subscription_type;'),
    ('join', 'Device with subscription details', 'SELECT * FROM devices_with_subscriptions WHERE serial_number = ''YOUR_SERIAL'';'),
    ('join', 'Get subscription key for a device', 'SELECT d.serial_number, s.key as subscription_key, s.subscription_type FROM devices d JOIN device_subscriptions ds ON d.id = ds.device_id JOIN subscriptions s ON ds.subscription_id = s.id WHERE d.serial_number = ''YOUR_SERIAL'';'),
    ('tags', 'Find devices by tag', 'SELECT * FROM get_devices_by_tag(''tag_key'', ''tag_value'');')
) AS v(category, description, sql_query)
WHERE NOT EXISTS (SELECT 1 FROM query_examples LIMIT 1);

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