# Database Relationships & Query Patterns Guide

This guide explains the core table relationships in the HPE GreenLake Device & Subscription Sync database and provides practical query patterns for common use cases.

> **See Also:** [ER_DIAGRAM.md](./ER_DIAGRAM.md) for the visual entity relationship diagram.

## Table of Contents
1. [Core Relationships](#core-relationships)
2. [Audit & Reference Tables](#audit--reference-tables)
3. [Network Clients & Sites Relationships](#network-clients--sites-relationships)
4. [Agent Chatbot Relationships & Special Features](#agent-chatbot-relationships--special-features)
5. [Querying Devices and Subscriptions](#querying-devices-and-subscriptions)
6. [Tag Relationships](#tag-relationships)
7. [JSONB Querying](#jsonb-querying)
8. [Full-Text Search](#full-text-search)
9. [Common Query Patterns](#common-query-patterns)
10. [Performance Tips](#performance-tips)
11. [Schema Files Reference](#schema-files-reference)
12. [Additional Resources](#additional-resources)
13. [Quick Reference](#quick-reference)

### Related Documentation
- [ER_DIAGRAM.md](./ER_DIAGRAM.md) - Visual entity relationship diagram with complete schema overview
- [schema.sql](./schema.sql) - SQL schema definitions for core tables
- [subscriptions_schema.sql](./subscriptions_schema.sql) - SQL schema for subscription tables
- [clients_migration.sql](./clients_migration.sql) - SQL schema for Aruba Central integration (sites, clients)
- [migrations/004_agent_chatbot.sql](./migrations/004_agent_chatbot.sql) - SQL schema for AI agent base tables
- [migrations/006_agentdb_memory_patterns.sql](./migrations/006_agentdb_memory_patterns.sql) - SQL schema for AI agent advanced features

---

## Core Relationships

> **See Also:** [ER_DIAGRAM.md - Key Relationships](./ER_DIAGRAM.md#key-relationships) for visual representation

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

## Audit & Reference Tables

### Sync History (Audit Trail)

The **sync_history** table is an **independent audit table** (no foreign keys) that tracks all synchronization operations for both devices and subscriptions.

```
sync_history (independent table)
  ↓
Tracks sync operations for:
  - devices
  - subscriptions
```

**Schema:**
```sql
sync_history (
  id BIGINT PRIMARY KEY,                 -- Auto-increment ID
  resource_type TEXT,                    -- 'devices' or 'subscriptions'
  started_at TIMESTAMPTZ,                -- Sync start time
  completed_at TIMESTAMPTZ,              -- Sync completion time
  status TEXT,                           -- 'running', 'completed', 'failed'
  records_fetched INTEGER,               -- Records fetched from API
  records_inserted INTEGER,              -- Records inserted to DB
  records_updated INTEGER,               -- Records updated in DB
  records_errors INTEGER,                -- Number of errors
  error_message TEXT,                    -- Error details if failed
  duration_ms INTEGER GENERATED ALWAYS AS (
    EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000
  ) STORED                               -- Computed sync duration in ms
)
```

**Key Points:**
- **No Foreign Keys:** Independent table that references no other tables
- **Dual Purpose:** Tracks both device syncs and subscription syncs via `resource_type` field
- **Audit Trail:** Provides complete history of all sync operations
- **Performance Metrics:** Captures timing (duration_ms), volume (records_fetched/inserted/updated), and errors
- **Computed Duration:** `duration_ms` is automatically calculated from `started_at` and `completed_at`

**Example Query: View Recent Sync History**
```sql
-- View last 10 sync operations
SELECT
  resource_type,
  started_at,
  completed_at,
  status,
  records_fetched,
  records_inserted,
  records_updated,
  records_errors,
  duration_ms,
  CASE
    WHEN status = 'completed' AND records_errors = 0 THEN '✅ Success'
    WHEN status = 'completed' AND records_errors > 0 THEN '⚠️ Partial'
    WHEN status = 'failed' THEN '❌ Failed'
    ELSE '🔄 Running'
  END as sync_status
FROM sync_history
ORDER BY started_at DESC
LIMIT 10;
```

---

### Query Examples (Reference Data)

The **query_examples** table is an **independent reference table** that stores example SQL queries for LLM/AI assistants and documentation purposes.

```
query_examples (independent table)
  ↓
Provides example queries categorized by use case
```

**Schema:**
```sql
query_examples (
  id BIGINT PRIMARY KEY,                 -- Auto-increment ID
  category TEXT,                         -- 'search', 'filter', 'expiring', 'summary', 'join', 'tags'
  description TEXT,                      -- Human-readable query description
  sql_query TEXT,                        -- SQL query template
  created_at TIMESTAMPTZ DEFAULT NOW()   -- Record creation timestamp
)
```

**Key Points:**
- **No Foreign Keys:** Independent reference table
- **AI Assistant Support:** Provides query examples for LLM-based tools (like MCP server)
- **Categorized:** Queries grouped by category for easy lookup
- **Templates:** SQL queries may include placeholders (e.g., `$1`, `?`) for parameterization
- **Documentation:** Serves as runnable documentation for common query patterns

**Query Categories:**
- **search:** Full-text search queries using `search_vector`
- **filter:** Filtering by device type, region, status, etc.
- **expiring:** Finding expiring subscriptions/devices
- **summary:** Aggregation queries (counts, summaries)
- **join:** Multi-table join examples (devices ↔ subscriptions)
- **tags:** Tag-based queries using normalized or JSONB tags

**Example Query: Browse Query Examples**
```sql
-- View all query examples by category
SELECT
  category,
  description,
  sql_query
FROM query_examples
ORDER BY category, id;

-- Find examples for a specific category
SELECT
  description,
  sql_query
FROM query_examples
WHERE category = 'expiring'
ORDER BY id;
```

---

### 3. Network Clients & Sites Relationships

Network clients (WiFi/wired devices connected to network equipment) are organized using a **two-level hierarchy**: Sites → Clients, with clients linked to network devices via serial numbers.

```
sites (1) ←→ (M) clients
clients (M) ←→ (1) devices [via serial_number]
devices (1) ←→ (1) firmware information
```

**Schema:**
```sql
-- sites table (physical locations)
sites (
  site_id TEXT PRIMARY KEY,          -- Unique site identifier from Aruba Central
  site_name TEXT,                    -- Human-readable site name
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
)

-- clients table (network clients connected to equipment)
clients (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,

  -- Client identifiers
  mac MACADDR NOT NULL,              -- Normalized MAC address
  name TEXT,

  -- Health & Status
  health TEXT CHECK (health IN ('Good', 'Fair', 'Poor', 'Unknown')),
  status TEXT CHECK (status IN ('Connected', 'Failed', 'Connecting',
                                 'Disconnected', 'Blocked', 'Unknown', 'REMOVED')),
  type TEXT CHECK (type IN ('Wired', 'Wireless')),

  -- Network information
  ipv4 INET,                         -- IPv4 address (INET type for validation)
  ipv6 INET,
  vlan_id TEXT,
  port TEXT,

  -- Connected device info (links to devices table)
  connected_device_serial TEXT,      -- Foreign key to devices.serial_number
  connected_to TEXT,                 -- Device name
  connected_since TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,

  -- Full API response
  raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,

  UNIQUE(site_id, mac)               -- One MAC per site
)

-- devices table firmware enrichment
ALTER TABLE devices ADD COLUMN firmware_version TEXT;
ALTER TABLE devices ADD COLUMN firmware_recommended_version TEXT;
ALTER TABLE devices ADD COLUMN firmware_upgrade_status TEXT;
ALTER TABLE devices ADD COLUMN firmware_classification TEXT;
ALTER TABLE devices ADD COLUMN firmware_last_upgraded_at TIMESTAMPTZ;
ALTER TABLE devices ADD COLUMN firmware_synced_at TIMESTAMPTZ;
```

**Key Points:**

1. **Sites Hierarchy:**
   - Sites represent physical locations where network devices are deployed
   - Each site can have multiple clients and devices
   - Sites are synced from Aruba Central

2. **Clients Connection to Sites:**
   - Each client **must** belong to exactly one site (`site_id` is NOT NULL)
   - `ON DELETE CASCADE` - deleting a site removes all its clients
   - `UNIQUE(site_id, mac)` - a MAC address can appear once per site (but can reappear at different sites)

3. **Clients Connection to Devices (via Serial Number):**
   - `clients.connected_device_serial` links to `devices.serial_number` (soft foreign key)
   - This is **not a database FK constraint** to allow flexibility when devices are removed
   - Use `get_clients_by_device(serial)` function to find all clients on a device
   - The `connected_to` field stores the device name for convenience

4. **Firmware Tracking:**
   - Firmware information is enriched **directly on the devices table**
   - `firmware_version` - Current version running on device
   - `firmware_recommended_version` - Recommended version from Aruba Central
   - `firmware_upgrade_status` - Current upgrade status
   - `firmware_classification` - Classification of firmware version
   - `firmware_last_upgraded_at` - Last upgrade timestamp
   - `firmware_synced_at` - When firmware info was last synced
   - Use `devices_firmware_status` view for firmware analysis

---

## Network Clients & Sites Relationships

> **Schema Files:** [clients_migration.sql](./clients_migration.sql) | **Visual:** [ER_DIAGRAM.md](./ER_DIAGRAM.md#one-to-many-sites--clients)

### Understanding the Hierarchy

The network clients data model follows a **two-level organizational hierarchy**:

```
Site (e.g., "San Francisco HQ")
  ├── Client 1 (MAC: aa:bb:cc:dd:ee:01, Connected to: Switch-01)
  ├── Client 2 (MAC: aa:bb:cc:dd:ee:02, Connected to: AP-01)
  └── Client 3 (MAC: aa:bb:cc:dd:ee:03, Connected to: AP-02)

Devices (network equipment)
  ├── Switch-01 (Serial: SN12345, Firmware: 10.2.1)
  ├── AP-01 (Serial: SN67890, Firmware: 8.5.3)
  └── AP-02 (Serial: SN11111, Firmware: 8.5.3)
```

### Query Pattern: Get All Clients for a Site

```sql
-- Get all clients at a specific site with health and status
SELECT
  c.mac,
  c.name,
  c.health,
  c.status,
  c.type,
  c.ipv4,
  c.connected_to,
  c.last_seen_at
FROM clients c
WHERE c.site_id = 'site-sf-hq'
  AND (c.status IS NULL OR c.status != 'REMOVED')
ORDER BY c.status, c.last_seen_at DESC;

-- Using the pre-built view (includes site name)
SELECT
  mac,
  name,
  site_name,
  health,
  status,
  type,
  connected_to
FROM active_clients
WHERE site_id = 'site-sf-hq'
ORDER BY status, last_seen_at DESC;
```

### Query Pattern: Get All Clients Connected to a Device

```sql
-- Find all clients connected to a specific device by serial number
SELECT
  c.mac,
  c.name,
  c.health,
  c.status,
  c.type,
  c.ipv4,
  c.vlan_id,
  c.port,
  c.connected_since,
  s.site_name
FROM clients c
JOIN sites s ON c.site_id = s.site_id
WHERE c.connected_device_serial = 'SN12345'
  AND (c.status IS NULL OR c.status != 'REMOVED')
ORDER BY c.connected_since DESC;

-- Using the built-in function
SELECT * FROM get_clients_by_device('SN12345');
```

### Query Pattern: Site Summary with Client Counts

```sql
-- Get site summary with dynamic client counts
SELECT
  site_id,
  site_name,
  client_count,
  connected_count,
  wired_count,
  wireless_count,
  good_health_count,
  fair_health_count,
  poor_health_count,
  device_count
FROM sites_with_stats
ORDER BY client_count DESC;

-- Filter to sites with issues
SELECT *
FROM sites_with_stats
WHERE poor_health_count > 0 OR (connected_count / NULLIF(client_count, 0)) < 0.9
ORDER BY poor_health_count DESC, connected_count ASC;
```

### Query Pattern: Client Health Summary

```sql
-- Overall client health across all sites
SELECT * FROM clients_health_summary;

-- Returns:
-- total_clients, connected, disconnected, failed, blocked,
-- wired, wireless, health_good, health_fair, health_poor, health_unknown
```

### Query Pattern: Search Clients

```sql
-- Search by MAC address, name, or IP
SELECT * FROM search_clients('aa:bb:cc', 50);

-- Search by IP address
SELECT * FROM search_clients('192.168.1', 50);

-- Search by client name
SELECT * FROM search_clients('iPhone', 50);

-- Manual search with site info
SELECT
  c.mac,
  c.name,
  s.site_name,
  c.health,
  c.status,
  c.type,
  c.ipv4,
  c.connected_to
FROM clients c
JOIN sites s ON c.site_id = s.site_id
WHERE (c.status IS NULL OR c.status != 'REMOVED')
  AND (
    c.mac::TEXT ILIKE '%aa:bb:cc%'
    OR c.name ILIKE '%iPhone%'
    OR c.ipv4::TEXT LIKE '%192.168.1%'
  )
ORDER BY
  CASE WHEN c.status = 'Connected' THEN 0 ELSE 1 END,
  c.last_seen_at DESC NULLS LAST
LIMIT 50;
```

### Query Pattern: Clients with Device Details

```sql
-- Join clients with their connected network devices
SELECT
  c.mac,
  c.name as client_name,
  c.health,
  c.status,
  c.type,
  c.ipv4,
  c.connected_since,
  c.last_seen_at,
  -- Device details
  d.serial_number,
  COALESCE(d.central_device_name, d.device_name) as device_name,
  COALESCE(d.central_device_type, d.device_type) as device_type,
  d.model,
  d.central_status as device_status,
  -- Site info
  s.site_name
FROM clients c
JOIN sites s ON c.site_id = s.site_id
LEFT JOIN devices d ON c.connected_device_serial = d.serial_number
WHERE (c.status IS NULL OR c.status != 'REMOVED')
ORDER BY c.last_seen_at DESC
LIMIT 100;
```

### Query Pattern: Firmware Status Analysis

```sql
-- View all devices with firmware information
SELECT * FROM devices_firmware_status
ORDER BY firmware_status, serial_number;

-- Find devices needing firmware updates
SELECT
  serial_number,
  device_name,
  device_type,
  model,
  central_site_name,
  firmware_version,
  firmware_recommended_version,
  firmware_upgrade_status
FROM devices_firmware_status
WHERE firmware_status = 'UPDATE_AVAILABLE'
ORDER BY central_site_name, device_type;

-- Group firmware status by device type
SELECT
  device_type,
  COUNT(*) as total_devices,
  COUNT(*) FILTER (WHERE firmware_version = firmware_recommended_version) as up_to_date,
  COUNT(*) FILTER (WHERE firmware_version != firmware_recommended_version) as needs_update,
  COUNT(*) FILTER (WHERE firmware_upgrade_status IS NOT NULL) as upgrade_in_progress
FROM devices
WHERE firmware_version IS NOT NULL AND NOT archived
GROUP BY device_type
ORDER BY device_type;
```

### Query Pattern: Device Firmware with Connected Clients

```sql
-- Find devices with outdated firmware and count connected clients
SELECT
  d.serial_number,
  COALESCE(d.central_device_name, d.device_name) as device_name,
  COALESCE(d.central_device_type, d.device_type) as device_type,
  d.firmware_version,
  d.firmware_recommended_version,
  d.firmware_upgrade_status,
  COUNT(c.id) as connected_clients,
  COUNT(c.id) FILTER (WHERE c.status = 'Connected') as active_connections
FROM devices d
LEFT JOIN clients c ON d.serial_number = c.connected_device_serial
  AND (c.status IS NULL OR c.status != 'REMOVED')
WHERE NOT d.archived
  AND d.firmware_version IS NOT NULL
  AND d.firmware_version != d.firmware_recommended_version
GROUP BY
  d.serial_number,
  d.central_device_name,
  d.device_name,
  d.central_device_type,
  d.device_type,
  d.firmware_version,
  d.firmware_recommended_version,
  d.firmware_upgrade_status
HAVING COUNT(c.id) > 0  -- Only devices with clients
ORDER BY connected_clients DESC;
```

### Important Data Type Notes

1. **MAC Address Storage:**
   - Stored as `MACADDR` type (PostgreSQL native)
   - Automatically normalizes format: `aa:bb:cc:dd:ee:ff` → `aa:bb:cc:dd:ee:ff`
   - Enables MAC address operations and comparisons
   - Search using text cast: `mac::TEXT ILIKE '%aa:bb%'`

2. **IP Address Storage:**
   - Stored as `INET` type (validates both IPv4 and IPv6)
   - Supports subnet operations and IP range queries
   - Cast to text for pattern matching: `ipv4::TEXT LIKE '192.168.%'`

3. **Firmware Timestamps:**
   - `firmware_last_upgraded_at` - When device was last upgraded
   - `firmware_synced_at` - When firmware data was last fetched from API
   - Use `firmware_synced_at` to detect stale data

### Performance Indexes

The following indexes optimize network client queries:

```sql
-- Site lookup (primary access pattern)
idx_clients_site_id ON clients(site_id)

-- MAC address search
idx_clients_mac ON clients(mac)

-- Status and health filtering (partial indexes)
idx_clients_status ON clients(status) WHERE status IS NOT NULL AND status != 'REMOVED'
idx_clients_health ON clients(health) WHERE health IS NOT NULL

-- Device connection lookup
idx_clients_connected_device ON clients(connected_device_serial)
  WHERE connected_device_serial IS NOT NULL

-- Time-based queries
idx_clients_last_seen ON clients(last_seen_at DESC NULLS LAST)

-- Composite index for filtered listing
idx_clients_site_status_health ON clients(site_id, status, health)
  WHERE status != 'REMOVED'

-- Full-text search on names
idx_clients_name_trgm ON clients USING gin(name gin_trgm_ops)

-- JSONB advanced queries
idx_clients_raw_data ON clients USING gin(raw_data jsonb_path_ops)

-- Firmware status
idx_devices_firmware_status ON devices(firmware_upgrade_status)
  WHERE firmware_upgrade_status IS NOT NULL
```

---

## Agent Chatbot Relationships & Special Features

> **Schema Files:** [004_agent_chatbot.sql](./migrations/004_agent_chatbot.sql), [006_agentdb_memory_patterns.sql](./migrations/006_agentdb_memory_patterns.sql) | **Visual:** [ER_DIAGRAM.md](./ER_DIAGRAM.md#agent-chatbot-relationships)

The agent chatbot system uses a sophisticated multi-table architecture with **pgvector semantic search**, **Row-Level Security (RLS)** for multi-tenancy, and **background embedding generation**. This section explains the core relationships and advanced features.

### Architecture Overview

```
agent_conversations (1) ←→ (M) agent_messages
                ↓                     ↓
           tenant_id            tenant_id (RLS)
                               embedding vector(3072)
                                     ↓
                            agent_embedding_jobs (queue)

agent_memory ←→ agent_memory_revisions (versioning)
     ↓
tenant_id (RLS)
embedding vector(3072)

agent_sessions (persistent state)
agent_patterns (learned patterns)
agent_audit_log (write operations)
```

### 1. Conversation → Messages Hierarchy

The **agent_conversations** and **agent_messages** tables implement a **one-to-many parent-child relationship** with automatic message counting and cascading deletes.

**Schema:**
```sql
-- Parent: Conversations (chat sessions)
agent_conversations (
  id UUID PRIMARY KEY,
  tenant_id TEXT NOT NULL,              -- Multi-tenancy isolation
  user_id TEXT NOT NULL,                -- User who owns this conversation
  title TEXT,
  summary TEXT,                         -- Auto-generated summary for long conversations
  message_count INTEGER DEFAULT 0,      -- Maintained by trigger
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'
)

-- Child: Messages (individual chat messages)
agent_messages (
  id UUID PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,              -- Denormalized for RLS performance
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
  content TEXT NOT NULL,

  -- Chain of Thought: ONLY redacted summary, never raw reasoning
  thinking_summary TEXT,

  -- Tool calls with correlation IDs
  tool_calls JSONB,                     -- [{tool_call_id, name, arguments, result}]

  -- Embeddings for semantic search
  embedding vector(3072),               -- Max dimension for multi-provider support
  embedding_model TEXT,                 -- e.g., 'text-embedding-3-large'
  embedding_dimension INTEGER,          -- Actual dimension used
  embedding_status TEXT DEFAULT 'pending',

  -- Model and performance metadata
  model_used TEXT,
  tokens_used INTEGER,
  latency_ms INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
)
```

**Key Points:**
- **Cascading Deletes:** Deleting a conversation automatically deletes all its messages
- **Message Count Trigger:** `message_count` is maintained automatically by `agent_update_conversation_count()` trigger
- **Denormalized tenant_id:** Messages store `tenant_id` from their parent conversation for RLS performance
- **Chain of Thought Security:** Only redacted `thinking_summary` is stored; raw CoT is NEVER persisted
- **Tool Call Tracking:** All tool invocations are logged in JSONB with correlation IDs for debugging

**Example Query: Get Full Conversation Thread**
```sql
SELECT
  c.id as conversation_id,
  c.title,
  c.message_count,
  m.id as message_id,
  m.role,
  m.content,
  m.thinking_summary,
  m.tool_calls,
  m.created_at
FROM agent_conversations c
LEFT JOIN agent_messages m ON c.id = m.conversation_id
WHERE c.tenant_id = 'acme-corp'
  AND c.user_id = 'user-123'
ORDER BY c.created_at DESC, m.created_at ASC
LIMIT 100;
```

---

### 2. Memory System with Semantic Search

The **agent_memory** table provides **long-term persistent memory** with semantic search capabilities using **pgvector**. Memories are categorized, deduplicated, and have confidence scores that decay over time.

**Schema:**
```sql
agent_memory (
  id UUID PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  memory_type TEXT NOT NULL CHECK (memory_type IN ('fact', 'preference', 'entity', 'procedure')),
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,           -- SHA-256 for deduplication

  -- Embeddings for semantic search
  embedding vector(3072),
  embedding_model TEXT,
  embedding_dimension INTEGER,

  -- Usage and relevance tracking
  access_count INTEGER DEFAULT 0,
  last_accessed_at TIMESTAMPTZ,

  -- Source tracking (optional)
  source_conversation_id UUID REFERENCES agent_conversations(id) ON DELETE SET NULL,
  source_message_id UUID REFERENCES agent_messages(id) ON DELETE SET NULL,

  -- Lifecycle management
  valid_from TIMESTAMPTZ DEFAULT NOW(),
  valid_until TIMESTAMPTZ,              -- NULL = forever valid
  confidence FLOAT DEFAULT 1.0,         -- Decays for unused memories
  is_invalidated BOOLEAN DEFAULT FALSE, -- Soft delete

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}',

  UNIQUE(tenant_id, user_id, content_hash)
)
```

**Memory Types:**
- **fact:** Objective information (e.g., "User's office is in San Francisco")
- **preference:** User preferences (e.g., "User prefers detailed responses")
- **entity:** Named entities (e.g., "John Smith is the IT director")
- **procedure:** How-to knowledge (e.g., "To restart device, run command X")

**Key Points:**
- **Deduplication:** SHA-256 hash prevents duplicate memories within tenant+user scope
- **Confidence Decay:** Unused memories (30+ days) have confidence multiplied by 0.9 via `agent_memory_cleanup()` function
- **Soft Delete:** `is_invalidated` flag marks memories for deletion without immediate removal
- **Source Tracking:** Optional links back to originating conversation/message
- **TTL Support:** `valid_until` timestamp for time-limited memories

**Example Query: Semantic Memory Search**
```sql
-- Find similar memories using cosine similarity
-- Note: Searches use sequential scan due to vector(3072) dimension > 2000 pgvector limit
SELECT
  id,
  memory_type,
  content,
  confidence,
  access_count,
  1 - (embedding <=> '[0.1, 0.2, ...]'::vector) as similarity
FROM agent_memory
WHERE tenant_id = 'acme-corp'
  AND user_id = 'user-123'
  AND NOT is_invalidated
  AND (valid_until IS NULL OR valid_until > NOW())
  AND embedding_model = 'text-embedding-3-large'  -- Filter by model
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 10;
```

**Memory Lifecycle Management:**
```sql
-- Run periodically to maintain memory health
SELECT * FROM agent_memory_cleanup('acme-corp');
-- Returns: (invalidated_count, decayed_count, deleted_count)
-- 1. Invalidates expired memories (valid_until < NOW)
-- 2. Decays confidence for unused memories (30+ days)
-- 3. Hard deletes very old invalidated memories (90+ days)
```

---

### 3. pgvector Semantic Search

**pgvector** is a PostgreSQL extension that enables **semantic similarity search** using vector embeddings. All agent tables use **vector(3072)** columns to support multiple embedding models.

**Key Features:**
- **Multi-Provider Support:** Stores embeddings from OpenAI (`text-embedding-3-large`), Claude, or other models
- **Model Tracking:** `embedding_model` and `embedding_dimension` columns track which model generated each embedding
- **Similarity Operators:**
  - `<->` Euclidean distance (L2)
  - `<#>` Negative inner product
  - `<=>` **Cosine distance** (most common, used for semantic search)

**Why vector(3072)?**
- OpenAI's `text-embedding-3-large` produces 3072-dimensional embeddings
- Claude's embeddings may use different dimensions
- Flexible column size supports multiple providers without schema changes

**Index Limitation:**
```sql
-- pgvector's HNSW and IVFFlat indexes only support up to 2000 dimensions
-- Since our vector(3072) > 2000, we cannot create vector indexes
-- Sequential scan is used for similarity searches (fine for moderate data sizes)
-- For production with millions of messages, consider:
--   1. Using a separate vector(2000) column for indexed searches
--   2. Dimensionality reduction (PCA/UMAP)
--   3. External vector search engine (Pinecone, Weaviate)
```

**Example: Semantic Search with Model Filtering**
```sql
-- Search for similar messages, filtering by embedding model
WITH query_embedding AS (
  SELECT '[0.1, 0.2, ...]'::vector(3072) as vec
)
SELECT
  m.id,
  m.content,
  m.embedding_model,
  1 - (m.embedding <=> q.vec) as similarity
FROM agent_messages m, query_embedding q
WHERE m.tenant_id = 'acme-corp'
  AND m.conversation_id = 'conv-abc'
  AND m.embedding_status = 'completed'
  AND m.embedding_model = 'text-embedding-3-large'  -- CRITICAL: filter by model
ORDER BY m.embedding <=> q.vec
LIMIT 5;
```

---

### 4. Embedding Job Queue

The **agent_embedding_jobs** table implements a **background job queue** for asynchronous embedding generation. Workers use the **SKIP LOCKED** pattern for concurrent processing without conflicts.

**Schema:**
```sql
agent_embedding_jobs (
  id UUID PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  target_table TEXT NOT NULL CHECK (target_table IN ('agent_messages', 'agent_memory')),
  target_id UUID NOT NULL,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead')),
  retries INTEGER DEFAULT 0,
  max_retries INTEGER DEFAULT 3,
  error_message TEXT,
  locked_at TIMESTAMPTZ,                -- For SKIP LOCKED pattern
  locked_by TEXT,                       -- Worker ID for debugging
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ,

  UNIQUE(target_table, target_id)       -- Prevent duplicate jobs
)
```

**Job States:**
- **pending:** Waiting for worker to pick up
- **processing:** Currently being processed by a worker
- **completed:** Successfully processed
- **failed:** Processing failed, will retry
- **dead:** Max retries exceeded, manual intervention needed

**Automatic Job Creation:**
```sql
-- Triggers automatically create jobs when new messages/memories are inserted
CREATE TRIGGER agent_messages_embedding_trigger
  AFTER INSERT ON agent_messages
  FOR EACH ROW
  EXECUTE FUNCTION agent_queue_embedding_job();

CREATE TRIGGER agent_memory_embedding_trigger
  AFTER INSERT ON agent_memory
  FOR EACH ROW
  EXECUTE FUNCTION agent_queue_memory_embedding_job();
```

**Worker Pattern: Claim and Process Jobs**
```sql
-- Worker claims a job using SKIP LOCKED (prevents conflicts)
UPDATE agent_embedding_jobs
SET
  status = 'processing',
  locked_at = NOW(),
  locked_by = 'worker-1234'
WHERE id = (
  SELECT id
  FROM agent_embedding_jobs
  WHERE status = 'pending'
    AND tenant_id = 'acme-corp'
  ORDER BY created_at ASC
  FOR UPDATE SKIP LOCKED  -- Critical: allows concurrent workers
  LIMIT 1
)
RETURNING *;

-- After processing, update status
UPDATE agent_embedding_jobs
SET
  status = 'completed',
  processed_at = NOW()
WHERE id = :job_id;

-- On failure, increment retries
UPDATE agent_embedding_jobs
SET
  status = CASE WHEN retries + 1 >= max_retries THEN 'dead' ELSE 'failed' END,
  retries = retries + 1,
  error_message = :error
WHERE id = :job_id;
```

**Monitoring Queue Health:**
```sql
-- View queue status by tenant and target table
SELECT * FROM agent_embedding_queue_status;

-- Returns:
-- tenant_id | target_table    | status      | count | oldest_job | newest_job
-- acme-corp | agent_messages  | pending     | 42    | 2026-01-12 | 2026-01-13
-- acme-corp | agent_messages  | completed   | 9384  | 2026-01-01 | 2026-01-13
-- acme-corp | agent_memory    | failed      | 3     | 2026-01-12 | 2026-01-13
```

---

### 5. Row-Level Security (RLS) for Multi-Tenancy

**All agent tables** use **Row-Level Security (RLS)** to enforce **tenant isolation** at the database level. This provides defense-in-depth security beyond application-level checks.

**How RLS Works:**
```sql
-- 1. Application sets tenant context before queries
SET app.tenant_id = 'acme-corp';

-- 2. RLS policies automatically filter all queries
SELECT * FROM agent_conversations;  -- Only returns acme-corp conversations

-- 3. Policies enforce both reads (USING) and writes (WITH CHECK)
CREATE POLICY agent_conversations_tenant_isolation ON agent_conversations
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
```

**Tables with RLS Enabled:**
- `agent_conversations`
- `agent_messages` (with denormalized `tenant_id` for performance)
- `agent_memory`
- `agent_embedding_jobs`
- `agent_audit_log`
- `agent_sessions`
- `agent_patterns`
- `agent_memory_revisions`

**Performance Considerations:**
- **Denormalized tenant_id:** `agent_messages.tenant_id` is copied from parent conversation to avoid joins in RLS checks
- **Indexed tenant_id:** All RLS tables have indexes on `tenant_id` for fast filtering
- **Current Setting Caching:** `current_setting('app.tenant_id', true)` is evaluated once per query

**Example: Application Usage**
```python
# Python example with asyncpg
async with pool.acquire() as conn:
    # Set tenant context for this connection
    await conn.execute("SET app.tenant_id = $1", tenant_id)

    # All subsequent queries are automatically filtered
    conversations = await conn.fetch("SELECT * FROM agent_conversations")
    # Only returns conversations for the set tenant
```

**Security Benefits:**
- **Defense in Depth:** Even if application code has bugs, database enforces isolation
- **Audit-Friendly:** RLS policies are visible in schema and audit logs
- **Zero Trust:** No trust in application layer to filter data correctly

---

### 6. Audit Logging for Write Operations

The **agent_audit_log** table tracks **all write operations** performed by the agent chatbot, providing a complete audit trail with idempotency support.

**Schema:**
```sql
agent_audit_log (
  id UUID PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,                 -- e.g., 'add_device', 'assign_subscription'
  resource_type TEXT,                   -- e.g., 'device', 'subscription'
  resource_id TEXT,                     -- ID of affected resource
  payload JSONB,                        -- Request payload
  result JSONB,                         -- Response/result
  status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed', 'conflict')),
  error_message TEXT,
  idempotency_key TEXT,                 -- For retry safety
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,

  UNIQUE(tenant_id, idempotency_key)    -- Prevent duplicate operations
)
```

**Audit Log States:**
- **pending:** Operation started but not completed
- **completed:** Successfully completed
- **failed:** Operation failed (error logged in `error_message`)
- **conflict:** Idempotency key conflict (duplicate request)

**Idempotency Support:**
```sql
-- Client provides idempotency key for retry safety
INSERT INTO agent_audit_log (
  tenant_id,
  user_id,
  action,
  resource_type,
  payload,
  status,
  idempotency_key
) VALUES (
  'acme-corp',
  'user-123',
  'assign_subscription',
  'device',
  '{"device_id": "dev-abc", "subscription_id": "sub-xyz"}',
  'pending',
  'req-20260113-001'
)
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
RETURNING *;

-- If conflict, return existing result
SELECT * FROM agent_audit_log
WHERE tenant_id = 'acme-corp'
  AND idempotency_key = 'req-20260113-001';
```

**Example Query: View User's Operation History**
```sql
SELECT
  action,
  resource_type,
  resource_id,
  status,
  created_at,
  completed_at,
  (completed_at - created_at) as duration
FROM agent_audit_log
WHERE tenant_id = 'acme-corp'
  AND user_id = 'user-123'
ORDER BY created_at DESC
LIMIT 50;
```

---

### 7. Advanced Features

#### 7.1 Persistent Sessions (AgentDB Pattern)

The **agent_sessions** table provides **persistent state storage** that survives server restarts and supports multi-instance deployments.

**Schema:**
```sql
agent_sessions (
  id UUID PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  session_type TEXT NOT NULL CHECK (session_type IN ('confirmation', 'operation', 'context', 'cache')),
  key TEXT NOT NULL,                    -- Unique key within session type
  data JSONB NOT NULL DEFAULT '{}',
  expires_at TIMESTAMPTZ,               -- NULL = no expiration
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(tenant_id, user_id, session_type, key)
)
```

**Session Types:**
- **confirmation:** Pending operations awaiting user confirmation
- **operation:** In-flight operation state
- **context:** Conversation context and working memory
- **cache:** Temporary cached data

**Example: Store Pending Confirmation**
```sql
INSERT INTO agent_sessions (tenant_id, user_id, session_type, key, data, expires_at)
VALUES (
  'acme-corp',
  'user-123',
  'confirmation',
  'conv-abc:op-assign-device',
  '{"device_id": "dev-123", "subscription_id": "sub-456", "confirmed": false}',
  NOW() + INTERVAL '15 minutes'
)
ON CONFLICT (tenant_id, user_id, session_type, key)
DO UPDATE SET data = EXCLUDED.data, updated_at = NOW();
```

**Cleanup Expired Sessions:**
```sql
SELECT agent_cleanup_expired_sessions('acme-corp');
-- Returns count of deleted sessions
```

#### 7.2 Pattern Learning

The **agent_patterns** table stores **successful interaction patterns** for future retrieval and application.

**Schema:**
```sql
agent_patterns (
  id UUID PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  pattern_type TEXT NOT NULL CHECK (pattern_type IN ('tool_success', 'query_response', 'error_recovery', 'workflow')),
  trigger_text TEXT NOT NULL,
  trigger_hash TEXT NOT NULL,           -- SHA-256 for deduplication
  trigger_embedding vector(3072),       -- For semantic pattern matching
  response TEXT NOT NULL,
  context JSONB DEFAULT '{}',
  success_count INTEGER DEFAULT 1,
  failure_count INTEGER DEFAULT 0,
  confidence FLOAT DEFAULT 1.0,         -- success_count / (success + failure)
  last_used_at TIMESTAMPTZ,
  is_active BOOLEAN DEFAULT TRUE,

  UNIQUE(tenant_id, trigger_hash)
)
```

**Pattern Types:**
- **tool_success:** Successful tool call patterns
- **query_response:** Q&A patterns
- **error_recovery:** Error handling patterns
- **workflow:** Multi-step workflow patterns

**Example: Record Successful Pattern**
```sql
INSERT INTO agent_patterns (tenant_id, pattern_type, trigger_text, trigger_hash, response, context)
VALUES (
  'acme-corp',
  'tool_success',
  'find devices without subscriptions',
  encode(sha256('tool_success:find devices without subscriptions'), 'hex'),
  'Use get_devices_without_subscriptions tool',
  '{"tool": "get_devices_without_subscriptions", "args": {}}'
)
ON CONFLICT (tenant_id, trigger_hash)
DO UPDATE SET
  success_count = agent_patterns.success_count + 1,
  confidence = (agent_patterns.success_count + 1.0) / (agent_patterns.success_count + agent_patterns.failure_count + 1.0),
  last_used_at = NOW();
```

#### 7.3 Memory Versioning

The **agent_memory_revisions** table tracks **changes to memories** over time for correction and audit.

**Schema:**
```sql
agent_memory_revisions (
  id UUID PRIMARY KEY,
  memory_id UUID NOT NULL REFERENCES agent_memory(id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  version_state TEXT NOT NULL CHECK (version_state IN ('current', 'superseded', 'corrected', 'merged')),
  content TEXT NOT NULL,
  previous_content TEXT,
  change_reason TEXT,
  changed_by TEXT,                      -- User who made the change (null = system)
  confidence FLOAT DEFAULT 1.0,
  created_at TIMESTAMPTZ DEFAULT NOW()
)

-- Each memory can have only one current version
CREATE UNIQUE INDEX idx_agent_memory_revisions_unique_current
  ON agent_memory_revisions(memory_id)
  WHERE version_state = 'current';
```

**Version States:**
- **current:** Active version
- **superseded:** Replaced by newer version
- **corrected:** User-corrected version
- **merged:** Combined from multiple memories

---

### 8. Query Patterns

#### Get Conversation with Semantic Context
```sql
-- Get conversation with semantically similar past messages
WITH current_conversation AS (
  SELECT id, tenant_id FROM agent_conversations WHERE id = 'conv-abc'
),
query_embedding AS (
  SELECT embedding FROM agent_messages
  WHERE id = (SELECT MAX(id) FROM agent_messages WHERE conversation_id = 'conv-abc')
)
SELECT
  m.id,
  m.role,
  m.content,
  c.title,
  1 - (m.embedding <=> q.embedding) as similarity
FROM agent_messages m
JOIN agent_conversations c ON m.conversation_id = c.id
JOIN current_conversation cc ON m.tenant_id = cc.tenant_id
CROSS JOIN query_embedding q
WHERE m.embedding_status = 'completed'
  AND m.embedding IS NOT NULL
  AND m.conversation_id != 'conv-abc'  -- Exclude current conversation
ORDER BY m.embedding <=> q.embedding
LIMIT 10;
```

#### Get Active Memories for User
```sql
SELECT
  id,
  memory_type,
  content,
  confidence,
  access_count,
  last_accessed_at,
  EXTRACT(EPOCH FROM (NOW() - last_accessed_at))/86400 as days_since_access
FROM agent_memory
WHERE tenant_id = 'acme-corp'
  AND user_id = 'user-123'
  AND NOT is_invalidated
  AND (valid_until IS NULL OR valid_until > NOW())
  AND confidence > 0.5
ORDER BY confidence DESC, access_count DESC
LIMIT 20;
```

#### Monitor Embedding Queue Backlog
```sql
SELECT
  tenant_id,
  target_table,
  COUNT(*) FILTER (WHERE status = 'pending') as pending_jobs,
  COUNT(*) FILTER (WHERE status = 'failed') as failed_jobs,
  COUNT(*) FILTER (WHERE status = 'dead') as dead_jobs,
  MIN(created_at) FILTER (WHERE status = 'pending') as oldest_pending,
  AVG(EXTRACT(EPOCH FROM (processed_at - created_at))) FILTER (WHERE status = 'completed') as avg_processing_seconds
FROM agent_embedding_jobs
GROUP BY tenant_id, target_table
ORDER BY pending_jobs DESC;
```

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

> **See Also:** [ER_DIAGRAM.md - Indexing Strategy](./ER_DIAGRAM.md#indexing-strategy) for index overview

### 1. Index Usage Guide

This section provides a comprehensive overview of all database indexes, when to use different index types, and best practices for optimal query performance.

#### Overview of All Indexes

The database uses three types of indexes:
- **B-tree indexes** (default) - For exact matches, range queries, sorting
- **GIN indexes** (Generalized Inverted Index) - For full-text search, JSONB, arrays
- **Partial indexes** - Index subset of rows matching a condition

**Devices Table Indexes:**

```sql
-- B-tree Indexes (Standard)
idx_devices_serial              -- serial_number (unique lookups)
idx_devices_mac                 -- mac_address (unique lookups)
idx_devices_type                -- device_type (categorical filtering)
idx_devices_region              -- region (categorical filtering)
idx_devices_assigned            -- assigned_state (categorical filtering)
idx_devices_updated             -- updated_at DESC (recent updates)
idx_devices_created             -- created_at DESC (recent additions)
idx_devices_application         -- application_id (foreign key)
idx_devices_location            -- location_id (foreign key)
idx_devices_location_country    -- location_country (geographic filtering)
idx_devices_location_city       -- location_city (geographic filtering)
idx_devices_tenant              -- tenant_workspace_id (multi-tenancy)
idx_devices_dedicated_platform  -- dedicated_platform_id (platform filtering)

-- B-tree Partial Indexes
idx_devices_archived            -- WHERE archived = false (only active devices)

-- GIN Indexes (Full-text & JSONB)
idx_devices_search              -- search_vector (full-text search)
idx_devices_raw                 -- raw_data jsonb_path_ops (JSONB containment @>)
idx_devices_subscriptions       -- raw_data->'subscription' (subscription array queries)
idx_devices_tags                -- raw_data->'tags' (tag existence/value queries)

-- Aruba Central Indexes
idx_devices_central_id          -- central_device_id (Aruba Central UUID)
idx_devices_central_status      -- central_status (device status)
idx_devices_central_site_id     -- central_site_id (site filtering)
idx_devices_central_model       -- central_model (partial, only non-null)
idx_devices_central_last_seen   -- central_last_seen_at DESC (partial, only non-null)
idx_devices_central_config_status -- central_config_status (partial, only non-null)
idx_devices_central_only        -- WHERE central_device_id IS NOT NULL AND id IS NULL
idx_devices_greenlake_only      -- WHERE id IS NOT NULL AND central_device_id IS NULL
idx_devices_both_platforms      -- WHERE id IS NOT NULL AND central_device_id IS NOT NULL
idx_devices_last_seen_central   -- central_last_seen_at DESC (time-based queries)

-- Firmware Indexes
idx_devices_firmware_status     -- firmware_upgrade_status (partial, only non-null)
idx_devices_firmware_synced     -- firmware_synced_at (partial, only non-null)
```

**Subscriptions Table Indexes:**

```sql
-- B-tree Indexes (Standard)
idx_subscriptions_key           -- key (unique lookups)
idx_subscriptions_type          -- subscription_type (categorical)
idx_subscriptions_status        -- subscription_status (categorical)
idx_subscriptions_tier          -- tier (categorical)
idx_subscriptions_product_type  -- product_type (categorical)
idx_subscriptions_is_eval       -- is_eval (boolean)
idx_subscriptions_end_time      -- end_time (expiration queries)
idx_subscriptions_start_time    -- start_time (activation queries)

-- B-tree Composite & Covering Indexes
idx_subscriptions_expiring      -- (subscription_status, end_time) WHERE subscription_status = 'STARTED'
idx_subscriptions_expiring_covering  -- Covering: end_time, key, subscription_type, tier, sku, quantity, available_quantity
                                     -- WHERE subscription_status = 'STARTED' (index-only scan)

-- GIN Indexes (Full-text & JSONB)
idx_subscriptions_search        -- search_vector (full-text search)
idx_subscriptions_raw           -- raw_data jsonb_path_ops (JSONB containment)
idx_subscriptions_tags          -- raw_data->'tags' (tag queries)
```

**Junction & Tag Tables:**

```sql
-- device_subscriptions (many-to-many)
PRIMARY KEY (device_id, subscription_id)  -- Composite primary key (clustered index)
idx_device_subscriptions_sub              -- subscription_id (reverse lookups)

-- device_tags
PRIMARY KEY (device_id, tag_key)          -- Composite primary key
idx_device_tags_key                       -- tag_key (find all devices with key)
idx_device_tags_key_value                 -- (tag_key, tag_value) (find devices by tag)
idx_device_tags_device                    -- device_id (get all tags for device)

-- subscription_tags
PRIMARY KEY (subscription_id, tag_key)
idx_subscription_tags_key
idx_subscription_tags_key_value
idx_subscription_tags_subscription
```

**Network Clients & Sites Indexes:**

```sql
-- sites
PRIMARY KEY (site_id)
idx_sites_name                  -- site_name (search by name)
idx_sites_last_synced           -- last_synced_at DESC (recent syncs)

-- clients
PRIMARY KEY (id)                -- Auto-increment BIGINT
UNIQUE (site_id, mac)           -- One MAC per site
idx_clients_site_id             -- site_id (get all clients for site)
idx_clients_mac                 -- mac (MAC address lookups)
idx_clients_connected_device    -- connected_device_serial (partial, only non-null)
idx_clients_last_seen           -- last_seen_at DESC NULLS LAST
idx_clients_synced_at           -- synced_at
idx_clients_name_trgm           -- GIN trigram for fuzzy name search
idx_clients_raw_data            -- GIN JSONB for advanced queries

-- Partial Indexes (only active clients)
idx_clients_status              -- WHERE status IS NOT NULL AND status != 'REMOVED'
idx_clients_health              -- WHERE health IS NOT NULL
idx_clients_type                -- WHERE type IS NOT NULL

-- Composite Partial Index
idx_clients_site_status_health  -- (site_id, status, health) WHERE status != 'REMOVED'
```

**Agent Chatbot Indexes:**

```sql
-- agent_conversations
PRIMARY KEY (id)
idx_agent_conversations_tenant_user  -- (tenant_id, user_id) (RLS filtering)

-- agent_messages
PRIMARY KEY (id)
idx_agent_messages_conversation      -- conversation_id (get messages for conversation)
idx_agent_messages_embedding_status  -- embedding_status (find pending embeddings)
idx_agent_messages_tenant            -- tenant_id (RLS filtering)
idx_agent_messages_tenant_conversation -- (tenant_id, conversation_id) (optimized RLS join)

-- agent_memory
PRIMARY KEY (id)
UNIQUE (tenant_id, user_id, content_hash)  -- Deduplication
idx_agent_memory_tenant_user        -- (tenant_id, user_id)
idx_agent_memory_ttl                -- valid_until (expiration cleanup)
idx_agent_memory_confidence         -- confidence (high-confidence memories)
idx_agent_memory_invalidated        -- is_invalidated (exclude invalidated)
idx_agent_memory_last_accessed      -- last_accessed_at (confidence decay)

-- agent_embedding_jobs (background queue)
PRIMARY KEY (id)
UNIQUE (target_table, target_id)    -- Prevent duplicate jobs
idx_agent_embedding_jobs_pending    -- WHERE status = 'pending' (worker queue)
idx_agent_embedding_jobs_status     -- status (monitoring)
idx_agent_embedding_jobs_locked     -- locked_at (stale job detection)

-- agent_audit_log
PRIMARY KEY (id)
UNIQUE (tenant_id, idempotency_key) -- Idempotency
idx_agent_audit_tenant_user         -- (tenant_id, user_id)
idx_agent_audit_idempotency         -- idempotency_key
idx_agent_audit_status              -- status

-- agent_sessions (persistent state)
PRIMARY KEY (id)
UNIQUE (tenant_id, user_id, session_type, key)
idx_agent_sessions_lookup           -- (tenant_id, user_id, session_type, key)
idx_agent_sessions_expiry           -- expires_at (cleanup)
idx_agent_sessions_type             -- session_type

-- agent_patterns (learned patterns)
PRIMARY KEY (id)
UNIQUE (tenant_id, trigger_hash)
idx_agent_patterns_type_confidence  -- (pattern_type, confidence DESC)
idx_agent_patterns_active           -- WHERE is_active = true

-- agent_memory_revisions (versioning)
PRIMARY KEY (id)
idx_agent_memory_revisions_unique_current  -- UNIQUE (memory_id) WHERE version_state = 'current'
idx_agent_memory_revisions_memory          -- memory_id (get all revisions)
idx_agent_memory_revisions_current         -- WHERE version_state = 'current'
idx_agent_memory_revisions_user            -- (tenant_id, user_id)
```

**Sync History:**

```sql
-- sync_history
PRIMARY KEY (id)
idx_sync_history_resource_type  -- resource_type (devices vs subscriptions)
idx_sync_history_started        -- started_at DESC (recent syncs)
```

---

#### When to Use GIN vs B-tree Indexes

**Use B-tree Indexes (Default) When:**

1. **Exact Match Queries**
   ```sql
   -- ✅ B-tree: Exact serial number lookup
   SELECT * FROM devices WHERE serial_number = 'VNT9KWC01V';
   ```

2. **Range Queries**
   ```sql
   -- ✅ B-tree: Date range queries
   SELECT * FROM subscriptions
   WHERE end_time BETWEEN '2026-01-01' AND '2026-12-31';
   ```

3. **Sorting and ORDER BY**
   ```sql
   -- ✅ B-tree: Can use idx_devices_updated for sorting
   SELECT * FROM devices
   ORDER BY updated_at DESC
   LIMIT 50;
   ```

4. **Foreign Keys and Joins**
   ```sql
   -- ✅ B-tree: Fast join on device_id
   SELECT d.*, s.*
   FROM devices d
   JOIN device_subscriptions ds ON d.id = ds.device_id
   JOIN subscriptions s ON ds.subscription_id = s.id;
   ```

5. **Prefix Matching (with LIKE pattern%)**
   ```sql
   -- ✅ B-tree: Can use idx_devices_serial for prefix
   SELECT * FROM devices
   WHERE serial_number LIKE 'VNT9%';
   ```

**Use GIN Indexes When:**

1. **Full-Text Search**
   ```sql
   -- ✅ GIN: idx_devices_search for full-text search
   SELECT * FROM devices
   WHERE search_vector @@ websearch_to_tsquery('english', 'aruba 6200');
   ```

2. **JSONB Containment Queries (@>)**
   ```sql
   -- ✅ GIN: idx_devices_raw (jsonb_path_ops) for containment
   SELECT * FROM devices
   WHERE raw_data @> '{"archived": false, "device_type": "SWITCH"}';
   ```

3. **JSONB Key Existence (?, ?|, ?&)**
   ```sql
   -- ✅ GIN: idx_devices_tags for tag key existence
   SELECT * FROM devices
   WHERE raw_data->'tags' ? 'customer';

   -- ✅ GIN: Check for any of multiple keys
   SELECT * FROM devices
   WHERE raw_data->'tags' ?| array['customer', 'site', 'region'];
   ```

4. **Array Operations**
   ```sql
   -- ✅ GIN: For array contains/overlap queries (if using arrays)
   SELECT * FROM table WHERE tags @> ARRAY['production'];
   ```

5. **Trigram Fuzzy Search (pg_trgm)**
   ```sql
   -- ✅ GIN: idx_clients_name_trgm for fuzzy name search
   SELECT * FROM clients
   WHERE name ILIKE '%iphone%';
   ```

**Index Type Comparison:**

| Feature | B-tree | GIN |
|---------|--------|-----|
| Exact match | ✅ Excellent | ✅ Good |
| Range queries | ✅ Excellent | ❌ Not supported |
| Sorting | ✅ Excellent | ❌ Not supported |
| Full-text search | ❌ Not supported | ✅ Excellent |
| JSONB containment | ❌ Not supported | ✅ Excellent |
| Array operations | ❌ Not supported | ✅ Excellent |
| Index size | Smaller | Larger |
| Update performance | Faster | Slower |
| Prefix match (LIKE 'x%') | ✅ Good | ❌ Not supported |
| Suffix match (LIKE '%x') | ❌ Not supported | ✅ With trigrams |

---

#### JSONB Query Optimization

**1. Use `jsonb_path_ops` for Containment Queries**

Our indexes use `jsonb_path_ops` which is optimized for `@>` (containment) but **not** for key existence (`?`).

```sql
-- ✅ FAST: Uses idx_devices_raw (jsonb_path_ops)
SELECT * FROM devices
WHERE raw_data @> '{"device_type": "SWITCH"}';

-- ⚠️ SLOWER: jsonb_path_ops doesn't support ? operator efficiently
-- Uses sequential scan or different index
SELECT * FROM devices
WHERE raw_data ? 'device_type';
```

**2. Use Dedicated Nested Path Indexes**

For frequently queried nested paths, we have dedicated GIN indexes:

```sql
-- ✅ FAST: Uses idx_devices_tags (dedicated GIN on raw_data->'tags')
SELECT * FROM devices
WHERE raw_data->'tags' ? 'customer';

-- ✅ FAST: Uses idx_devices_subscriptions (dedicated GIN on raw_data->'subscription')
SELECT * FROM devices
WHERE raw_data->'subscription' @> '[{"tier": "FOUNDATION_AP"}]';
```

**3. Prefer Normalized Columns Over JSONB**

Always use normalized columns when available - they're faster and more predictable:

```sql
-- ✅ EXCELLENT: Uses B-tree idx_devices_type
SELECT * FROM devices WHERE device_type = 'SWITCH';

-- ❌ SLOWER: JSONB query even with GIN index
SELECT * FROM devices WHERE raw_data->>'device_type' = 'SWITCH';
```

**4. JSONB Operator Best Practices**

```sql
-- ✅ Use @> for containment (uses jsonb_path_ops index)
WHERE raw_data @> '{"key": "value"}'

-- ✅ Use -> for extraction (returns JSONB)
WHERE (raw_data->'subscription'->>0->>'tier') = 'FOUNDATION_AP'

-- ✅ Use ->> for text extraction
WHERE raw_data->>'device_name' = 'Switch-01'

-- ❌ AVOID: Functions on indexed columns prevent index usage
WHERE LOWER(raw_data->>'device_name') = 'switch-01'

-- ✅ BETTER: Store normalized lowercase or use expression index
WHERE raw_data->>'device_name' = 'switch-01'  -- If data is already normalized
```

**5. JSONB Array Queries**

```sql
-- Extract and filter JSONB arrays
SELECT
  d.serial_number,
  sub->>'key' as subscription_key,
  sub->>'tier' as tier
FROM devices d,
     jsonb_array_elements(d.raw_data->'subscription') as sub
WHERE sub->>'tier' LIKE 'FOUNDATION%';

-- Check array length
SELECT * FROM devices
WHERE jsonb_array_length(raw_data->'subscription') > 0;

-- Containment in array
SELECT * FROM devices
WHERE raw_data->'subscription' @> '[{"key": "PAT4DYYJAEEEJA"}]';
```

---

#### Full-Text Search Best Practices

**1. Use `websearch_to_tsquery` for Natural Language**

```sql
-- ✅ RECOMMENDED: Natural language syntax (supports AND, OR, quotes)
SELECT * FROM devices
WHERE search_vector @@ websearch_to_tsquery('english', 'aruba 6200');

-- Supports natural operators:
-- 'aruba 6200'              → aruba AND 6200
-- 'aruba OR cisco'          → aruba OR cisco
-- '"access point"'          → exact phrase
-- 'switch -aruba'           → switch AND NOT aruba
-- '(aruba OR cisco) switch' → (aruba OR cisco) AND switch
```

**2. Use Ranking for Relevance Sorting**

```sql
-- ✅ Include ts_rank for relevance scoring
SELECT
  serial_number,
  device_name,
  device_type,
  ts_rank(search_vector, websearch_to_tsquery('english', 'aruba 6200')) as rank
FROM devices
WHERE search_vector @@ websearch_to_tsquery('english', 'aruba 6200')
  AND NOT archived
ORDER BY rank DESC
LIMIT 50;
```

**3. Use Weighted Search Vectors**

Our `search_vector` columns use weights (A, B, C) to prioritize different fields:

```sql
-- Devices search_vector weights:
-- A (highest): serial_number, device_name
-- B (medium):  mac_address, model
-- C (lowest):  device_type, region, location_city, location_country

-- This means matches in serial_number rank higher than matches in region
```

**4. Performance Optimization**

```sql
-- ✅ FAST: Indexed full-text search
SELECT * FROM search_devices('aruba 6200', 50);

-- ✅ FAST: Direct search_vector query
WHERE search_vector @@ websearch_to_tsquery('english', 'query')

-- ❌ SLOW: to_tsvector on-the-fly (no index)
WHERE to_tsvector('english', device_name) @@ to_tsquery('aruba')

-- ✅ Use the generated column instead
WHERE search_vector @@ websearch_to_tsquery('english', 'aruba')
```

**5. Combine Full-Text with Filters**

```sql
-- ✅ Filter first, then search (uses multiple indexes)
SELECT
  serial_number,
  device_name,
  ts_rank(search_vector, websearch_to_tsquery('english', 'switch')) as rank
FROM devices
WHERE device_type = 'SWITCH'              -- Uses idx_devices_type
  AND region = 'us-west'                  -- Uses idx_devices_region
  AND search_vector @@ websearch_to_tsquery('english', '6200')  -- Uses idx_devices_search
ORDER BY rank DESC;
```

**6. Trigram Search for Fuzzy Matching**

For fuzzy/partial name matching, use the `pg_trgm` GIN indexes:

```sql
-- ✅ FAST: Uses idx_clients_name_trgm (GIN trigram index)
SELECT * FROM clients
WHERE name ILIKE '%iphone%'
LIMIT 50;

-- Can also use similarity matching
SELECT
  name,
  similarity(name, 'iPhone') as sim
FROM clients
WHERE name % 'iPhone'  -- % operator = similar to
ORDER BY sim DESC
LIMIT 10;
```

---

#### pgvector Index Limitations & Best Practices

**Critical Limitation: 2000-Dimension Maximum**

pgvector's HNSW and IVFFlat indexes **only support up to 2000 dimensions**. Our schema uses `vector(3072)` to support OpenAI's `text-embedding-3-large` model, which means:

⚠️ **We CANNOT create vector indexes on our embedding columns**

```sql
-- ❌ FAILS: Dimension 3072 > 2000 limit
CREATE INDEX idx_agent_messages_embedding
ON agent_messages USING hnsw(embedding vector_cosine_ops);
-- ERROR: hnsw index does not support vector(3072)

-- ❌ FAILS: Same issue with IVFFlat
CREATE INDEX idx_agent_messages_embedding
ON agent_messages USING ivfflat(embedding vector_cosine_ops);
-- ERROR: ivfflat index does not support vector(3072)
```

**Current Behavior: Sequential Scans**

All semantic search queries use **sequential scans** (full table scans):

```sql
-- This query scans ALL rows in agent_messages
SELECT
  id,
  content,
  1 - (embedding <=> '[0.1, 0.2, ...]'::vector(3072)) as similarity
FROM agent_messages
WHERE tenant_id = 'acme-corp'
  AND conversation_id = 'conv-abc'
  AND embedding_status = 'completed'
  AND embedding_model = 'text-embedding-3-large'  -- CRITICAL: filter by model
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector(3072)
LIMIT 10;
```

**Performance Characteristics:**

| Data Size | Performance | Notes |
|-----------|-------------|-------|
| < 10,000 rows | ✅ Acceptable | Sequential scan is fast enough |
| 10,000 - 100,000 rows | ⚠️ Moderate | Noticeable latency (100-500ms) |
| > 100,000 rows | ❌ Slow | Consider alternatives |

**Optimization Strategies:**

**1. Filter Before Similarity Search**

Reduce the scan set with indexed filters:

```sql
-- ✅ GOOD: Filter first using indexed columns
SELECT
  id,
  content,
  1 - (embedding <=> $1::vector(3072)) as similarity
FROM agent_messages
WHERE tenant_id = 'acme-corp'              -- Uses idx_agent_messages_tenant
  AND conversation_id = 'conv-abc'         -- Uses idx_agent_messages_tenant_conversation
  AND embedding_status = 'completed'       -- Uses idx_agent_messages_embedding_status
  AND embedding_model = 'text-embedding-3-large'  -- Filter by model
  AND created_at > NOW() - INTERVAL '30 days'     -- Further reduce scan set
ORDER BY embedding <=> $1::vector(3072)
LIMIT 10;
```

**2. Partition by Tenant**

For multi-tenant deployments, consider table partitioning by `tenant_id` to isolate tenant data:

```sql
-- Each tenant gets a smaller table to scan
CREATE TABLE agent_messages PARTITION BY LIST (tenant_id);
CREATE TABLE agent_messages_acme PARTITION OF agent_messages FOR VALUES IN ('acme-corp');
CREATE TABLE agent_messages_globex PARTITION OF agent_messages FOR VALUES IN ('globex');
```

**3. Use Dual Embedding Strategy (Advanced)**

For production with millions of messages, consider storing **two embeddings**:

```sql
ALTER TABLE agent_messages
ADD COLUMN embedding_reduced vector(1536),  -- Reduced dimensions for indexing
ADD COLUMN embedding_dimension_reduced INTEGER;

-- Create index on reduced embedding
CREATE INDEX idx_agent_messages_embedding_reduced
ON agent_messages USING hnsw(embedding_reduced vector_cosine_ops);

-- Two-phase search:
-- 1. Fast approximate search with index (top 100)
-- 2. Precise re-ranking with full embedding (top 10)
WITH approximate_results AS (
  SELECT id, content, embedding
  FROM agent_messages
  WHERE tenant_id = 'acme-corp'
    AND embedding_reduced IS NOT NULL
  ORDER BY embedding_reduced <=> $1::vector(1536)
  LIMIT 100
)
SELECT
  id,
  content,
  1 - (embedding <=> $2::vector(3072)) as similarity
FROM approximate_results
ORDER BY embedding <=> $2::vector(3072)
LIMIT 10;
```

**4. External Vector Search Engine**

For very large deployments (millions of vectors), consider external vector databases:

- **Pinecone** - Managed vector database
- **Weaviate** - Open-source vector search engine
- **Qdrant** - High-performance vector database
- **Milvus** - Cloud-native vector database

Store only metadata in PostgreSQL, vectors in external engine.

**5. Dimensionality Reduction**

Use PCA, UMAP, or other techniques to reduce embeddings to ≤2000 dimensions:

```python
# Python example: Reduce 3072 → 1536 dimensions
from sklearn.decomposition import PCA

pca = PCA(n_components=1536)
reduced_embeddings = pca.fit_transform(full_embeddings)
```

**Best Practices:**

1. **Always Filter by `embedding_model`** - Don't compare embeddings from different models
2. **Use `embedding_status = 'completed'`** - Exclude pending/failed embeddings
3. **Limit Result Set** - Use `LIMIT` to stop scanning early
4. **Monitor Query Performance** - Use `EXPLAIN ANALYZE` to track scan times
5. **Consider Caching** - Cache frequently requested similarity results in Redis
6. **Batch Operations** - For bulk similarity searches, use batching to amortize overhead

**Vector Similarity Operators:**

```sql
-- Cosine distance (most common for semantic search)
-- Range: 0 (identical) to 2 (opposite)
ORDER BY embedding <=> query_vector

-- Euclidean distance (L2)
-- Range: 0 (identical) to infinity
ORDER BY embedding <-> query_vector

-- Negative inner product
-- Range: -infinity to +infinity
ORDER BY embedding <#> query_vector

-- Convert cosine distance to similarity (0-1 scale)
SELECT 1 - (embedding <=> query_vector) as similarity
```

**Memory Considerations:**

```sql
-- vector(3072) with FLOAT4 = 3072 * 4 bytes = 12.3 KB per embedding
-- 1 million messages = ~12.3 GB just for embeddings
-- Factor in PostgreSQL overhead: ~15-20 GB total

-- Monitor embedding storage
SELECT
  pg_size_pretty(pg_total_relation_size('agent_messages')) as total_size,
  COUNT(*) as message_count,
  COUNT(*) FILTER (WHERE embedding IS NOT NULL) as embeddings_count,
  pg_size_pretty(pg_total_relation_size('agent_messages') / NULLIF(COUNT(*), 0)) as avg_row_size
FROM agent_messages;
```

---

### 2. Use Indexes Wisely

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

## Schema Files Reference

The complete database schema is defined across multiple SQL files:

| File | Description | Documentation |
|------|-------------|---------------|
| [schema.sql](./schema.sql) | Core tables: devices, device_tags, device_subscriptions, sync_history, query_examples | [ER Diagram](./ER_DIAGRAM.md) |
| [subscriptions_schema.sql](./subscriptions_schema.sql) | Subscription tables: subscriptions, subscription_tags | [Core Relationships](#core-relationships) |
| [clients_migration.sql](./clients_migration.sql) | Aruba Central: sites, clients, firmware tracking | [Network Clients & Sites](#network-clients--sites-relationships) |
| [migrations/004_agent_chatbot.sql](./migrations/004_agent_chatbot.sql) | AI agent base: conversations, messages, memory, embeddings, audit | [Agent Chatbot](#agent-chatbot-relationships--special-features) |
| [migrations/006_agentdb_memory_patterns.sql](./migrations/006_agentdb_memory_patterns.sql) | AI agent advanced: sessions, patterns, memory revisions | [Agent Chatbot](#agent-chatbot-relationships--special-features) |
| [migrations/](./migrations/) | Database migration scripts for schema updates | - |

### Quick Setup

```bash
# Initialize database with all schemas (run in order)
psql $DATABASE_URL -f db/schema.sql
psql $DATABASE_URL -f db/subscriptions_schema.sql
psql $DATABASE_URL -f db/clients_migration.sql
psql $DATABASE_URL -f db/migrations/004_agent_chatbot.sql
psql $DATABASE_URL -f db/migrations/006_agentdb_memory_patterns.sql

# Or use Docker Compose (includes all schemas)
docker compose up -d postgres
```

---

## Additional Resources

- **Visual Documentation:**
  - [ER_DIAGRAM.md](./ER_DIAGRAM.md) - Entity relationship diagram with Mermaid visualization

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
  - [pgvector Extension](https://github.com/pgvector/pgvector)

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
