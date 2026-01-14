#!/bin/bash
# Test script to verify tenant isolation for search history
# This script verifies that searches from one tenant/user don't appear in another's history or suggestions

set -e

API_BASE="http://localhost:8000/api/dashboard"
API_KEY="${API_KEY:-test-api-key-12345}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Tenant Isolation Verification Test"
echo "=========================================="
echo ""

# Function to make API calls with proper headers
api_call() {
    local method=$1
    local endpoint=$2
    local data=$3

    if [ -z "$data" ]; then
        curl -s -X "$method" \
            -H "X-API-Key: $API_KEY" \
            "$API_BASE$endpoint"
    else
        curl -s -X "$method" \
            -H "X-API-Key: $API_KEY" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$API_BASE$endpoint"
    fi
}

# Function to verify isolation
verify_isolation() {
    local test_name=$1
    local tenant_id=$2
    local user_id=$3
    local expected_count=$4
    local search_type=$5

    echo -n "  Testing: $test_name... "

    local endpoint="/search-history?tenant_id=$tenant_id&user_id=$user_id"
    if [ -n "$search_type" ]; then
        endpoint="${endpoint}&search_type=$search_type"
    fi

    local response=$(api_call GET "$endpoint")
    local actual_count=$(echo "$response" | jq -r '.total // 0')

    if [ "$actual_count" -eq "$expected_count" ]; then
        echo -e "${GREEN}✓ PASS${NC} (found $actual_count records)"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (expected $expected_count, got $actual_count)"
        echo "    Response: $response"
        return 1
    fi
}

# Function to verify suggestions isolation
verify_suggestions_isolation() {
    local test_name=$1
    local tenant_id=$2
    local user_id=$3
    local prefix=$4
    local expected_count=$5
    local search_type=$6

    echo -n "  Testing: $test_name... "

    local endpoint="/search-suggestions?tenant_id=$tenant_id&user_id=$user_id&prefix=$prefix"
    if [ -n "$search_type" ]; then
        endpoint="${endpoint}&search_type=$search_type"
    fi

    local response=$(api_call GET "$endpoint")
    local actual_count=$(echo "$response" | jq -r '.suggestions | length')

    if [ "$actual_count" -eq "$expected_count" ]; then
        echo -e "${GREEN}✓ PASS${NC} (found $actual_count suggestions)"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (expected $expected_count, got $actual_count)"
        echo "    Response: $response"
        return 1
    fi
}

# Check if API is running
echo "1. Checking API availability..."
if ! curl -s -f -H "X-API-Key: $API_KEY" "$API_BASE/stats" > /dev/null 2>&1; then
    echo -e "  ${RED}✗ FAIL${NC} API server not running at $API_BASE"
    echo "  Please start the API server: uv run uvicorn src.glp.assignment.app:app --reload --port 8000"
    exit 1
fi
echo -e "  ${GREEN}✓ PASS${NC} API is running"
echo ""

# Clear any existing search history for test tenants
echo "2. Cleaning up test data..."
echo "  Cleaning search history from database..."
if [ -n "$DATABASE_URL" ]; then
    psql "$DATABASE_URL" -c "DELETE FROM search_history WHERE tenant_id LIKE 'test-tenant-%'" > /dev/null 2>&1 || true
    echo -e "  ${GREEN}✓ PASS${NC} Test data cleaned"
else
    echo -e "  ${YELLOW}⚠ SKIP${NC} DATABASE_URL not set, skipping direct cleanup"
fi
echo ""

# Test Scenario 1: Create search history for different tenants
echo "3. Creating search history for different tenant/user combinations..."

# Tenant A, User 1
echo "  Creating searches for tenant-a/user-1..."
api_call POST "/search-history" '{"tenant_id":"test-tenant-a","user_id":"user-1","query":"compute server","search_type":"device"}' > /dev/null
api_call POST "/search-history" '{"tenant_id":"test-tenant-a","user_id":"user-1","query":"storage device","search_type":"device"}' > /dev/null
api_call POST "/search-history" '{"tenant_id":"test-tenant-a","user_id":"user-1","query":"aruba subscription","search_type":"subscription"}' > /dev/null

# Tenant A, User 2
echo "  Creating searches for tenant-a/user-2..."
api_call POST "/search-history" '{"tenant_id":"test-tenant-a","user_id":"user-2","query":"network switch","search_type":"device"}' > /dev/null
api_call POST "/search-history" '{"tenant_id":"test-tenant-a","user_id":"user-2","query":"aruba central","search_type":"subscription"}' > /dev/null

# Tenant B, User 1
echo "  Creating searches for tenant-b/user-1..."
api_call POST "/search-history" '{"tenant_id":"test-tenant-b","user_id":"user-1","query":"backup device","search_type":"device"}' > /dev/null
api_call POST "/search-history" '{"tenant_id":"test-tenant-b","user_id":"user-1","query":"cloud subscription","search_type":"subscription"}' > /dev/null

# Tenant B, User 2
echo "  Creating searches for tenant-b/user-2..."
api_call POST "/search-history" '{"tenant_id":"test-tenant-b","user_id":"user-2","query":"monitoring server","search_type":"device"}' > /dev/null

echo -e "  ${GREEN}✓ PASS${NC} Test data created"
echo ""

# Test Scenario 2: Verify tenant isolation for search history
echo "4. Verifying search history isolation..."
PASSED=0
FAILED=0

verify_isolation "tenant-a/user-1 sees only their 3 searches" "test-tenant-a" "user-1" 3 && ((PASSED++)) || ((FAILED++))
verify_isolation "tenant-a/user-2 sees only their 2 searches" "test-tenant-a" "user-2" 2 && ((PASSED++)) || ((FAILED++))
verify_isolation "tenant-b/user-1 sees only their 2 searches" "test-tenant-b" "user-1" 2 && ((PASSED++)) || ((FAILED++))
verify_isolation "tenant-b/user-2 sees only their 1 search" "test-tenant-b" "user-2" 1 && ((PASSED++)) || ((FAILED++))

# Verify cross-tenant isolation
verify_isolation "tenant-a/user-1 doesn't see tenant-b data" "test-tenant-a" "user-1" 3 && ((PASSED++)) || ((FAILED++))
verify_isolation "tenant-b/user-1 doesn't see tenant-a data" "test-tenant-b" "user-1" 2 && ((PASSED++)) || ((FAILED++))

echo ""

# Test Scenario 3: Verify search type filtering
echo "5. Verifying search type filtering within tenant/user..."
verify_isolation "tenant-a/user-1 has 2 device searches" "test-tenant-a" "user-1" 2 "device" && ((PASSED++)) || ((FAILED++))
verify_isolation "tenant-a/user-1 has 1 subscription search" "test-tenant-a" "user-1" 1 "subscription" && ((PASSED++)) || ((FAILED++))
verify_isolation "tenant-b/user-1 has 1 device search" "test-tenant-b" "user-1" 1 "device" && ((PASSED++)) || ((FAILED++))
verify_isolation "tenant-b/user-1 has 1 subscription search" "test-tenant-b" "user-1" 1 "subscription" && ((PASSED++)) || ((FAILED++))

echo ""

# Test Scenario 4: Verify suggestions isolation
echo "6. Verifying search suggestions isolation..."

# Add some more searches with common prefixes for better testing
api_call POST "/search-history" '{"tenant_id":"test-tenant-a","user_id":"user-1","query":"compute cluster","search_type":"device"}' > /dev/null
api_call POST "/search-history" '{"tenant_id":"test-tenant-b","user_id":"user-1","query":"compute node","search_type":"device"}' > /dev/null

verify_suggestions_isolation "tenant-a/user-1 gets suggestions for 'comp'" "test-tenant-a" "user-1" "comp" 2 && ((PASSED++)) || ((FAILED++))
verify_suggestions_isolation "tenant-b/user-1 gets different suggestions for 'comp'" "test-tenant-b" "user-1" "comp" 1 && ((PASSED++)) || ((FAILED++))
verify_suggestions_isolation "tenant-a/user-2 gets no suggestions for 'comp'" "test-tenant-a" "user-2" "comp" 0 && ((PASSED++)) || ((FAILED++))

# Verify prefix matching is working correctly
verify_suggestions_isolation "tenant-a/user-1 gets suggestions for 'aruba'" "test-tenant-a" "user-1" "aruba" 1 && ((PASSED++)) || ((FAILED++))
verify_suggestions_isolation "tenant-a/user-2 gets suggestions for 'aruba'" "test-tenant-a" "user-2" "aruba" 1 && ((PASSED++)) || ((FAILED++))
verify_suggestions_isolation "tenant-b/user-1 gets no suggestions for 'aruba'" "test-tenant-b" "user-1" "aruba" 0 && ((PASSED++)) || ((FAILED++))

echo ""

# Test Scenario 5: Verify no data leakage via search type filtering in suggestions
echo "7. Verifying suggestions with search_type filtering..."
verify_suggestions_isolation "tenant-a/user-1 device suggestions for 'comp'" "test-tenant-a" "user-1" "comp" 2 "device" && ((PASSED++)) || ((FAILED++))
verify_suggestions_isolation "tenant-a/user-1 subscription suggestions for 'aruba'" "test-tenant-a" "user-1" "aruba" 1 "subscription" && ((PASSED++)) || ((FAILED++))

echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "Total Tests: $((PASSED + FAILED))"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tenant isolation tests PASSED!${NC}"
    echo ""
    echo "Tenant isolation is working correctly:"
    echo "  • Searches are properly isolated by tenant_id and user_id"
    echo "  • Search suggestions respect tenant/user boundaries"
    echo "  • No data leakage between different tenants or users"
    echo "  • Search type filtering works within tenant/user context"
    exit 0
else
    echo -e "${RED}✗ Some tests FAILED${NC}"
    echo ""
    echo "Please review the failures above and fix the tenant isolation issues."
    exit 1
fi
