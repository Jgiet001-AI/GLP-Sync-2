# Database Relationships & Query Patterns Guide

This guide explains the core table relationships in the HPE GreenLake Device & Subscription Sync database and provides practical query patterns for common use cases.

> **See Also:** [ER_DIAGRAM.md](./ER_DIAGRAM.md) for the visual entity relationship diagram.

## Table of Contents
1. [Core Relationships](#core-relationships)
2. [Querying Devices and Subscriptions](#querying-devices-and-subscriptions)
3. [Tag Relationships](#tag-relationships)
4. [JSONB Querying](#jsonb-querying)
5. [Full-Text Search](#full-text-search)
6. [Common Query Patterns](#common-query-patterns)
7. [Performance Tips](#performance-tips)

---

## Core Relationships

### 1. Many-to-Many: Devices ↔ Subscriptions

The **device_subscriptions** junction table implements the many-to-many relationship between devices and subscriptions.

```
devices (1) ←→ (M) device_subscriptions (M) ←→ (1) subscriptions
```

**Schema:**
```sql
-- devices table (28 columns + JSONB raw_data)
devices (
  id UUID PRIMARY KEY,           -- Device UUID from GreenLake API
  serial_number TEXT NOT NULL,   -- Unique serial number
  device_type TEXT,              -- SWITCH, AP, IAP, GATEWAY, etc.
  ...
)

-- subscriptions table (20 columns + JSONB raw_data)
subscriptions (
  id UUID PRIMARY KEY,           -- Subscription UUID from GreenLake API
  key TEXT,                      -- Human-readable key (e.g., PAT4DYYJAEEEJA)
  subscription_type TEXT,        -- CENTRAL_AP, CENTRAL_SWITCH, etc.
  subscription_status TEXT,      -- STARTED, ENDED, SUSPENDED, CANCELLED
  ...
)

-- Junction table
device_subscriptions (
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
  subscription_id UUID REFERENCES subscriptions(id) ON DELETE CASCADE,
  resource_uri TEXT,
  synced_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (device_id, subscription_id)
)
```

**Key Points:**
- A device can have **multiple subscriptions** (e.g., AP license + advanced features)
- A subscription can cover **multiple devices** (e.g., 100-device AP license)
- Both foreign keys have `ON DELETE CASCADE` - removing a device/subscription automatically removes the junction records
- The `subscriptions.key` field is human-readable; always use UUID (`id`) for joins

### 2. One-to-Many: Tags Relationships

Tags are stored in both **normalized tables** (for fast querying) and **JSONB** (for flexibility).

```
devices (1) ←→ (M) device_tags
subscriptions (1) ←→ (M) subscription_tags
```

**Schema:**
```sql
device_tags (
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
  tag_key TEXT NOT NULL,
  tag_value TEXT,
  synced_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (device_id, tag_key)
)

subscription_tags (
  subscription_id UUID REFERENCES subscriptions(id) ON DELETE CASCADE,
  tag_key TEXT NOT NULL,
  tag_value TEXT,
  synced_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (subscription_id, tag_key)
)
```

**Key Points:**
- Tags are key-value pairs for categorization (e.g., `{"customer": "Acme Corp", "environment": "production"}`)
- Each device/subscription can have multiple tags, but only one value per tag key
- Tags are also available in `devices.raw_data->'tags'` and `subscriptions.raw_data->'tags'` as JSONB
- Use normalized tables for filtering; use JSONB for ad-hoc queries

---

## Querying Devices and Subscriptions

### Basic Join: Get Subscription Details for a Device

```sql
-- Get all subscriptions for a specific device
SELECT
  d.serial_number,
  d.device_type,
  d.model,
  s.key as subscription_key,
  s.subscription_type,
  s.subscription_status,
  s.tier,
  s.start_time,
  s.end_time,
  (s.end_time - NOW()) as time_remaining
FROM devices d
JOIN device_subscriptions ds ON d.id = ds.device_id
JOIN subscriptions s ON ds.subscription_id = s.id
WHERE d.serial_number = 'VNT9KWC01V';
```

### Using the Pre-Built View

The **devices_with_subscriptions** view provides a convenient denormalized join:

```sql
-- Same query using the view
SELECT *
FROM devices_with_subscriptions
WHERE serial_number = 'VNT9KWC01V';

-- View definition (from schema.sql)
CREATE OR REPLACE VIEW devices_with_subscriptions AS
SELECT
  -- Device fields
  d.id as device_id,
  d.serial_number,
  d.device_type,
  d.model,
  d.region,
  ...
  -- Subscription fields
  s.id as subscription_id,
  s.key as subscription_key,
  s.subscription_type,
  s.tier,
  s.end_time as subscription_end,
  ...
  -- Computed fields
  s.end_time - NOW() as time_remaining,
  DATE_PART('day', s.end_time - NOW()) as days_remaining
FROM devices d
LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
LEFT JOIN subscriptions s ON ds.subscription_id = s.id
WHERE NOT d.archived;
```

### Reverse Query: Get All Devices for a Subscription

```sql
-- Find all devices using a specific subscription key
SELECT
  d.serial_number,
  d.device_type,
  d.model,
  d.region,
  d.assigned_state
FROM subscriptions s
JOIN device_subscriptions ds ON s.id = ds.subscription_id
JOIN devices d ON ds.device_id = d.id
WHERE s.key = 'PAT4DYYJAEEEJA'
  AND NOT d.archived;
```

### Subscription Utilization Query

```sql
-- Count how many devices are using each subscription
SELECT
  s.key as subscription_key,
  s.subscription_type,
  s.tier,
  s.quantity as total_licenses,
  s.available_quantity as available_licenses,
  COUNT(DISTINCT ds.device_id) as devices_using,
  s.quantity - s.available_quantity as licenses_in_use
FROM subscriptions s
LEFT JOIN device_subscriptions ds ON s.id = ds.subscription_id
WHERE s.subscription_status = 'STARTED'
GROUP BY s.id, s.key, s.subscription_type, s.tier, s.quantity, s.available_quantity
ORDER BY devices_using DESC;
```

---

## Tag Relationships

### Query Devices by Tag (Normalized Table)

```sql
-- Find all devices with a specific tag key
SELECT d.*
FROM devices d
JOIN device_tags dt ON d.id = dt.device_id
WHERE dt.tag_key = 'customer'
  AND NOT d.archived;

-- Find devices with a specific tag key-value pair
SELECT d.*
FROM devices d
JOIN device_tags dt ON d.id = dt.device_id
WHERE dt.tag_key = 'customer'
  AND dt.tag_value = 'Acme Corp'
  AND NOT d.archived;
```

### Using the Built-In Function

```sql
-- Find devices by tag using the helper function
SELECT * FROM get_devices_by_tag('customer', 'Acme Corp');

-- Find devices that have a tag key (any value)
SELECT * FROM get_devices_by_tag('customer');
```

**Function Definition:**
```sql
CREATE OR REPLACE FUNCTION get_devices_by_tag(
  tag_key TEXT,
  tag_value TEXT DEFAULT NULL
) RETURNS SETOF devices AS $$
BEGIN
  IF tag_value IS NULL THEN
    -- Just check if tag key exists
    RETURN QUERY
    SELECT * FROM devices
    WHERE raw_data->'tags' ? tag_key
      AND NOT archived;
  ELSE
    -- Check key and value
    RETURN QUERY
    SELECT * FROM devices
    WHERE raw_data->'tags'->>tag_key = tag_value
      AND NOT archived;
  END IF;
END;
$$ LANGUAGE plpgsql;
```

### Get All Tags for a Device

```sql
-- Using normalized table
SELECT tag_key, tag_value
FROM device_tags
WHERE device_id = 'your-device-uuid'
ORDER BY tag_key;

-- Using JSONB (returns as JSON object)
SELECT raw_data->'tags' as tags
FROM devices
WHERE id = 'your-device-uuid';
```

---

## JSONB Querying

Both `devices.raw_data` and `subscriptions.raw_data` contain the complete API response in JSONB format. This allows flexible querying without schema changes.

### JSONB Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `->` | Get JSON object field (returns JSON) | `raw_data->'subscription'` |
| `->>` | Get JSON object field as text | `raw_data->>'device_name'` |
| `@>` | Contains (JSON containment) | `raw_data @> '{"archived": false}'` |
| `?` | Does object have key? | `raw_data->'tags' ? 'customer'` |
| `?|` | Does object have any of these keys? | `raw_data->'tags' ?| array['customer', 'site']` |
| `?&` | Does object have all of these keys? | `raw_data->'tags' ?& array['customer', 'site']` |

### Common JSONB Queries

```sql
-- 1. Extract nested subscription data from device
SELECT
  serial_number,
  device_type,
  raw_data->'subscription' as subscriptions
FROM devices
WHERE id = 'your-device-uuid';

-- 2. Filter by JSONB field value
SELECT serial_number, device_type
FROM devices
WHERE raw_data->>'assigned_state' = 'ASSIGNED_TO_SERVICE';

-- 3. Check if device has any subscriptions (JSONB array)
SELECT serial_number, device_type
FROM devices
WHERE jsonb_typeof(raw_data->'subscription') = 'array'
  AND jsonb_array_length(raw_data->'subscription') > 0;

-- 4. Extract array elements
SELECT
  d.serial_number,
  sub->>'key' as subscription_key,
  (sub->>'endTime')::timestamptz as subscription_end
FROM devices d,
     jsonb_array_elements(d.raw_data->'subscription') as sub
WHERE d.id = 'your-device-uuid';

-- 5. Containment query (find devices in specific tier)
SELECT serial_number, device_type
FROM devices
WHERE raw_data @> '{"subscription": [{"tier": "FOUNDATION_SWITCH_6200"}]}';

-- 6. Tag existence check
SELECT serial_number
FROM devices
WHERE raw_data->'tags' ? 'customer'
  AND NOT archived;

-- 7. Tag value check
SELECT serial_number
FROM devices
WHERE raw_data->'tags'->>'customer' = 'Acme Corp'
  AND NOT archived;
```

### Performance Considerations

- JSONB queries use the GIN index: `idx_devices_raw` and `idx_subscriptions_raw`
- For frequently queried fields, prefer normalized columns over JSONB
- Use `jsonb_path_ops` indexes for containment queries (`@>`)
- Use separate GIN indexes for nested paths (e.g., `idx_devices_tags` on `raw_data->'tags'`)

---

## Full-Text Search

The schema includes auto-generated `tsvector` columns for full-text search, combining multiple fields with different weights.

### Search Vector Composition

**Devices:**
```sql
-- Generated column definition
search_vector tsvector GENERATED ALWAYS AS (
  setweight(to_tsvector('english', coalesce(serial_number, '')), 'A') ||  -- Highest weight
  setweight(to_tsvector('english', coalesce(device_name, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(mac_address, '')), 'B') ||
  setweight(to_tsvector('english', coalesce(model, '')), 'B') ||
  setweight(to_tsvector('english', coalesce(device_type, '')), 'C') ||
  setweight(to_tsvector('english', coalesce(region, '')), 'C') ||
  setweight(to_tsvector('english', coalesce(location_city, '')), 'C') ||
  setweight(to_tsvector('english', coalesce(location_country, '')), 'C')
) STORED
```

**Subscriptions:**
```sql
search_vector tsvector GENERATED ALWAYS AS (
  setweight(to_tsvector('english', coalesce(key, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(sku, '')), 'B') ||
  setweight(to_tsvector('english', coalesce(sku_description, '')), 'C') ||
  setweight(to_tsvector('english', coalesce(tier, '')), 'C') ||
  setweight(to_tsvector('english', coalesce(contract, '')), 'C')
) STORED
```

### Basic Full-Text Search

```sql
-- Simple search (uses websearch_to_tsquery for natural language)
SELECT
  serial_number,
  device_name,
  device_type,
  model,
  ts_rank(search_vector, websearch_to_tsquery('english', 'aruba 6200')) as rank
FROM devices
WHERE search_vector @@ websearch_to_tsquery('english', 'aruba 6200')
  AND NOT archived
ORDER BY rank DESC
LIMIT 50;
```

### Using the Search Function

```sql
-- Built-in search function with ranking
SELECT * FROM search_devices('aruba 6200', 50);

-- Search for serial number
SELECT * FROM search_devices('VNT9KWC01V');

-- Search for location
SELECT * FROM search_devices('San Francisco');

-- Search with multiple terms (websearch supports "AND", "OR", quotes)
SELECT * FROM search_devices('switch 6200 us-west');
```

**Function Definition:**
```sql
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
```

### Search Query Syntax

PostgreSQL's `websearch_to_tsquery` supports natural language queries:

```sql
-- AND operator (implicit)
'aruba switch'          -- matches documents with both "aruba" AND "switch"

-- OR operator
'aruba OR cisco'        -- matches documents with either term

-- NOT operator (-)
'switch -aruba'         -- matches "switch" but NOT "aruba"

-- Phrase search (quotes)
'"access point"'        -- exact phrase match

-- Combining operators
'(aruba OR cisco) switch -gateway'
```

---

## Common Query Patterns

### 1. Find Expiring Subscriptions

```sql
-- Using the pre-built view
SELECT *
FROM subscriptions_expiring_soon
WHERE days_remaining < 30
ORDER BY days_remaining ASC;

-- Manual query
SELECT
  key as subscription_key,
  subscription_type,
  tier,
  end_time,
  DATE_PART('day', end_time - NOW()) as days_remaining
FROM subscriptions
WHERE subscription_status = 'STARTED'
  AND end_time > NOW()
  AND end_time < NOW() + INTERVAL '30 days'
ORDER BY end_time ASC;
```

### 2. Devices with Expiring Subscriptions

```sql
-- Using the pre-built view
SELECT *
FROM devices_expiring_soon
ORDER BY subscription_end ASC;

-- Manual query
SELECT
  d.id,
  d.serial_number,
  d.device_type,
  d.model,
  sub->>'key' as subscription_key,
  (sub->>'endTime')::timestamptz as subscription_end
FROM devices d,
     jsonb_array_elements(d.raw_data->'subscription') as sub
WHERE NOT d.archived
  AND jsonb_typeof(d.raw_data->'subscription') = 'array'
  AND (sub->>'endTime')::timestamptz < NOW() + INTERVAL '90 days'
  AND (sub->>'endTime')::timestamptz > NOW()
ORDER BY (sub->>'endTime')::timestamptz ASC;
```

### 3. Device Summary by Type and Region

```sql
-- Using the pre-built view
SELECT *
FROM device_summary
ORDER BY device_type, region;

-- Manual query
SELECT
  device_type,
  region,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE assigned_state = 'ASSIGNED_TO_SERVICE') as assigned,
  COUNT(*) FILTER (WHERE assigned_state = 'UNASSIGNED') as unassigned,
  COUNT(*) FILTER (WHERE archived) as archived
FROM devices
GROUP BY device_type, region
ORDER BY device_type, region;
```

### 4. Subscription Utilization

```sql
-- Using the pre-built view
SELECT *
FROM subscription_summary;

-- Manual query with device counts
SELECT
  s.subscription_type,
  s.subscription_status,
  COUNT(*) as total_subscriptions,
  SUM(s.quantity) as total_licenses,
  SUM(s.available_quantity) as available_licenses,
  COUNT(DISTINCT ds.device_id) as devices_using
FROM subscriptions s
LEFT JOIN device_subscriptions ds ON s.id = ds.subscription_id
GROUP BY s.subscription_type, s.subscription_status
ORDER BY s.subscription_type, s.subscription_status;
```

### 5. Find Device by Serial, MAC, or Name

```sql
-- Exact lookup (fastest - uses index)
SELECT * FROM devices WHERE serial_number = 'VNT9KWC01V';
SELECT * FROM devices WHERE mac_address = '5C:A4:7D:6D:25:C0';

-- Partial match (uses full-text search)
SELECT * FROM search_devices('VNT9KWC01V');

-- Case-insensitive partial match
SELECT * FROM devices
WHERE serial_number ILIKE '%VNT9%'
  AND NOT archived;
```

### 6. Recently Updated Devices

```sql
-- Devices updated in last 24 hours
SELECT
  serial_number,
  device_type,
  model,
  updated_at,
  synced_at
FROM devices
WHERE updated_at > NOW() - INTERVAL '24 hours'
ORDER BY updated_at DESC;
```

### 7. Devices in Specific Location

```sql
-- By city
SELECT serial_number, device_type, model, location_city
FROM devices
WHERE location_city = 'San Francisco'
  AND NOT archived;

-- By country
SELECT serial_number, device_type, model, location_country
FROM devices
WHERE location_country = 'United States'
  AND NOT archived;

-- With coordinates (geospatial query)
SELECT
  serial_number,
  device_type,
  location_city,
  location_latitude,
  location_longitude
FROM devices
WHERE location_latitude IS NOT NULL
  AND location_longitude IS NOT NULL
  AND NOT archived;
```

### 8. Complex Join: Devices with Subscription and Tags

```sql
-- Get complete device profile
SELECT
  d.serial_number,
  d.device_type,
  d.model,
  d.region,
  d.assigned_state,
  s.key as subscription_key,
  s.subscription_type,
  s.tier,
  s.end_time as subscription_end,
  jsonb_object_agg(dt.tag_key, dt.tag_value) as tags
FROM devices d
LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
LEFT JOIN subscriptions s ON ds.subscription_id = s.id
LEFT JOIN device_tags dt ON d.id = dt.device_id
WHERE d.serial_number = 'VNT9KWC01V'
GROUP BY
  d.serial_number, d.device_type, d.model, d.region, d.assigned_state,
  s.key, s.subscription_type, s.tier, s.end_time;
```

---

## Performance Tips

### 1. Use Indexes Wisely

```sql
-- ✅ GOOD: Uses index on device_type
SELECT * FROM devices WHERE device_type = 'SWITCH';

-- ❌ BAD: Function on indexed column prevents index usage
SELECT * FROM devices WHERE LOWER(device_type) = 'switch';

-- ✅ GOOD: Use normalized columns for common filters
SELECT * FROM devices WHERE archived = false;

-- ❌ BAD: JSONB query when normalized column exists
SELECT * FROM devices WHERE raw_data->>'archived' = 'false';
```

### 2. Leverage Partial Indexes

```sql
-- Partial index: idx_devices_archived (only non-archived devices)
-- This query uses the partial index
SELECT * FROM devices WHERE NOT archived;

-- Partial index: idx_subscriptions_expiring (only STARTED subscriptions)
-- This query uses the partial index
SELECT * FROM subscriptions
WHERE subscription_status = 'STARTED'
  AND end_time < NOW() + INTERVAL '30 days';
```

### 3. Use Covering Indexes

```sql
-- Covering index: idx_subscriptions_expiring_covering
-- Includes: end_time, key, subscription_type, tier, sku, quantity, available_quantity
-- This query uses index-only scan (no table access needed)
SELECT key, subscription_type, tier, end_time
FROM subscriptions
WHERE subscription_status = 'STARTED'
  AND end_time < NOW() + INTERVAL '30 days';
```

### 4. Optimize Joins

```sql
-- ✅ GOOD: Use pre-built views for common joins
SELECT * FROM devices_with_subscriptions WHERE serial_number = 'VNT9KWC01V';

-- ✅ GOOD: Filter early in the query
SELECT d.*, s.*
FROM devices d
JOIN device_subscriptions ds ON d.id = ds.device_id
JOIN subscriptions s ON ds.subscription_id = s.id
WHERE d.serial_number = 'VNT9KWC01V'  -- Filter on indexed column
  AND NOT d.archived;                   -- Use partial index

-- ❌ BAD: No filters, large result set
SELECT d.*, s.*
FROM devices d
LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
LEFT JOIN subscriptions s ON ds.subscription_id = s.id;
```

### 5. Pagination for Large Results

```sql
-- ✅ GOOD: Use LIMIT and OFFSET for pagination
SELECT serial_number, device_type, model, updated_at
FROM devices
WHERE NOT archived
ORDER BY updated_at DESC
LIMIT 50 OFFSET 0;  -- First page (0-49)

-- Next page
LIMIT 50 OFFSET 50;  -- Second page (50-99)
```

### 6. Analyze Query Performance

```sql
-- Use EXPLAIN ANALYZE to understand query execution
EXPLAIN ANALYZE
SELECT * FROM devices
WHERE device_type = 'SWITCH'
  AND region = 'us-west'
  AND NOT archived;

-- Look for:
-- - "Index Scan" vs "Seq Scan" (index scans are faster)
-- - "Index Only Scan" (best - no table access)
-- - Execution time and row counts
```

### 7. Use Prepared Statements

For applications making repeated queries with different parameters, use prepared statements to avoid parsing overhead and enable query plan caching.

```sql
-- PostgreSQL prepared statement
PREPARE find_device AS
  SELECT * FROM devices WHERE serial_number = $1;

EXECUTE find_device('VNT9KWC01V');
```

---

## Additional Resources

- **Schema Files:**
  - [schema.sql](./schema.sql) - Devices, tags, sync tracking
  - [subscriptions_schema.sql](./subscriptions_schema.sql) - Subscriptions and related tables
  - [ER_DIAGRAM.md](./ER_DIAGRAM.md) - Visual entity relationship diagram

- **Built-in Documentation:**
  ```sql
  -- View schema documentation
  SELECT * FROM schema_info ORDER BY table_name, column_name;

  -- View valid categorical values
  SELECT * FROM valid_column_values;

  -- View example queries
  SELECT category, description, sql_query
  FROM query_examples
  ORDER BY category;
  ```

- **PostgreSQL Documentation:**
  - [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html)
  - [Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
  - [Indexes](https://www.postgresql.org/docs/current/indexes.html)

---

## Quick Reference

### Useful Queries Cheat Sheet

```sql
-- Find device by serial
SELECT * FROM devices WHERE serial_number = 'YOUR_SERIAL';

-- Search devices (full-text)
SELECT * FROM search_devices('aruba 6200');

-- Find devices by tag
SELECT * FROM get_devices_by_tag('customer', 'Acme Corp');

-- Get subscription details for device
SELECT * FROM devices_with_subscriptions WHERE serial_number = 'YOUR_SERIAL';

-- Find expiring subscriptions
SELECT * FROM subscriptions_expiring_soon WHERE days_remaining < 30;

-- Devices with expiring subscriptions
SELECT * FROM devices_expiring_soon;

-- Device summary by type
SELECT * FROM device_summary;

-- Subscription utilization
SELECT * FROM subscription_summary;

-- Recently synced devices
SELECT * FROM devices WHERE synced_at > NOW() - INTERVAL '1 hour' ORDER BY synced_at DESC;

-- View sync history
SELECT * FROM sync_history ORDER BY started_at DESC LIMIT 10;
```

### Index Reference

```sql
-- List all indexes on a table
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'devices'
ORDER BY indexname;

-- Check index usage statistics
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan as index_scans,
  idx_tup_read as tuples_read,
  idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

---

**Last Updated:** 2024-01-13
**Schema Version:** PostgreSQL 16+ with pgvector, pg_trgm, uuid-ossp extensions
