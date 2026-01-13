-- Migration 007: Add Composite Indexes for Common Device Query Patterns
-- Applied: 2026-01-13
--
-- This migration adds composite indexes to optimize common device query patterns
-- used in the devices list endpoint. These indexes support filtered queries with
-- combinations of device_type, region, assigned_state, and archived columns,
-- sorted by updated_at DESC.
--
-- Performance Impact:
-- - Reduces multi-column queries from bitmap index scans to single index scans
-- - Improves query performance for common filter combinations
-- - Particularly beneficial for paginated API responses with ORDER BY updated_at DESC

-- ============================================
-- COMPOSITE INDEXES FOR COMMON QUERY PATTERNS
-- ============================================

-- Index for device_type + archived + updated_at DESC
-- Optimizes: WHERE device_type = X AND NOT archived ORDER BY updated_at DESC
CREATE INDEX IF NOT EXISTS idx_devices_type_archived_updated
ON devices(device_type, archived, updated_at DESC);

-- Index for region + archived + updated_at DESC
-- Optimizes: WHERE region = X AND NOT archived ORDER BY updated_at DESC
CREATE INDEX IF NOT EXISTS idx_devices_region_archived_updated
ON devices(region, archived, updated_at DESC);

-- Index for assigned_state + archived + updated_at DESC
-- Optimizes: WHERE assigned_state = X AND NOT archived ORDER BY updated_at DESC
CREATE INDEX IF NOT EXISTS idx_devices_assigned_archived_updated
ON devices(assigned_state, archived, updated_at DESC);

-- Composite index for device_type + region + archived + updated_at DESC
-- Optimizes: WHERE device_type = X AND region = Y AND NOT archived ORDER BY updated_at DESC
-- This covers more specific multi-filter queries
CREATE INDEX IF NOT EXISTS idx_devices_type_region_archived_updated
ON devices(device_type, region, archived, updated_at DESC);

-- ============================================
-- Migration complete
-- ============================================
