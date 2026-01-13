# Database Schema ER Diagram

This diagram shows the core database schema for the HPE GreenLake Device & Subscription Sync platform.

## Entity Relationship Diagram

```mermaid
erDiagram
    devices ||--o{ device_subscriptions : "has many"
    subscriptions ||--o{ device_subscriptions : "has many"
    devices ||--o{ device_tags : "has many"
    subscriptions ||--o{ subscription_tags : "has many"

    devices {
        UUID id PK "Device UUID from GreenLake API"
        TEXT serial_number UK "Unique device serial number"
        TEXT mac_address "Device MAC address"
        TEXT part_number "Device part number"
        TEXT device_type "SWITCH, AP, IAP, GATEWAY, COMPUTE, STORAGE"
        TEXT model "Hardware model name"
        TEXT region "Geographic region"
        BOOLEAN archived "True if decommissioned"
        TEXT device_name "Primary device name"
        TEXT secondary_name "Alternative device name"
        TEXT assigned_state "ASSIGNED_TO_SERVICE, UNASSIGNED"
        TEXT resource_type "e.g., devices/device"
        UUID tenant_workspace_id "MSP tenant workspace"
        UUID application_id "Application reference"
        TEXT application_resource_uri "Application URI"
        UUID dedicated_platform_id "Dedicated platform workspace"
        UUID location_id "Location reference ID"
        TEXT location_name "Location name"
        TEXT location_city "City"
        TEXT location_state "State/Province"
        TEXT location_country "Country"
        TEXT location_postal_code "Postal code"
        TEXT location_street_address "Street address"
        DOUBLE_PRECISION location_latitude "Latitude"
        DOUBLE_PRECISION location_longitude "Longitude"
        TEXT location_source "Source of location data"
        TIMESTAMPTZ created_at "Created timestamp from API"
        TIMESTAMPTZ updated_at "Updated timestamp from API"
        TIMESTAMPTZ synced_at "Last sync timestamp"
        JSONB raw_data "Full API response for flexibility"
        TSVECTOR search_vector "Auto-generated FTS vector"
    }

    subscriptions {
        UUID id PK "Subscription UUID from GreenLake API"
        TEXT key UK "Human-readable subscription key"
        TEXT resource_type "e.g., subscriptions/subscription"
        TEXT subscription_type "CENTRAL_AP, CENTRAL_SWITCH, CENTRAL_GW, etc."
        TEXT subscription_status "STARTED, ENDED, SUSPENDED, CANCELLED"
        INTEGER quantity "Total licenses"
        INTEGER available_quantity "Remaining unused licenses"
        TEXT sku "Stock keeping unit code"
        TEXT sku_description "SKU description"
        TIMESTAMPTZ start_time "Subscription start date"
        TIMESTAMPTZ end_time "Subscription expiration date"
        TEXT tier "Service tier level"
        TEXT tier_description "Tier description"
        TEXT product_type "DEVICE, SERVICE, etc."
        BOOLEAN is_eval "True if evaluation/trial"
        TEXT contract "Contract reference"
        TEXT quote "Quote reference"
        TEXT po "Purchase order"
        TEXT reseller_po "Reseller PO for indirect orders"
        TIMESTAMPTZ created_at "Created timestamp from API"
        TIMESTAMPTZ updated_at "Updated timestamp from API"
        TIMESTAMPTZ synced_at "Last sync timestamp"
        JSONB raw_data "Full API response for flexibility"
        TSVECTOR search_vector "Auto-generated FTS vector"
    }

    device_subscriptions {
        UUID device_id PK,FK "References devices.id"
        UUID subscription_id PK,FK "References subscriptions.id"
        TEXT resource_uri "Subscription resource URI"
        TIMESTAMPTZ synced_at "Last sync timestamp"
    }

    device_tags {
        UUID device_id PK,FK "References devices.id"
        TEXT tag_key PK "Tag key name"
        TEXT tag_value "Tag value"
        TIMESTAMPTZ synced_at "Last sync timestamp"
    }

    subscription_tags {
        UUID subscription_id PK,FK "References subscriptions.id"
        TEXT tag_key PK "Tag key name"
        TEXT tag_value "Tag value"
        TIMESTAMPTZ synced_at "Last sync timestamp"
    }

    sync_history {
        BIGINT id PK "Auto-increment ID"
        TEXT resource_type "devices, subscriptions"
        TIMESTAMPTZ started_at "Sync start time"
        TIMESTAMPTZ completed_at "Sync completion time"
        TEXT status "running, completed, failed"
        INTEGER records_fetched "Records fetched from API"
        INTEGER records_inserted "Records inserted to DB"
        INTEGER records_updated "Records updated in DB"
        INTEGER records_errors "Number of errors"
        TEXT error_message "Error details if failed"
        INTEGER duration_ms "Computed sync duration in ms"
    }

    query_examples {
        BIGINT id PK "Auto-increment ID"
        TEXT category "search, filter, expiring, summary, join, tags"
        TEXT description "Human-readable query description"
        TEXT sql_query "SQL query template"
        TIMESTAMPTZ created_at "Record creation timestamp"
    }
```

## Key Relationships

### Many-to-Many: Devices ↔ Subscriptions
- **device_subscriptions** table acts as a junction table
- One device can have multiple subscriptions
- One subscription can cover multiple devices
- Implements the M:M relationship between devices and their subscription licenses

### One-to-Many: Devices ↔ Device Tags
- Each device can have multiple tags (key-value pairs)
- Tags are normalized into **device_tags** table for efficient querying
- Also available in JSONB format within `devices.raw_data` for flexibility

### One-to-Many: Subscriptions ↔ Subscription Tags
- Each subscription can have multiple tags (key-value pairs)
- Tags are normalized into **subscription_tags** table
- Also available in JSONB format within `subscriptions.raw_data`

### Tracking Table: Sync History
- **sync_history** table is independent (no foreign keys)
- Tracks all synchronization operations for both devices and subscriptions
- Provides audit trail and sync metrics

### Reference Table: Query Examples
- **query_examples** table is independent
- Stores example SQL queries for LLM/AI assistants
- Categorized by query type (search, filter, expiring, etc.)

## Important Views

The schema includes several materialized views for common queries:

- **active_devices** - Non-archived devices only
- **active_subscriptions** - Active (STARTED) subscriptions only
- **devices_expiring_soon** - Devices with subscriptions expiring in 90 days
- **subscriptions_expiring_soon** - Subscriptions expiring in 90 days
- **devices_with_subscriptions** - Denormalized view joining devices and subscriptions
- **device_summary** - Aggregated device counts by type and region
- **subscription_summary** - Aggregated subscription counts by type and status
- **schema_info** - Schema metadata for LLM understanding
- **valid_column_values** - Valid categorical values with occurrence counts

## Important Functions

- **search_devices(query, limit)** - Full-text search with ranking
- **get_devices_by_tag(key, value)** - Tag-based device lookup

## Data Storage Philosophy

The schema follows a **hybrid approach**:

1. **Normalized fields** - Frequently queried fields are extracted to table columns with indexes
2. **JSONB raw_data** - Complete API response stored for flexibility and future-proofing
3. **Full-text search** - Auto-generated `tsvector` columns enable fast search
4. **Normalized tags** - Tags extracted to separate tables for efficient filtering

This design optimizes for:
- Fast common queries (using indexed columns)
- Flexibility (using JSONB for complex/rare queries)
- Maintainability (API changes don't break existing queries)
- Performance (strategic indexes, covering indexes, partial indexes)

## Indexing Strategy

### Primary Indexes
- Primary keys on all tables (UUID for entities, composite for junction tables)
- Unique indexes on natural keys (serial_number, subscription key)

### Query Optimization Indexes
- B-tree indexes on frequently filtered columns (device_type, region, subscription_status, etc.)
- GIN indexes for full-text search (search_vector columns)
- GIN indexes for JSONB queries (raw_data columns)
- Composite indexes for common multi-column filters
- Covering indexes to enable index-only scans
- Partial indexes for common WHERE clause patterns

### Performance Features
- Generated columns for computed values (search_vector, duration_ms)
- Partial indexes for active/non-archived records
- JSONB path operators for nested data access
- PostgreSQL extensions: uuid-ossp, pg_trgm, pgvector (for AI features)
