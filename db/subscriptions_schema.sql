-- HPE GreenLake Subscription Inventory Schema
-- PostgreSQL 16+
-- ============================================
-- SUBSCRIPTIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS subscriptions (
    -- Primary identifier (UUID from GreenLake API)
    id UUID PRIMARY KEY,
    
    -- Core fields
    key VARCHAR(100),
    resource_type VARCHAR(50),              -- e.g., "subscriptions/subscription"
    subscription_type VARCHAR(50),          -- CENTRAL_AP, CENTRAL_SWITCH, etc.
    subscription_status VARCHAR(20),        -- STARTED, ENDED, SUSPENDED, etc.
    
    -- Quantities
    quantity INTEGER,
    available_quantity INTEGER,
    
    -- SKU details
    sku VARCHAR(100),
    sku_description TEXT,
    
    -- Time range
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    
    -- Tier information
    tier VARCHAR(100),
    tier_description TEXT,
    
    -- Classification
    product_type VARCHAR(50),               -- DEVICE, SERVICE, etc.
    is_eval BOOLEAN DEFAULT FALSE,
    
    -- Order references
    contract VARCHAR(100),
    quote VARCHAR(100),
    po VARCHAR(100),
    reseller_po VARCHAR(100),               -- For indirect orders
    
    -- Timestamps from API
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    
    -- Our sync tracking
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Full API response for flexibility
    raw_data JSONB NOT NULL,
    
    -- Auto-generated full-text search vector
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(key, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(sku, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(sku_description, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(tier, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(contract, '')), 'C')
    ) STORED
);

-- ============================================
-- INDEXES
-- ============================================
-- Primary lookups
CREATE INDEX IF NOT EXISTS idx_subscriptions_key ON subscriptions(key);

-- Filter queries
CREATE INDEX IF NOT EXISTS idx_subscriptions_type ON subscriptions(subscription_type);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(subscription_status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tier ON subscriptions(tier);
CREATE INDEX IF NOT EXISTS idx_subscriptions_product_type ON subscriptions(product_type);
CREATE INDEX IF NOT EXISTS idx_subscriptions_is_eval ON subscriptions(is_eval);

-- Date range queries (critical for "expiring soon" queries)
CREATE INDEX IF NOT EXISTS idx_subscriptions_end_time ON subscriptions(end_time);
CREATE INDEX IF NOT EXISTS idx_subscriptions_start_time ON subscriptions(start_time);

-- Composite index for common expiration query
CREATE INDEX IF NOT EXISTS idx_subscriptions_expiring ON subscriptions(subscription_status, end_time)
WHERE subscription_status = 'STARTED';

-- Full-text search
CREATE INDEX IF NOT EXISTS idx_subscriptions_search ON subscriptions USING GIN(search_vector);

-- JSONB queries
CREATE INDEX IF NOT EXISTS idx_subscriptions_raw ON subscriptions USING GIN(raw_data jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tags ON subscriptions USING GIN((raw_data->'tags'));

-- ============================================
-- SUBSCRIPTION TAGS TABLE (normalized)
-- ============================================
CREATE TABLE IF NOT EXISTS subscription_tags (
    subscription_id UUID NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    tag_key VARCHAR(100) NOT NULL,
    tag_value VARCHAR(255),
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (subscription_id, tag_key)
);

CREATE INDEX IF NOT EXISTS idx_subscription_tags_key ON subscription_tags(tag_key);
CREATE INDEX IF NOT EXISTS idx_subscription_tags_key_value ON subscription_tags(tag_key, tag_value);

-- ============================================
-- USEFUL VIEWS
-- ============================================

-- Active subscriptions only
CREATE OR REPLACE VIEW active_subscriptions AS
SELECT 
    id, key, subscription_type, tier, sku,
    quantity, available_quantity,
    start_time, end_time,
    (end_time - NOW()) as time_remaining,
    raw_data->'tags' as tags
FROM subscriptions
WHERE subscription_status = 'STARTED';

-- Subscriptions expiring in next 90 days
CREATE OR REPLACE VIEW subscriptions_expiring_soon AS
SELECT 
    id, key, subscription_type, tier, sku,
    quantity, available_quantity,
    end_time,
    (end_time - NOW()) as time_remaining,
    DATE_PART('day', end_time - NOW()) as days_remaining
FROM subscriptions
WHERE subscription_status = 'STARTED'
  AND end_time > NOW()
  AND end_time < NOW() + INTERVAL '90 days'
ORDER BY end_time ASC;

-- Subscription summary by type and status
CREATE OR REPLACE VIEW subscription_summary AS
SELECT 
    subscription_type,
    subscription_status,
    COUNT(*) as total,
    SUM(quantity) as total_quantity,
    SUM(available_quantity) as total_available
FROM subscriptions
GROUP BY subscription_type, subscription_status
ORDER BY subscription_type, subscription_status;

-- ============================================
-- SYNC HISTORY (extend existing if present)
-- ============================================
-- Note: sync_history table already exists from devices schema
-- It can be used for subscription syncs as well by adding a 'resource_type' column
-- or keeping separate tracking
