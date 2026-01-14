-- SQL script to verify tenant isolation for search history
-- This script creates test data and verifies isolation at the database level

-- ============================================
-- SETUP: Clean up any existing test data
-- ============================================

DELETE FROM search_history WHERE tenant_id LIKE 'test-tenant-%';

-- ============================================
-- STEP 1: Create test data for multiple tenants and users
-- ============================================

-- Tenant A, User 1 (3 searches)
INSERT INTO search_history (tenant_id, user_id, query, search_type, result_count)
VALUES
    ('test-tenant-a', 'user-1', 'compute server', 'device', 5),
    ('test-tenant-a', 'user-1', 'storage device', 'device', 3),
    ('test-tenant-a', 'user-1', 'aruba subscription', 'subscription', 2);

-- Tenant A, User 2 (2 searches)
INSERT INTO search_history (tenant_id, user_id, query, search_type, result_count)
VALUES
    ('test-tenant-a', 'user-2', 'network switch', 'device', 8),
    ('test-tenant-a', 'user-2', 'aruba central', 'subscription', 4);

-- Tenant B, User 1 (2 searches)
INSERT INTO search_history (tenant_id, user_id, query, search_type, result_count)
VALUES
    ('test-tenant-b', 'user-1', 'backup device', 'device', 6),
    ('test-tenant-b', 'user-1', 'cloud subscription', 'subscription', 1);

-- Tenant B, User 2 (1 search)
INSERT INTO search_history (tenant_id, user_id, query, search_type, result_count)
VALUES
    ('test-tenant-b', 'user-2', 'monitoring server', 'device', 10);

-- Add some searches with common prefixes for suggestion testing
INSERT INTO search_history (tenant_id, user_id, query, search_type)
VALUES
    ('test-tenant-a', 'user-1', 'compute cluster', 'device'),
    ('test-tenant-b', 'user-1', 'compute node', 'device');

\echo ''
\echo '============================================'
\echo 'Test Data Created'
\echo '============================================'
\echo ''

-- ============================================
-- STEP 2: Verify tenant/user isolation
-- ============================================

\echo 'TEST 1: Verify each tenant/user sees only their own searches'
\echo ''

\echo '  Test 1.1: tenant-a/user-1 should see exactly 4 searches'
SELECT
    CASE
        WHEN COUNT(*) = 4 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 4, got ' || COUNT(*)::text
    END as result,
    COUNT(*) as actual_count
FROM search_history
WHERE tenant_id = 'test-tenant-a' AND user_id = 'user-1';

\echo '  Test 1.2: tenant-a/user-2 should see exactly 2 searches'
SELECT
    CASE
        WHEN COUNT(*) = 2 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 2, got ' || COUNT(*)::text
    END as result,
    COUNT(*) as actual_count
FROM search_history
WHERE tenant_id = 'test-tenant-a' AND user_id = 'user-2';

\echo '  Test 1.3: tenant-b/user-1 should see exactly 3 searches'
SELECT
    CASE
        WHEN COUNT(*) = 3 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 3, got ' || COUNT(*)::text
    END as result,
    COUNT(*) as actual_count
FROM search_history
WHERE tenant_id = 'test-tenant-b' AND user_id = 'user-1';

\echo '  Test 1.4: tenant-b/user-2 should see exactly 1 search'
SELECT
    CASE
        WHEN COUNT(*) = 1 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 1, got ' || COUNT(*)::text
    END as result,
    COUNT(*) as actual_count
FROM search_history
WHERE tenant_id = 'test-tenant-b' AND user_id = 'user-2';

\echo ''
\echo 'TEST 2: Verify no cross-tenant data leakage'
\echo ''

\echo '  Test 2.1: tenant-a should not see tenant-b data'
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Found ' || COUNT(*)::text || ' tenant-b records in tenant-a query'
    END as result
FROM search_history
WHERE tenant_id = 'test-tenant-a' AND id IN (
    SELECT id FROM search_history WHERE tenant_id = 'test-tenant-b'
);

\echo '  Test 2.2: tenant-b should not see tenant-a data'
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Found ' || COUNT(*)::text || ' tenant-a records in tenant-b query'
    END as result
FROM search_history
WHERE tenant_id = 'test-tenant-b' AND id IN (
    SELECT id FROM search_history WHERE tenant_id = 'test-tenant-a'
);

\echo ''
\echo 'TEST 3: Verify no cross-user data leakage within same tenant'
\echo ''

\echo '  Test 3.1: tenant-a/user-1 should not see tenant-a/user-2 data'
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Found ' || COUNT(*)::text || ' user-2 records in user-1 query'
    END as result
FROM search_history
WHERE tenant_id = 'test-tenant-a' AND user_id = 'user-1' AND id IN (
    SELECT id FROM search_history WHERE tenant_id = 'test-tenant-a' AND user_id = 'user-2'
);

\echo ''
\echo 'TEST 4: Verify search type filtering within tenant/user'
\echo ''

\echo '  Test 4.1: tenant-a/user-1 should have 3 device searches'
SELECT
    CASE
        WHEN COUNT(*) = 3 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 3, got ' || COUNT(*)::text
    END as result,
    COUNT(*) as actual_count
FROM search_history
WHERE tenant_id = 'test-tenant-a' AND user_id = 'user-1' AND search_type = 'device';

\echo '  Test 4.2: tenant-a/user-1 should have 1 subscription search'
SELECT
    CASE
        WHEN COUNT(*) = 1 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 1, got ' || COUNT(*)::text
    END as result,
    COUNT(*) as actual_count
FROM search_history
WHERE tenant_id = 'test-tenant-a' AND user_id = 'user-1' AND search_type = 'subscription';

\echo ''
\echo 'TEST 5: Verify prefix-based suggestions isolation'
\echo ''

\echo '  Test 5.1: tenant-a/user-1 should get 2 suggestions for prefix "comp"'
SELECT
    CASE
        WHEN COUNT(DISTINCT query) = 2 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 2, got ' || COUNT(DISTINCT query)::text
    END as result,
    COUNT(DISTINCT query) as suggestion_count
FROM search_history
WHERE tenant_id = 'test-tenant-a'
    AND user_id = 'user-1'
    AND query ILIKE 'comp%';

\echo '  Test 5.2: tenant-b/user-1 should get 1 suggestion for prefix "comp"'
SELECT
    CASE
        WHEN COUNT(DISTINCT query) = 1 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 1, got ' || COUNT(DISTINCT query)::text
    END as result,
    COUNT(DISTINCT query) as suggestion_count
FROM search_history
WHERE tenant_id = 'test-tenant-b'
    AND user_id = 'user-1'
    AND query ILIKE 'comp%';

\echo '  Test 5.3: tenant-a/user-2 should get 0 suggestions for prefix "comp"'
SELECT
    CASE
        WHEN COUNT(DISTINCT query) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 0, got ' || COUNT(DISTINCT query)::text
    END as result,
    COUNT(DISTINCT query) as suggestion_count
FROM search_history
WHERE tenant_id = 'test-tenant-a'
    AND user_id = 'user-2'
    AND query ILIKE 'comp%';

\echo ''
\echo 'TEST 6: Verify suggestions with search_type filtering'
\echo ''

\echo '  Test 6.1: tenant-a/user-1 device suggestions for "comp"'
SELECT
    CASE
        WHEN COUNT(DISTINCT query) = 2 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 2, got ' || COUNT(DISTINCT query)::text
    END as result,
    COUNT(DISTINCT query) as suggestion_count
FROM search_history
WHERE tenant_id = 'test-tenant-a'
    AND user_id = 'user-1'
    AND search_type = 'device'
    AND query ILIKE 'comp%';

\echo '  Test 6.2: tenant-a/user-1 subscription suggestions for "aruba"'
SELECT
    CASE
        WHEN COUNT(DISTINCT query) = 1 THEN '✓ PASS'
        ELSE '✗ FAIL - Expected 1, got ' || COUNT(DISTINCT query)::text
    END as result,
    COUNT(DISTINCT query) as suggestion_count
FROM search_history
WHERE tenant_id = 'test-tenant-a'
    AND user_id = 'user-1'
    AND search_type = 'subscription'
    AND query ILIKE 'aruba%';

\echo ''
\echo '============================================'
\echo 'Detailed Data View (for manual inspection)'
\echo '============================================'
\echo ''

\echo 'All test data grouped by tenant and user:'
SELECT
    tenant_id,
    user_id,
    search_type,
    COUNT(*) as search_count,
    array_agg(query ORDER BY created_at DESC) as queries
FROM search_history
WHERE tenant_id LIKE 'test-tenant-%'
GROUP BY tenant_id, user_id, search_type
ORDER BY tenant_id, user_id, search_type;

\echo ''
\echo '============================================'
\echo 'CLEANUP: Remove test data'
\echo '============================================'

-- Uncomment the line below to automatically clean up test data
-- DELETE FROM search_history WHERE tenant_id LIKE 'test-tenant-%';

\echo ''
\echo 'Test data preserved. Run this command to clean up:'
\echo "  DELETE FROM search_history WHERE tenant_id LIKE 'test-tenant-%';"
\echo ''
