-- Migration: Add all missing Aruba Central fields
-- These columns enrich GreenLake device records with Central monitoring data

-- Add missing Central columns
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_model TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_part_number TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_ipv6 TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_uptime_millis BIGINT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_last_seen_at TIMESTAMPTZ;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_building_id UUID;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_floor_id UUID;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_config_status TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_config_last_modified_at TIMESTAMPTZ;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS central_cluster_name TEXT;

-- Add comments for documentation
COMMENT ON COLUMN devices.central_model IS 'Hardware model from Aruba Central (e.g., 635)';
COMMENT ON COLUMN devices.central_part_number IS 'Part number from Aruba Central (e.g., R7J28A)';
COMMENT ON COLUMN devices.central_ipv6 IS 'IPv6 address from Aruba Central';
COMMENT ON COLUMN devices.central_uptime_millis IS 'Device uptime in milliseconds from Aruba Central';
COMMENT ON COLUMN devices.central_last_seen_at IS 'Last time device was seen online in Aruba Central';
COMMENT ON COLUMN devices.central_building_id IS 'Building UUID from Aruba Central location';
COMMENT ON COLUMN devices.central_floor_id IS 'Floor UUID from Aruba Central location';
COMMENT ON COLUMN devices.central_config_status IS 'Configuration sync status from Aruba Central';
COMMENT ON COLUMN devices.central_config_last_modified_at IS 'Last config modification time from Aruba Central';
COMMENT ON COLUMN devices.central_cluster_name IS 'Cluster/stack name from Aruba Central';

-- Create indexes for commonly queried fields
CREATE INDEX IF NOT EXISTS idx_devices_central_model ON devices(central_model) WHERE central_model IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_devices_central_last_seen ON devices(central_last_seen_at DESC NULLS LAST) WHERE central_last_seen_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_devices_central_config_status ON devices(central_config_status) WHERE central_config_status IS NOT NULL;
