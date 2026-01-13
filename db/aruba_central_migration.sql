-- ============================================
-- Aruba Central Integration Migration
-- PostgreSQL 16+
-- ============================================
--
-- This migration adds support for Aruba Central device data alongside
-- existing GreenLake device data. The schema is designed to:
--
-- 1. Keep GreenLake data in existing columns (no changes)
-- 2. Add Central-specific columns with 'central_' prefix
-- 3. Track which platform(s) each device exists on
-- 4. Support correlation by serial_number
--
-- Run this migration after the base schema is in place.
-- ============================================

-- ============================================
-- ARUBA CENTRAL DEVICE COLUMNS
-- These columns store data from Aruba Central API
-- ============================================

-- Central's unique identifier for the device
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_id TEXT;

-- Device name as seen in Central (may differ from GLP device_name)
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_device_name TEXT;

-- Device type in Central format: ACCESS_POINT, SWITCH, GATEWAY
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_device_type TEXT;

-- Status in Central: ONLINE, OFFLINE
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_status TEXT;

-- Software/firmware version running on device (from Central)
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_software_version TEXT;

-- IPv4 address as reported by Central
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_ipv4 TEXT;

-- Deployment mode (e.g., Standalone, Virtual Controller)
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_deployment TEXT;

-- Role in network topology
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_device_role TEXT;

-- Device function/persona (e.g., Campus AP, Access Switch)
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_device_function TEXT;

-- Whether the device is provisioned in Central
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_is_provisioned BOOLEAN;

-- Site information from Central
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_site_id TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_site_name TEXT;

-- Device group information from Central
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_device_group_id TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_device_group_name TEXT;

-- Scope and stack identifiers
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_scope_id TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_stack_id TEXT;

-- License tier from Central
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_tier TEXT;

-- Full API response from Central (for advanced queries)
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_raw_data JSONB;


-- ============================================
-- SOURCE TRACKING COLUMNS
-- Track which platform(s) each device exists on
-- ============================================

-- Boolean flags for platform presence
ALTER TABLE devices ADD COLUMN IF NOT EXISTS in_greenlake BOOLEAN DEFAULT TRUE;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS in_central BOOLEAN DEFAULT FALSE;

-- Timestamps for last sync from each platform
ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_seen_greenlake TIMESTAMPTZ;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_seen_central TIMESTAMPTZ;


-- ============================================
-- INDEXES
-- Using partial indexes for better selectivity (per Codex review)
-- ============================================

-- Central ID lookup (sparse - only devices in Central)
CREATE INDEX IF NOT EXISTS idx_devices_central_id
    ON devices(central_id)
    WHERE central_id IS NOT NULL;

-- Central status for monitoring (only online/offline devices)
CREATE INDEX IF NOT EXISTS idx_devices_central_status
    ON devices(central_status)
    WHERE central_status IS NOT NULL;

-- Central site lookup (sparse)
CREATE INDEX IF NOT EXISTS idx_devices_central_site_id
    ON devices(central_site_id)
    WHERE central_site_id IS NOT NULL;

-- Devices in Central only (partial index for high selectivity)
CREATE INDEX IF NOT EXISTS idx_devices_central_only
    ON devices(serial_number)
    WHERE in_central = TRUE AND (in_greenlake IS NULL OR in_greenlake = FALSE);

-- Devices in GreenLake only (partial index for high selectivity)
CREATE INDEX IF NOT EXISTS idx_devices_greenlake_only
    ON devices(serial_number)
    WHERE in_greenlake = TRUE AND (in_central IS NULL OR in_central = FALSE);

-- Devices in both platforms (partial index)
CREATE INDEX IF NOT EXISTS idx_devices_both_platforms
    ON devices(serial_number)
    WHERE in_greenlake = TRUE AND in_central = TRUE;

-- Last seen timestamps (for stale detection)
CREATE INDEX IF NOT EXISTS idx_devices_last_seen_central
    ON devices(last_seen_central)
    WHERE in_central = TRUE;


-- ============================================
-- CONSTRAINTS
-- Ensure serial_number is unique for correlation
-- ============================================

-- Serial number should be unique (correlation key)
-- Note: This creates the index if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_devices_serial_number'
    ) THEN
        ALTER TABLE devices ADD CONSTRAINT uq_devices_serial_number
            UNIQUE (serial_number);
    END IF;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END;
$$;


-- ============================================
-- VIEWS FOR CROSS-PLATFORM ANALYSIS
-- ============================================

-- View showing all devices with platform presence info
CREATE OR REPLACE VIEW devices_cross_platform AS
SELECT
    -- Identifiers
    id AS greenlake_id,
    central_id,
    serial_number,
    mac_address,

    -- Names from both platforms
    device_name AS greenlake_device_name,
    central_device_name,
    COALESCE(device_name, central_device_name) AS display_name,

    -- Device classification
    device_type AS greenlake_device_type,
    central_device_type,
    model,

    -- Location info
    region AS greenlake_region,
    central_site_name,
    location_name,
    location_city,
    location_country,

    -- Status
    central_status,
    central_software_version,
    central_ipv4,

    -- Platform presence
    in_greenlake,
    in_central,
    last_seen_greenlake,
    last_seen_central,

    -- Computed platform status
    CASE
        WHEN in_greenlake = TRUE AND in_central = TRUE THEN 'BOTH'
        WHEN in_greenlake = TRUE THEN 'GREENLAKE_ONLY'
        WHEN in_central = TRUE THEN 'CENTRAL_ONLY'
        ELSE 'UNKNOWN'
    END AS platform_presence,

    -- Sync freshness
    CASE
        WHEN last_seen_greenlake IS NULL THEN NULL
        ELSE NOW() - last_seen_greenlake
    END AS greenlake_sync_age,
    CASE
        WHEN last_seen_central IS NULL THEN NULL
        ELSE NOW() - last_seen_central
    END AS central_sync_age,

    -- Subscription info (from GreenLake)
    assigned_state,
    archived

FROM devices
WHERE NOT archived;


-- View for devices in Central with online/offline status
CREATE OR REPLACE VIEW central_devices_status AS
SELECT
    serial_number,
    COALESCE(central_device_name, device_name) AS device_name,
    central_device_type,
    model,
    central_status,
    central_software_version,
    central_ipv4,
    central_site_name,
    central_device_group_name,
    central_is_provisioned,
    last_seen_central,
    in_greenlake
FROM devices
WHERE in_central = TRUE AND NOT archived
ORDER BY central_status, serial_number;


-- View for devices only in one platform (potential sync issues)
CREATE OR REPLACE VIEW devices_platform_mismatch AS
SELECT
    serial_number,
    COALESCE(device_name, central_device_name) AS device_name,
    model,
    CASE
        WHEN in_greenlake = TRUE AND (in_central IS NULL OR in_central = FALSE)
        THEN 'GREENLAKE_ONLY'
        WHEN in_central = TRUE AND (in_greenlake IS NULL OR in_greenlake = FALSE)
        THEN 'CENTRAL_ONLY'
    END AS platform,
    last_seen_greenlake,
    last_seen_central,
    device_type AS greenlake_device_type,
    central_device_type
FROM devices
WHERE NOT archived
  AND (
    (in_greenlake = TRUE AND (in_central IS NULL OR in_central = FALSE))
    OR (in_central = TRUE AND (in_greenlake IS NULL OR in_greenlake = FALSE))
  )
ORDER BY platform, serial_number;


-- Summary view for platform coverage
CREATE OR REPLACE VIEW platform_coverage_summary AS
SELECT
    device_type,
    COUNT(*) AS total_devices,
    COUNT(*) FILTER (WHERE in_greenlake = TRUE AND in_central = TRUE) AS in_both,
    COUNT(*) FILTER (WHERE in_greenlake = TRUE AND (in_central IS NULL OR in_central = FALSE)) AS greenlake_only,
    COUNT(*) FILTER (WHERE in_central = TRUE AND (in_greenlake IS NULL OR in_greenlake = FALSE)) AS central_only,
    COUNT(*) FILTER (WHERE in_central = TRUE AND central_status = 'ONLINE') AS central_online,
    COUNT(*) FILTER (WHERE in_central = TRUE AND central_status = 'OFFLINE') AS central_offline
FROM devices
WHERE NOT archived
GROUP BY device_type
ORDER BY device_type;


-- ============================================
-- FUNCTIONS
-- ============================================

-- Function to mark devices as no longer in Central (for reconciliation)
CREATE OR REPLACE FUNCTION mark_devices_removed_from_central(
    serials_still_present TEXT[]
) RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE devices
    SET
        in_central = FALSE
    WHERE
        in_central = TRUE
        AND serial_number IS NOT NULL
        AND serial_number != ''
        AND serial_number != ALL(serials_still_present);

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;


-- Function to get devices by Central site
CREATE OR REPLACE FUNCTION get_devices_by_central_site(
    p_site_id TEXT
) RETURNS SETOF devices AS $$
BEGIN
    RETURN QUERY
    SELECT *
    FROM devices
    WHERE central_site_id = p_site_id
      AND NOT archived;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- TABLE COMMENTS
-- ============================================

-- New column comments
COMMENT ON COLUMN devices.central_id IS 'Aruba Central unique device identifier. Different from GreenLake id.';
COMMENT ON COLUMN devices.central_device_name IS 'Device name as shown in Aruba Central. May differ from GreenLake device_name.';
COMMENT ON COLUMN devices.central_device_type IS 'Device type in Central format: ACCESS_POINT, SWITCH, GATEWAY';
COMMENT ON COLUMN devices.central_status IS 'Real-time status from Central: ONLINE or OFFLINE';
COMMENT ON COLUMN devices.central_software_version IS 'Firmware/software version running on device (from Central)';
COMMENT ON COLUMN devices.central_ipv4 IS 'IPv4 address as reported by Aruba Central';
COMMENT ON COLUMN devices.central_site_id IS 'Site ID where device is located in Central';
COMMENT ON COLUMN devices.central_site_name IS 'Site name where device is located in Central';
COMMENT ON COLUMN devices.in_greenlake IS 'TRUE if device exists in GreenLake inventory';
COMMENT ON COLUMN devices.in_central IS 'TRUE if device exists in Aruba Central inventory';
COMMENT ON COLUMN devices.last_seen_greenlake IS 'Timestamp when device was last synced from GreenLake';
COMMENT ON COLUMN devices.last_seen_central IS 'Timestamp when device was last synced from Aruba Central';
COMMENT ON COLUMN devices.central_raw_data IS 'Full JSON response from Aruba Central API for this device';

-- View comments
COMMENT ON VIEW devices_cross_platform IS 'Unified view of devices showing data from both GreenLake and Aruba Central platforms';
COMMENT ON VIEW central_devices_status IS 'View of devices in Aruba Central with online/offline status';
COMMENT ON VIEW devices_platform_mismatch IS 'Devices that exist in only one platform - useful for identifying sync issues';
COMMENT ON VIEW platform_coverage_summary IS 'Summary statistics of device presence across platforms';


-- ============================================
-- UPDATE sync_history FOR CENTRAL
-- ============================================

-- Extend resource_type check constraint if needed
-- Note: Must include agent migration markers used by migrations 004 and 006
DO $$
BEGIN
    ALTER TABLE sync_history DROP CONSTRAINT IF EXISTS sync_history_resource_type_check;
    ALTER TABLE sync_history ADD CONSTRAINT sync_history_resource_type_check
        CHECK (resource_type IN ('devices', 'subscriptions', 'all', 'central_devices',
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
-- 1. Existing GreenLake devices will have in_greenlake = TRUE (default)
-- 2. in_central will be FALSE until Central sync runs
-- 3. Use the ArubaCentralSyncer to populate Central columns
--
-- To verify: SELECT * FROM platform_coverage_summary;
-- ============================================
