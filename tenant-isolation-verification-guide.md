# Tenant Isolation Verification Guide

## Overview

This guide provides comprehensive steps to verify that search history is properly isolated by `tenant_id` and `user_id`, ensuring that searches from one tenant/user don't appear in another's history or suggestions.

## Prerequisites

- PostgreSQL database with `search_history` table (migration 007 applied)
- API server running at `http://localhost:8000` (optional, for API testing)
- `DATABASE_URL` environment variable set
- `API_KEY` environment variable set (default: `test-api-key-12345`)

## Verification Methods

### Method 1: Database-Level Verification (Recommended)

This method directly tests the database queries and isolation logic without requiring the API server.

#### Run the SQL Test Script

```bash
psql $DATABASE_URL -f test-tenant-isolation-db.sql
```

#### Expected Results

All tests should show `✓ PASS`:

1. **TEST 1**: Each tenant/user sees only their own searches
   - tenant-a/user-1: 4 searches
   - tenant-a/user-2: 2 searches
   - tenant-b/user-1: 3 searches
   - tenant-b/user-2: 1 search

2. **TEST 2**: No cross-tenant data leakage
   - tenant-a queries don't return tenant-b data
   - tenant-b queries don't return tenant-a data

3. **TEST 3**: No cross-user data leakage within same tenant
   - tenant-a/user-1 doesn't see tenant-a/user-2 data

4. **TEST 4**: Search type filtering works within tenant/user
   - Filtering by `search_type` doesn't bypass isolation

5. **TEST 5**: Prefix-based suggestions respect isolation
   - Different tenants/users get different suggestions for same prefix

6. **TEST 6**: Suggestions with search_type filtering
   - Type filtering in suggestions respects tenant/user boundaries

#### Manual Database Queries

You can also run these queries manually to verify isolation:

```sql
-- 1. Check isolation: user should only see their own searches
SELECT tenant_id, user_id, query, search_type
FROM search_history
WHERE tenant_id = 'test-tenant-a' AND user_id = 'user-1';
-- Should return only user-1's searches, not user-2's

-- 2. Verify no cross-tenant leakage
SELECT COUNT(*) FROM search_history
WHERE tenant_id = 'test-tenant-a'
  AND id IN (SELECT id FROM search_history WHERE tenant_id = 'test-tenant-b');
-- Should return 0

-- 3. Test suggestion query isolation
SELECT DISTINCT query
FROM search_history
WHERE tenant_id = 'test-tenant-a'
  AND user_id = 'user-1'
  AND query ILIKE 'comp%'
GROUP BY query
ORDER BY MAX(created_at) DESC;
-- Should return suggestions only for this user
```

### Method 2: API-Level Verification

This method tests the complete stack including the API endpoints.

#### Prerequisites

Start the API server:

```bash
uv run uvicorn src.glp.assignment.app:app --reload --port 8000
```

#### Run the API Test Script

```bash
export API_KEY=test-api-key-12345
bash test-tenant-isolation.sh
```

#### Expected Results

All 18 tests should pass:
- ✓ Search history isolation (6 tests)
- ✓ Search type filtering (4 tests)
- ✓ Suggestions isolation (6 tests)
- ✓ Suggestions with type filtering (2 tests)

#### Manual API Testing

You can also test the API endpoints manually using curl:

```bash
API_KEY="test-api-key-12345"

# 1. Create search history for tenant-a/user-1
curl -X POST http://localhost:8000/api/dashboard/search-history \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant-a",
    "user_id": "user-1",
    "query": "test query",
    "search_type": "device"
  }'

# 2. Create search history for tenant-b/user-1
curl -X POST http://localhost:8000/api/dashboard/search-history \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant-b",
    "user_id": "user-1",
    "query": "test query",
    "search_type": "device"
  }'

# 3. Get history for tenant-a/user-1 (should NOT include tenant-b data)
curl -X GET "http://localhost:8000/api/dashboard/search-history?tenant_id=test-tenant-a&user_id=user-1" \
  -H "X-API-Key: $API_KEY"

# 4. Get suggestions for tenant-a/user-1 (should NOT include tenant-b data)
curl -X GET "http://localhost:8000/api/dashboard/search-suggestions?tenant_id=test-tenant-a&user_id=user-1&prefix=test" \
  -H "X-API-Key: $API_KEY"
```

### Method 3: Frontend Browser Testing

This method tests the complete user experience through the browser.

#### Steps

1. **Start the full stack**:
   ```bash
   # Terminal 1: API server
   uv run uvicorn src.glp.assignment.app:app --reload --port 8000

   # Terminal 2: Frontend dev server
   cd frontend && npm run dev
   ```

2. **Open browser** to `http://localhost:5173`

3. **Simulate different users**:
   - Use browser profiles or incognito windows for different users
   - The frontend should pass `tenant_id` and `user_id` from authentication context

4. **Perform searches**:
   - User A (tenant-1/user-1): Search for "server"
   - User B (tenant-1/user-2): Search for "device"
   - User C (tenant-2/user-1): Search for "server"

5. **Verify isolation**:
   - User A's search history should show "server" only
   - User B's search history should show "device" only
   - User C's search history should show "server" only (different from User A)
   - Suggestions should respect the same boundaries

## Test Scenarios Covered

### Scenario 1: Same Tenant, Different Users
- **Setup**: tenant-a/user-1 and tenant-a/user-2
- **Verification**: Each user sees only their own searches
- **Result**: ✓ Users within same tenant are isolated

### Scenario 2: Different Tenants, Same User ID
- **Setup**: tenant-a/user-1 and tenant-b/user-1
- **Verification**: Same user_id in different tenants see different data
- **Result**: ✓ Tenants are isolated even with same user_id

### Scenario 3: Search Type Filtering
- **Setup**: Create device and subscription searches for same user
- **Verification**: Filtering by search_type doesn't bypass tenant/user isolation
- **Result**: ✓ Type filtering works within isolation boundaries

### Scenario 4: Prefix Suggestions
- **Setup**: Different tenants/users with similar search queries
- **Verification**: Suggestions only match within tenant/user boundary
- **Result**: ✓ Suggestions respect isolation

### Scenario 5: Combined Filters
- **Setup**: Use both tenant/user and search_type filters together
- **Verification**: All filters work correctly together
- **Result**: ✓ Multiple filters maintain isolation

## Security Checklist

- [ ] **Tenant Isolation**: Searches from tenant-a never appear in tenant-b queries
- [ ] **User Isolation**: Searches from user-1 never appear in user-2 queries (same tenant)
- [ ] **Combined Isolation**: tenant-a/user-1 isolated from tenant-b/user-2
- [ ] **Search Type Filtering**: Type filter doesn't bypass isolation
- [ ] **Suggestions Isolation**: Prefix matching respects tenant/user boundaries
- [ ] **No SQL Injection**: Special characters in tenant_id/user_id don't break isolation
- [ ] **No Data Leakage via IDs**: UUIDs don't reveal data from other tenants

## Database Schema Validation

Verify the indexes are in place for efficient isolation queries:

```sql
-- Check indexes exist
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'search_history'
ORDER BY indexname;
```

Expected indexes:
1. `idx_search_history_tenant_user` - For listing user's searches
2. `idx_search_history_search_type` - For filtering by type
3. `idx_search_history_query_prefix` - For prefix matching (suggestions)
4. `idx_search_history_created_at` - For cleanup/analytics

## Troubleshooting

### Test Failures

If tests fail, check:

1. **Database Migration**: Ensure migration 007 has been applied
   ```bash
   psql $DATABASE_URL -c "\d search_history"
   ```

2. **API Authentication**: Verify API_KEY is set correctly
   ```bash
   echo $API_KEY
   ```

3. **Database Connection**: Check DATABASE_URL is valid
   ```bash
   psql $DATABASE_URL -c "SELECT 1"
   ```

4. **Query Logic**: Review the WHERE clauses in dashboard_router.py
   - All queries should filter by `tenant_id` AND `user_id`
   - No queries should allow cross-tenant or cross-user access

### Data Cleanup

To remove all test data:

```sql
DELETE FROM search_history WHERE tenant_id LIKE 'test-tenant-%';
```

## Conclusion

When all tests pass:
- ✓ Tenant isolation is working correctly
- ✓ User isolation is working correctly
- ✓ No data leakage between tenants or users
- ✓ Search type filtering respects isolation
- ✓ Suggestions maintain isolation boundaries

The search history feature is secure for multi-tenant deployment.
