-- Migration: Add missing device fields from API schema
-- Version: 001
-- Date: 2026-01-09
-- Description: Adds 13 new columns to devices table and creates 
--              device_subscriptions and device_tags tables

-- ============================================
-- STEP 1: Add new columns to devices table
-- ============================================
ALTER TABLE devices
ADD COLUMN IF NOT EXISTS resource_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS tenant_workspace_id UUID,
ADD COLUMN IF NOT EXISTS application_id UUID,
ADD COLUMN IF NOT EXISTS application_resource_uri VARCHAR(255),
ADD COLUMN IF NOT EXISTS dedicated_platform_id UUID,
ADD COLUMN IF NOT EXISTS location_id UUID,
ADD COLUMN IF NOT EXISTS location_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS location_city VARCHAR(100),
ADD COLUMN IF NOT EXISTS location_state VARCHAR(100),
ADD COLUMN IF NOT EXISTS location_country VARCHAR(100),
ADD COLUMN IF NOT EXISTS location_postal_code VARCHAR(20),
ADD COLUMN IF NOT EXISTS location_street_address VARCHAR(255),
ADD COLUMN IF NOT EXISTS location_latitude DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS location_longitude DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS location_source VARCHAR(50);

-- ============================================
-- STEP 2: Add new indexes
-- ============================================
CREATE INDEX IF NOT EXISTS idx_devices_application ON devices(application_id);
CREATE INDEX IF NOT EXISTS idx_devices_location ON devices(location_id);
CREATE INDEX IF NOT EXISTS idx_devices_location_country ON devices(location_country);
CREATE INDEX IF NOT EXISTS idx_devices_location_city ON devices(location_city);
CREATE INDEX IF NOT EXISTS idx_devices_tenant ON devices(tenant_workspace_id);
CREATE INDEX IF NOT EXISTS idx_devices_dedicated_platform ON devices(dedicated_platform_id);

-- ============================================
-- STEP 3: Create device_subscriptions table
-- ============================================
CREATE TABLE IF NOT EXISTS device_subscriptions (
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    subscription_id UUID NOT NULL,
    resource_uri VARCHAR(255),
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (device_id, subscription_id)
);
CREATE INDEX IF NOT EXISTS idx_device_subscriptions_sub ON device_subscriptions(subscription_id);

-- ============================================
-- STEP 4: Create device_tags table
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
-- STEP 5: Backfill existing data from raw_data JSONB
-- ============================================
UPDATE devices SET
    resource_type = raw_data->>'type',
    tenant_workspace_id = CASE 
        WHEN raw_data->>'tenantWorkspaceId' IS NOT NULL 
        THEN (raw_data->>'tenantWorkspaceId')::UUID 
        ELSE NULL 
    END,
    application_id = CASE 
        WHEN raw_data->'application'->>'id' IS NOT NULL 
        THEN (raw_data->'application'->>'id')::UUID 
        ELSE NULL 
    END,
    application_resource_uri = raw_data->'application'->>'resourceUri',
    dedicated_platform_id = CASE 
        WHEN raw_data->'dedicatedPlatformWorkspace'->>'id' IS NOT NULL 
        THEN (raw_data->'dedicatedPlatformWorkspace'->>'id')::UUID 
        ELSE NULL 
    END,
    location_id = CASE 
        WHEN raw_data->'location'->>'id' IS NOT NULL 
        THEN (raw_data->'location'->>'id')::UUID 
        ELSE NULL 
    END,
    location_name = raw_data->'location'->>'locationName',
    location_city = raw_data->'location'->>'city',
    location_state = raw_data->'location'->>'state',
    location_country = raw_data->'location'->>'country',
    location_postal_code = raw_data->'location'->>'postalCode',
    location_street_address = raw_data->'location'->>'streetAddress',
    location_latitude = CASE 
        WHEN raw_data->'location'->>'latitude' IS NOT NULL 
        THEN (raw_data->'location'->>'latitude')::DOUBLE PRECISION 
        ELSE NULL 
    END,
    location_longitude = CASE 
        WHEN raw_data->'location'->>'longitude' IS NOT NULL 
        THEN (raw_data->'location'->>'longitude')::DOUBLE PRECISION 
        ELSE NULL 
    END,
    location_source = raw_data->'location'->>'locationSource'
WHERE resource_type IS NULL;

-- ============================================
-- STEP 6: Backfill subscriptions from raw_data JSONB
-- ============================================
INSERT INTO device_subscriptions (device_id, subscription_id, resource_uri)
SELECT 
    d.id,
    (sub->>'id')::UUID,
    sub->>'resourceUri'
FROM devices d,
LATERAL jsonb_array_elements(d.raw_data->'subscription') AS sub
WHERE sub->>'id' IS NOT NULL
ON CONFLICT (device_id, subscription_id) DO NOTHING;

-- ============================================
-- STEP 7: Backfill tags from raw_data JSONB
-- ============================================
INSERT INTO device_tags (device_id, tag_key, tag_value)
SELECT 
    d.id,
    key,
    value::text
FROM devices d,
LATERAL jsonb_each_text(d.raw_data->'tags') AS t(key, value)
WHERE d.raw_data->'tags' IS NOT NULL
ON CONFLICT (device_id, tag_key) DO UPDATE SET tag_value = EXCLUDED.tag_value;

-- ============================================
-- Migration complete
-- ============================================
