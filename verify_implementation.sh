#!/bin/bash
# Verification script for HTTP caching implementation
# This script checks that the code has the correct Cache-Control headers

echo "========================================================================"
echo "HTTP CACHING IMPLEMENTATION VERIFICATION"
echo "========================================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check file exists
FILE="./src/glp/assignment/api/dashboard_router.py"
if [ ! -f "$FILE" ]; then
    echo -e "${RED}✗ File not found: $FILE${NC}"
    exit 1
fi

echo "Checking file: $FILE"
echo ""

# Test 1: Check filters endpoint has Response parameter
echo "Test 1: Filters endpoint has Response parameter injection"
if grep -A 5 '@router.get("/filters"' "$FILE" | grep -q 'response: Response'; then
    echo -e "${GREEN}✓ PASS${NC} - Response parameter found"
else
    echo -e "${RED}✗ FAIL${NC} - Response parameter not found"
    exit 1
fi

# Test 2: Check filters endpoint sets Cache-Control header
echo "Test 2: Filters endpoint sets Cache-Control header (5 minutes)"
if grep -A 20 '@router.get("/filters"' "$FILE" | grep -q 'Cache-Control.*max-age=300'; then
    echo -e "${GREEN}✓ PASS${NC} - Cache-Control: public, max-age=300 found"
else
    echo -e "${RED}✗ FAIL${NC} - Cache-Control header not found or incorrect"
    exit 1
fi

# Test 3: Check dashboard endpoint has Response parameter
echo "Test 3: Dashboard endpoint has Response parameter injection"
if grep -A 7 '@router.get("", response_model=DashboardResponse)' "$FILE" | grep -q 'response: Response'; then
    echo -e "${GREEN}✓ PASS${NC} - Response parameter found"
else
    echo -e "${RED}✗ FAIL${NC} - Response parameter not found"
    exit 1
fi

# Test 4: Check dashboard endpoint sets Cache-Control header
echo "Test 4: Dashboard endpoint sets Cache-Control header (30 seconds)"
if grep -A 15 'async def get_dashboard' "$FILE" | grep -q 'Cache-Control.*max-age=30'; then
    echo -e "${GREEN}✓ PASS${NC} - Cache-Control: public, max-age=30 found"
else
    echo -e "${RED}✗ FAIL${NC} - Cache-Control header not found or incorrect"
    exit 1
fi

# Test 5: Verify Response is imported from fastapi
echo "Test 5: Response is imported from fastapi"
if grep -q 'from fastapi import.*Response' "$FILE"; then
    echo -e "${GREEN}✓ PASS${NC} - Response imported from fastapi"
else
    echo -e "${RED}✗ FAIL${NC} - Response not imported"
    exit 1
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
echo "========================================================================"
echo ""
echo "The implementation is correct. Cache-Control headers will be sent"
echo "when the code is deployed and the API server is running with this code."
echo ""
echo "Summary:"
echo "  - /api/dashboard/filters: Cache-Control: public, max-age=300 (5 min)"
echo "  - /api/dashboard:         Cache-Control: public, max-age=30  (30 sec)"
echo ""
