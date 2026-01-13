-- ============================================
-- Aruba Central Clients & Firmware Migration
-- PostgreSQL 16+
-- ============================================
--
-- This migration adds support for:
-- 1. Network clients (devices connected to network equipment)
-- 2. Site organization for clients
-- 3. Firmware details enrichment for devices
--
-- Run this migration after the base schema and aruba_central_migration.sql
-- ============================================

-- ============================================
-- SITES TABLE
-- Represents physical locations where network devices are deployed
-- ============================================

CREATE TABLE IF NOT EXISTS sites (
    site_id TEXT PRIMARY KEY,
    site_name TEXT,

    -- Timestamps
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for listing/searching sites
CREATE INDEX IF NOT EXISTS idx_sites_name ON sites(site_name);
CREATE INDEX IF NOT EXISTS idx_sites_last_synced ON sites(last_synced_at DESC);

COMMENT ON TABLE sites IS 'Physical locations/sites from Aruba Central where network devices are deployed';
COMMENT ON COLUMN sites.site_id IS 'Unique site identifier from Aruba Central';
COMMENT ON COLUMN sites.site_name IS 'Human-readable site name';


-- ============================================
-- CLIENTS TABLE
-- Network clients (WiFi/Wired devices) connected to network equipment
-- ============================================

CREATE TABLE IF NOT EXISTS clients (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Site relationship
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,

    -- Client identifiers - using MACADDR for normalized storage
    mac MACADDR NOT NULL,
    name TEXT,

    -- Health & Status with CHECK constraints
    health TEXT CHECK (health IS NULL OR health IN ('Good', 'Fair', 'Poor', 'Unknown')),
    status TEXT CHECK (status IS NULL OR status IN (
        'Connected', 'Failed', 'Connecting', 'Disconnected',
        'Blocked', 'Unknown', 'REMOVED'
    )),
    status_reason TEXT,

    -- Client type
    type TEXT CHECK (type IS NULL OR type IN ('Wired', 'Wireless')),

    -- Network information - using INET for IP addresses
    ipv4 INET,
    ipv6 INET,
    network TEXT,
    vlan_id TEXT,
    port TEXT,
    role TEXT,

    -- Connected device info (links to devices table)
    connected_device_serial TEXT,
    connected_to TEXT,
    connected_since TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,

    -- Tunnel information
    tunnel TEXT CHECK (tunnel IS NULL OR tunnel IN ('Port-based', 'User-based', 'Overlay')),
    tunnel_id INTEGER,

    -- Security information
    key_management TEXT,
    authentication TEXT,
    capabilities TEXT,

    -- Full API response for advanced queries
    raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    synced_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint per site
    UNIQUE(site_id, mac)
);

-- ============================================
-- CLIENTS INDEXES
-- Optimized for common query patterns
-- ============================================

-- Primary lookup: clients by site (for site detail view)
CREATE INDEX IF NOT EXISTS idx_clients_site_id ON clients(site_id);

-- MAC address lookup (for search)
CREATE INDEX IF NOT EXISTS idx_clients_mac ON clients(mac);

-- Status filtering (partial index excludes removed clients)
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status)
    WHERE status IS NOT NULL AND status != 'REMOVED';

-- Health filtering
CREATE INDEX IF NOT EXISTS idx_clients_health ON clients(health)
    WHERE health IS NOT NULL;

-- Type filtering (Wired/Wireless)
CREATE INDEX IF NOT EXISTS idx_clients_type ON clients(type)
    WHERE type IS NOT NULL;

-- Connected device lookup (join to devices table)
CREATE INDEX IF NOT EXISTS idx_clients_connected_device ON clients(connected_device_serial)
    WHERE connected_device_serial IS NOT NULL;

-- Time-based queries (recent clients, cleanup)
CREATE INDEX IF NOT EXISTS idx_clients_last_seen ON clients(last_seen_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_clients_synced_at ON clients(synced_at);

-- Composite index for common filtered listing
CREATE INDEX IF NOT EXISTS idx_clients_site_status_health
    ON clients(site_id, status, health) WHERE status != 'REMOVED';

-- Full-text search on client name
CREATE INDEX IF NOT EXISTS idx_clients_name_trgm ON clients USING gin(name gin_trgm_ops)
    WHERE name IS NOT NULL;

-- JSONB index for advanced queries
CREATE INDEX IF NOT EXISTS idx_clients_raw_data ON clients USING gin(raw_data jsonb_path_ops);


-- ============================================
-- FIRMWARE COLUMNS FOR DEVICES TABLE
-- Enriches existing devices with firmware information
-- ============================================

ALTER TABLE devices ADD COLUMN IF NOT EXISTS firmware_version TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS firmware_recommended_version TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS firmware_upgrade_status TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS firmware_classification TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS firmware_last_upgraded_at TIMESTAMPTZ;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS firmware_synced_at TIMESTAMPTZ;

-- Index for firmware status queries
CREATE INDEX IF NOT EXISTS idx_devices_firmware_status ON devices(firmware_upgrade_status)
    WHERE firmware_upgrade_status IS NOT NULL;

-- Index for stale firmware detection
CREATE INDEX IF NOT EXISTS idx_devices_firmware_synced ON devices(firmware_synced_at)
    WHERE firmware_synced_at IS NOT NULL;


-- ============================================
-- VIEWS FOR CLIENTS
-- ============================================

-- Active clients (excludes removed)
CREATE OR REPLACE VIEW active_clients AS
SELECT
    c.*,
    s.site_name
FROM clients c
JOIN sites s ON c.site_id = s.site_id
WHERE c.status IS NULL OR c.status != 'REMOVED';

-- Site summary with dynamic counts (no denormalized columns)
CREATE OR REPLACE VIEW sites_with_stats AS
SELECT
    s.site_id,
    s.site_name,
    s.last_synced_at,
    s.created_at,
    s.updated_at,
    COALESCE(client_stats.total_clients, 0) AS client_count,
    COALESCE(client_stats.connected_clients, 0) AS connected_count,
    COALESCE(client_stats.wired_clients, 0) AS wired_count,
    COALESCE(client_stats.wireless_clients, 0) AS wireless_count,
    COALESCE(client_stats.good_health, 0) AS good_health_count,
    COALESCE(client_stats.fair_health, 0) AS fair_health_count,
    COALESCE(client_stats.poor_health, 0) AS poor_health_count,
    COALESCE(device_stats.device_count, 0) AS device_count
FROM sites s
LEFT JOIN (
    SELECT
        site_id,
        COUNT(*) AS total_clients,
        COUNT(*) FILTER (WHERE status = 'Connected') AS connected_clients,
        COUNT(*) FILTER (WHERE type = 'Wired') AS wired_clients,
        COUNT(*) FILTER (WHERE type = 'Wireless') AS wireless_clients,
        COUNT(*) FILTER (WHERE health = 'Good') AS good_health,
        COUNT(*) FILTER (WHERE health = 'Fair') AS fair_health,
        COUNT(*) FILTER (WHERE health = 'Poor') AS poor_health
    FROM clients
    WHERE status IS NULL OR status != 'REMOVED'
    GROUP BY site_id
) client_stats ON s.site_id = client_stats.site_id
LEFT JOIN (
    SELECT
        central_site_id AS site_id,
        COUNT(*) AS device_count
    FROM devices
    WHERE central_site_id IS NOT NULL AND NOT archived
    GROUP BY central_site_id
) device_stats ON s.site_id = device_stats.site_id;

-- Clients health summary across all sites
CREATE OR REPLACE VIEW clients_health_summary AS
SELECT
    COUNT(*) AS total_clients,
    COUNT(*) FILTER (WHERE status = 'Connected') AS connected,
    COUNT(*) FILTER (WHERE status = 'Disconnected') AS disconnected,
    COUNT(*) FILTER (WHERE status = 'Failed') AS failed,
    COUNT(*) FILTER (WHERE status = 'Blocked') AS blocked,
    COUNT(*) FILTER (WHERE type = 'Wired') AS wired,
    COUNT(*) FILTER (WHERE type = 'Wireless') AS wireless,
    COUNT(*) FILTER (WHERE health = 'Good') AS health_good,
    COUNT(*) FILTER (WHERE health = 'Fair') AS health_fair,
    COUNT(*) FILTER (WHERE health = 'Poor') AS health_poor,
    COUNT(*) FILTER (WHERE health = 'Unknown' OR health IS NULL) AS health_unknown
FROM clients
WHERE status IS NULL OR status != 'REMOVED';

-- Devices with firmware information
CREATE OR REPLACE VIEW devices_firmware_status AS
SELECT
    serial_number,
    COALESCE(central_device_name, device_name) AS device_name,
    COALESCE(central_device_type, device_type) AS device_type,
    model,
    central_site_name,
    firmware_version,
    firmware_recommended_version,
    firmware_upgrade_status,
    firmware_classification,
    firmware_last_upgraded_at,
    firmware_synced_at,
    CASE
        WHEN firmware_version = firmware_recommended_version THEN 'UP_TO_DATE'
        WHEN firmware_version IS NOT NULL AND firmware_recommended_version IS NOT NULL THEN 'UPDATE_AVAILABLE'
        ELSE 'UNKNOWN'
    END AS firmware_status
FROM devices
WHERE NOT archived AND firmware_version IS NOT NULL
ORDER BY firmware_upgrade_status, serial_number;


-- ============================================
-- FUNCTIONS
-- ============================================

-- Search clients by MAC or name
CREATE OR REPLACE FUNCTION search_clients(
    search_query TEXT,
    max_results INTEGER DEFAULT 50
) RETURNS TABLE (
    id BIGINT,
    site_id TEXT,
    site_name TEXT,
    mac MACADDR,
    name TEXT,
    health TEXT,
    status TEXT,
    type TEXT,
    ipv4 INET,
    connected_to TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.site_id,
        s.site_name,
        c.mac,
        c.name,
        c.health,
        c.status,
        c.type,
        c.ipv4,
        c.connected_to
    FROM clients c
    JOIN sites s ON c.site_id = s.site_id
    WHERE (c.status IS NULL OR c.status != 'REMOVED')
      AND (
          c.mac::TEXT ILIKE '%' || search_query || '%'
          OR c.name ILIKE '%' || search_query || '%'
          OR c.ipv4::TEXT LIKE '%' || search_query || '%'
      )
    ORDER BY
        CASE WHEN c.status = 'Connected' THEN 0 ELSE 1 END,
        c.last_seen_at DESC NULLS LAST
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Get clients by connected device serial
CREATE OR REPLACE FUNCTION get_clients_by_device(
    device_serial TEXT
) RETURNS SETOF clients AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM clients
    WHERE connected_device_serial = device_serial
      AND (status IS NULL OR status != 'REMOVED')
    ORDER BY last_seen_at DESC NULLS LAST;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- COLUMN COMMENTS
-- ============================================

COMMENT ON COLUMN clients.mac IS 'Client MAC address (normalized using MACADDR type)';
COMMENT ON COLUMN clients.health IS 'Client health status: Good, Fair, Poor, Unknown';
COMMENT ON COLUMN clients.status IS 'Connection status: Connected, Disconnected, Failed, Blocked, REMOVED';
COMMENT ON COLUMN clients.type IS 'Connection type: Wired or Wireless';
COMMENT ON COLUMN clients.ipv4 IS 'IPv4 address (stored as INET for validation)';
COMMENT ON COLUMN clients.ipv6 IS 'IPv6 address (stored as INET for validation)';
COMMENT ON COLUMN clients.connected_device_serial IS 'Serial number of the network device this client is connected to';
COMMENT ON COLUMN clients.connected_to IS 'Name of the device this client is connected to';
COMMENT ON COLUMN clients.tunnel IS 'Tunnel type: Port-based, User-based, Overlay';
COMMENT ON COLUMN clients.raw_data IS 'Full JSON response from Aruba Central API';

COMMENT ON COLUMN devices.firmware_version IS 'Current firmware version running on device';
COMMENT ON COLUMN devices.firmware_recommended_version IS 'Recommended firmware version from Aruba Central';
COMMENT ON COLUMN devices.firmware_upgrade_status IS 'Current upgrade status of the device';
COMMENT ON COLUMN devices.firmware_classification IS 'Classification of the firmware version';
COMMENT ON COLUMN devices.firmware_last_upgraded_at IS 'Timestamp of the last firmware upgrade';
COMMENT ON COLUMN devices.firmware_synced_at IS 'When firmware info was last synced from Aruba Central';


-- ============================================
-- UPDATE sync_history FOR CLIENTS
-- ============================================

-- Note: Must include agent migration markers used by migrations 004 and 006
DO $$
BEGIN
    ALTER TABLE sync_history DROP CONSTRAINT IF EXISTS sync_history_resource_type_check;
    ALTER TABLE sync_history ADD CONSTRAINT sync_history_resource_type_check
        CHECK (resource_type IN ('devices', 'subscriptions', 'all', 'central_devices', 'clients', 'firmware',
                                 'agent_migration_004', 'agent_migration_006_agentdb'));
EXCEPTION
    WHEN OTHERS THEN NULL;
END;
$$;


-- ============================================
-- MIGRATION COMPLETE
-- ============================================
--
-- After running this migration:
-- 1. Sites table is ready to receive site data
-- 2. Clients table is ready with proper MACADDR type
-- 3. Firmware columns added to devices table
-- 4. Views provide computed stats (no denormalization issues)
--
-- To verify: SELECT * FROM sites_with_stats;
-- ============================================
