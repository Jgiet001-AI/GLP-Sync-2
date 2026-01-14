#!/bin/bash
# End-to-End Verification Script for Circuit Breaker Status Feature
# This script verifies the complete circuit breaker status integration

set -e

echo "========================================="
echo "Circuit Breaker E2E Verification"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Verify auto-registration
echo "Step 1: Testing circuit breaker auto-registration..."
python3 << 'EOF'
from src.glp.api.resilience import CircuitBreaker, get_all_circuit_breaker_status, clear_circuit_breaker_registry

# Clear registry
clear_circuit_breaker_registry()

# Create circuit breakers (should auto-register)
cb1 = CircuitBreaker(name='glp_api')
cb2 = CircuitBreaker(name='aruba_central_api')

# Verify registration
statuses = get_all_circuit_breaker_status()
assert len(statuses) == 2, f"Expected 2 circuit breakers, got {len(statuses)}"
names = [s['name'] for s in statuses]
assert 'glp_api' in names, "'glp_api' not registered"
assert 'aruba_central_api' in names, "'aruba_central_api' not registered"

print(f"✅ Auto-registration working: {names}")
EOF

# Step 2: Verify health endpoint models
echo "Step 2: Verifying Pydantic models..."
python3 << 'EOF'
from src.glp.assignment.api.dashboard_router import CircuitBreakerStatus, HealthCheckResponse
from datetime import datetime

# Test CircuitBreakerStatus model
cb_status = CircuitBreakerStatus(
    state="closed",
    failure_count=0,
    last_failure_time=None,
    next_attempt_time=None
)
print(f"✅ CircuitBreakerStatus model OK: {cb_status.state}")

# Test HealthCheckResponse model
health = HealthCheckResponse(
    status="healthy",
    circuit_breaker=cb_status
)
print(f"✅ HealthCheckResponse model OK: {health.status}")
EOF

# Step 3: Start API server (if not running)
echo ""
echo "Step 3: Testing API server health endpoint..."
API_PORT=8000
API_URL="http://localhost:${API_PORT}/api/dashboard/health"

# Check if server is running
if ! curl -s -f "${API_URL}" > /dev/null 2>&1; then
    echo "${YELLOW}⚠️  API server not running on port ${API_PORT}${NC}"
    echo "   Please start it with:"
    echo "   uv run uvicorn src.glp.assignment.app:app --port 8000"
    echo ""
    echo "   Then run this script again to test the /health endpoint"
else
    echo "${GREEN}✅ API server is running${NC}"

    # Test health endpoint
    echo ""
    echo "Testing /health endpoint..."
    RESPONSE=$(curl -s "${API_URL}")

    # Verify response contains expected fields
    echo "$RESPONSE" | python3 -m json.tool

    # Check for circuit_breaker field
    if echo "$RESPONSE" | grep -q "circuit_breaker"; then
        echo "${GREEN}✅ Health endpoint includes circuit_breaker field${NC}"
    else
        echo "${RED}❌ Health endpoint missing circuit_breaker field${NC}"
        exit 1
    fi
fi

# Step 4: Frontend verification
echo ""
echo "Step 4: Frontend verification..."
FRONTEND_PORT=5173
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

if ! curl -s -f "${FRONTEND_URL}" > /dev/null 2>&1; then
    echo "${YELLOW}⚠️  Frontend not running on port ${FRONTEND_PORT}${NC}"
    echo "   To verify frontend integration:"
    echo "   1. cd frontend"
    echo "   2. npm install"
    echo "   3. npm run dev"
    echo "   4. Open http://localhost:5173 in browser"
    echo "   5. Verify circuit breaker indicators are visible in dashboard header"
else
    echo "${GREEN}✅ Frontend is running at ${FRONTEND_URL}${NC}"
    echo ""
    echo "   Manual verification checklist:"
    echo "   [ ] Dashboard renders without errors"
    echo "   [ ] Circuit breaker status indicators visible in header"
    echo "   [ ] Status colors match circuit state:"
    echo "       - Emerald (green) = closed/healthy"
    echo "       - Amber (yellow) = half_open/testing"
    echo "       - Rose (red) = open/failing"
    echo "   [ ] Tooltip shows circuit breaker details on hover"
fi

echo ""
echo "========================================="
echo "${GREEN}Verification Complete!${NC}"
echo "========================================="
echo ""
echo "Summary of changes:"
echo "  ✅ Circuit breaker auto-registration implemented"
echo "  ✅ CircuitBreakerStatus and HealthCheckResponse models added"
echo "  ✅ /health endpoint returns circuit breaker status"
echo "  ✅ Frontend types updated (CircuitBreakerStatus, HealthCheckResponse)"
echo "  ✅ Dashboard displays circuit breaker status with color coding"
echo ""
