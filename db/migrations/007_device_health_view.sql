-- ============================================
-- Device Health Aggregation View Migration
-- PostgreSQL 16+
-- ============================================
--
-- This migration adds a device_health_aggregation view that provides
-- at-a-glance operational health status by site and region.
--
-- The view aggregates:
-- 1. Device counts by site/region
-- 2. Online/offline status distribution
-- 3. Firmware classification breakdown
-- 4. Device type breakdown
--
-- Run this migration after aruba_central_migration.sql
-- ============================================


-- ============================================
-- DEVICE HEALTH AGGREGATION VIEW
-- Aggregates device health metrics by site and region
-- ============================================

CREATE OR REPLACE VIEW device_health_aggregation AS
SELECT
    -- Grouping dimensions
    COALESCE(central_site_id, 'no-site') AS site_id,
    COALESCE(central_site_name, 'No Site') AS site_name,
    COALESCE(region, 'Unknown') AS region,

    -- Total device counts
    COUNT(*) AS total_devices,
    COUNT(*) FILTER (WHERE in_central = TRUE) AS central_devices,
    COUNT(*) FILTER (WHERE in_greenlake = TRUE) AS greenlake_devices,

    -- Online/Offline status (from Aruba Central)
    COUNT(*) FILTER (WHERE central_status = 'ONLINE') AS online_count,
    COUNT(*) FILTER (WHERE central_status = 'OFFLINE') AS offline_count,
    COUNT(*) FILTER (WHERE central_status IS NULL) AS status_unknown,

    -- Firmware classification breakdown
    COUNT(*) FILTER (WHERE firmware_classification = 'CRITICAL') AS firmware_critical,
    COUNT(*) FILTER (WHERE firmware_classification = 'RECOMMENDED') AS firmware_recommended,
    COUNT(*) FILTER (WHERE firmware_classification = 'CURRENT') AS firmware_current,
    COUNT(*) FILTER (WHERE firmware_classification IS NULL) AS firmware_unknown,

    -- Device type breakdown (Central device types)
    COUNT(*) FILTER (WHERE central_device_type = 'ACCESS_POINT') AS access_points,
    COUNT(*) FILTER (WHERE central_device_type = 'SWITCH') AS switches,
    COUNT(*) FILTER (WHERE central_device_type = 'GATEWAY') AS gateways,
    COUNT(*) FILTER (WHERE central_device_type IS NULL) AS type_unknown,

    -- Health percentage (online / total central devices)
    CASE
        WHEN COUNT(*) FILTER (WHERE in_central = TRUE) > 0 THEN
            ROUND(
                (COUNT(*) FILTER (WHERE central_status = 'ONLINE')::NUMERIC /
                 COUNT(*) FILTER (WHERE in_central = TRUE)::NUMERIC) * 100,
                2
            )
        ELSE NULL
    END AS health_percentage,

    -- Last sync timestamp (most recent device update)
    MAX(last_seen_central) AS last_synced_at

FROM devices
WHERE NOT archived
GROUP BY
    COALESCE(central_site_id, 'no-site'),
    COALESCE(central_site_name, 'No Site'),
    COALESCE(region, 'Unknown')
ORDER BY
    site_name,
    region;


-- ============================================
-- VIEW COMMENTS
-- ============================================

COMMENT ON VIEW device_health_aggregation IS 'Aggregates device health metrics by site and region. Includes online/offline status, firmware classification, and device type breakdowns. Useful for operational health dashboards and monitoring.';


-- ============================================
-- EXAMPLE QUERIES
-- ============================================
--
-- Get health status for all sites:
--   SELECT * FROM device_health_aggregation ORDER BY total_devices DESC;
--
-- Find sites with offline devices:
--   SELECT site_name, region, offline_count, health_percentage
--   FROM device_health_aggregation
--   WHERE offline_count > 0
--   ORDER BY offline_count DESC;
--
-- Find sites with critical firmware:
--   SELECT site_name, region, firmware_critical, total_devices
--   FROM device_health_aggregation
--   WHERE firmware_critical > 0
--   ORDER BY firmware_critical DESC;
--
-- Get overall health summary:
--   SELECT
--     SUM(total_devices) AS total,
--     SUM(online_count) AS online,
--     SUM(offline_count) AS offline,
--     ROUND(SUM(online_count)::NUMERIC / NULLIF(SUM(total_devices), 0)::NUMERIC * 100, 2) AS overall_health_pct
--   FROM device_health_aggregation;
--
-- ============================================


-- ============================================
-- MIGRATION COMPLETE
-- ============================================
--
-- After running this migration:
-- 1. View device_health_aggregation will be available
-- 2. Query it to get device health metrics by site/region
-- 3. Use it in dashboard APIs for operational health monitoring
--
-- To verify: SELECT * FROM device_health_aggregation LIMIT 5;
-- ============================================
