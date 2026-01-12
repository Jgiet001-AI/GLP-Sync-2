-- Migration: 005_agent_messages_rls.sql
-- Description: Add tenant_id column and RLS policy to agent_messages table
-- Created: 2026-01-11
-- Security: Enforces tenant isolation at database level

-- ============================================
-- SAFETY CHECKS
-- ============================================

-- This migration should be run in a maintenance window
-- Backfill may lock the table temporarily on large datasets

-- ============================================
-- STEP 1: Add tenant_id column (nullable first)
-- ============================================

ALTER TABLE agent_messages
ADD COLUMN IF NOT EXISTS tenant_id TEXT;

COMMENT ON COLUMN agent_messages.tenant_id IS
    'Tenant identifier for RLS isolation. Denormalized from conversation for query performance.';

-- ============================================
-- STEP 2: Backfill tenant_id from conversations
-- ============================================

-- Single UPDATE for moderate-sized tables (recommended for most deployments)
-- For very large tables (1M+ rows), run this in batches using external scripting
UPDATE agent_messages m
SET tenant_id = c.tenant_id
FROM agent_conversations c
WHERE m.conversation_id = c.id
  AND m.tenant_id IS NULL;

-- ============================================
-- STEP 3: Handle orphaned messages
-- ============================================

-- Log any orphaned messages (conversation deleted but messages remain)
DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM agent_messages m
    LEFT JOIN agent_conversations c ON m.conversation_id = c.id
    WHERE c.id IS NULL;

    IF orphan_count > 0 THEN
        RAISE WARNING 'Found % orphaned messages without conversations', orphan_count;

        -- Delete orphans (they have no tenant context)
        DELETE FROM agent_messages
        WHERE conversation_id NOT IN (SELECT id FROM agent_conversations);
    END IF;
END $$;

-- ============================================
-- STEP 4: Make tenant_id NOT NULL
-- ============================================

-- Verify no nulls remain
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count FROM agent_messages WHERE tenant_id IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'Cannot set NOT NULL: % messages still have NULL tenant_id', null_count;
    END IF;
END $$;

ALTER TABLE agent_messages
ALTER COLUMN tenant_id SET NOT NULL;

-- ============================================
-- STEP 5: Add indexes for RLS performance
-- ============================================

-- Primary tenant isolation index
CREATE INDEX IF NOT EXISTS idx_agent_messages_tenant
ON agent_messages(tenant_id);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_agent_messages_tenant_conversation
ON agent_messages(tenant_id, conversation_id, created_at);

-- ============================================
-- STEP 6: Create RLS policy BEFORE enabling RLS
-- ============================================

-- Drop existing policy if any (for idempotency)
DROP POLICY IF EXISTS agent_messages_tenant_isolation ON agent_messages;

-- Create the isolation policy
CREATE POLICY agent_messages_tenant_isolation ON agent_messages
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ============================================
-- STEP 7: Enable RLS
-- ============================================

ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;

-- ============================================
-- STEP 8: Add foreign key constraint (optional but recommended)
-- ============================================

-- Check if constraint already exists before adding
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_agent_messages_conversation'
    ) THEN
        ALTER TABLE agent_messages
        ADD CONSTRAINT fk_agent_messages_conversation
        FOREIGN KEY (conversation_id)
        REFERENCES agent_conversations(id)
        ON DELETE CASCADE;
    END IF;
END $$;

-- ============================================
-- VERIFICATION
-- ============================================

-- Verify RLS is enabled
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE tablename = 'agent_messages'
        AND rowsecurity = true
    ) THEN
        RAISE EXCEPTION 'RLS not enabled on agent_messages';
    END IF;

    RAISE NOTICE 'Migration 005 completed successfully: RLS enabled on agent_messages';
END $$;
