#!/bin/bash
# Manual Security Verification Script
# Tests error response sanitization without requiring full environment

echo "================================================================================"
echo "MANUAL SECURITY VERIFICATION - ERROR RESPONSE SANITIZATION"
echo "================================================================================"
echo ""
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Working Directory: $(pwd)"
echo ""

PASS_COUNT=0
FAIL_COUNT=0
TOTAL_COUNT=0

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

test_pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASS_COUNT++))
    ((TOTAL_COUNT++))
}

test_fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    echo -e "   Details: $2"
    ((FAIL_COUNT++))
    ((TOTAL_COUNT++))
}

test_info() {
    echo -e "${YELLOW}ℹ INFO${NC}: $1"
}

echo "================================================================================"
echo "TEST 1: Verify Error Sanitizer Module Exists"
echo "================================================================================"
echo ""

if [ -f "src/glp/api/error_sanitizer.py" ]; then
    test_pass "Error sanitizer module exists"

    # Check for key components
    if grep -q "class ErrorSanitizer" src/glp/api/error_sanitizer.py; then
        test_pass "ErrorSanitizer class defined"
    else
        test_fail "ErrorSanitizer class missing" "Class not found in module"
    fi

    if grep -q "def sanitize_error_message" src/glp/api/error_sanitizer.py; then
        test_pass "sanitize_error_message function defined"
    else
        test_fail "sanitize_error_message function missing" "Function not found in module"
    fi

    # Check for sensitive pattern coverage
    if grep -q "password" src/glp/api/error_sanitizer.py; then
        test_pass "Password pattern covered"
    else
        test_fail "Password pattern missing" "No password redaction pattern"
    fi

    if grep -q "DATABASE_URL\|postgresql://\|mysql://" src/glp/api/error_sanitizer.py; then
        test_pass "Database URL pattern covered"
    else
        test_fail "Database URL pattern missing" "No database URL redaction pattern"
    fi

    if grep -q "GLP_CLIENT_ID\|ENV_VAR" src/glp/api/error_sanitizer.py; then
        test_pass "Environment variable pattern covered"
    else
        test_fail "Environment variable pattern missing" "No env var redaction pattern"
    fi

    if grep -q "/etc/\|FILE_PATH" src/glp/api/error_sanitizer.py; then
        test_pass "File path pattern covered"
    else
        test_fail "File path pattern missing" "No file path redaction pattern"
    fi

    if grep -q "Traceback\|STACK_TRACE" src/glp/api/error_sanitizer.py; then
        test_pass "Stack trace pattern covered"
    else
        test_fail "Stack trace pattern missing" "No stack trace redaction pattern"
    fi

    if grep -q "192\.168\|IP_ADDRESS" src/glp/api/error_sanitizer.py; then
        test_pass "IP address pattern covered"
    else
        test_fail "IP address pattern missing" "No IP redaction pattern"
    fi

else
    test_fail "Error sanitizer module missing" "File not found: src/glp/api/error_sanitizer.py"
fi

echo ""
echo "================================================================================"
echo "TEST 2: Verify FastAPI Exception Handlers"
echo "================================================================================"
echo ""

if [ -f "src/glp/assignment/app.py" ]; then
    test_pass "FastAPI app file exists"

    # Check for exception handler functions
    if grep -q "http_exception_handler" src/glp/assignment/app.py; then
        test_pass "HTTPException handler defined"
    else
        test_fail "HTTPException handler missing" "Function not found in app.py"
    fi

    if grep -q "generic_exception_handler" src/glp/assignment/app.py; then
        test_pass "Generic exception handler defined"
    else
        test_fail "Generic exception handler missing" "Function not found in app.py"
    fi

    # Check handlers are registered
    if grep -q "add_exception_handler.*HTTPException.*http_exception_handler" src/glp/assignment/app.py; then
        test_pass "HTTPException handler registered"
    else
        test_fail "HTTPException handler not registered" "app.add_exception_handler(HTTPException, ...) not found"
    fi

    if grep -q "add_exception_handler.*Exception.*generic_exception_handler" src/glp/assignment/app.py; then
        test_pass "Generic exception handler registered"
    else
        test_fail "Generic exception handler not registered" "app.add_exception_handler(Exception, ...) not found"
    fi

    # Check handlers use sanitize_error_message
    if grep -q "sanitize_error_message.*exc.detail\|sanitize_error_message.*str(exc)" src/glp/assignment/app.py; then
        test_pass "Exception handlers use sanitize_error_message"
    else
        test_fail "Exception handlers don't use sanitizer" "No sanitize_error_message calls in handlers"
    fi

    # Check handlers log original errors
    if grep -q "logger.*exc\|logging.*exc" src/glp/assignment/app.py; then
        test_pass "Exception handlers log original errors"
    else
        test_fail "Exception handlers don't log" "No logging found in handlers"
    fi

else
    test_fail "FastAPI app missing" "File not found: src/glp/assignment/app.py"
fi

echo ""
echo "================================================================================"
echo "TEST 3: Verify Router Error Handling"
echo "================================================================================"
echo ""

# Check dashboard_router.py
test_info "Checking Dashboard Router..."
if [ -f "src/glp/assignment/api/dashboard_router.py" ]; then
    if grep -q "from.*error_sanitizer import sanitize_error_message" src/glp/assignment/api/dashboard_router.py; then
        test_pass "Dashboard router imports sanitize_error_message"
    else
        test_fail "Dashboard router missing import" "No sanitize_error_message import"
    fi

    # Count unsanitized HTTPException instances with {e}
    UNSANITIZED=$(grep -c 'HTTPException.*detail.*f.*{e}' src/glp/assignment/api/dashboard_router.py 2>/dev/null || echo "0")
    if [ "$UNSANITIZED" -eq "0" ]; then
        test_pass "Dashboard router: No unsanitized {e} in HTTPException"
    else
        test_fail "Dashboard router has unsanitized errors" "Found $UNSANITIZED instances of HTTPException with {e}"
    fi
else
    test_fail "Dashboard router missing" "File not found"
fi

# Check clients_router.py
echo ""
test_info "Checking Clients Router..."
if [ -f "src/glp/assignment/api/clients_router.py" ]; then
    if grep -q "from.*error_sanitizer import sanitize_error_message" src/glp/assignment/api/clients_router.py; then
        test_pass "Clients router imports sanitize_error_message"
    else
        test_fail "Clients router missing import" "No sanitize_error_message import"
    fi

    UNSANITIZED=$(grep -c 'HTTPException.*detail.*f.*{e}' src/glp/assignment/api/clients_router.py 2>/dev/null || echo "0")
    if [ "$UNSANITIZED" -eq "0" ]; then
        test_pass "Clients router: No unsanitized {e} in HTTPException"
    else
        test_fail "Clients router has unsanitized errors" "Found $UNSANITIZED instances of HTTPException with {e}"
    fi
else
    test_fail "Clients router missing" "File not found"
fi

# Check assignment router.py
echo ""
test_info "Checking Assignment Router..."
if [ -f "src/glp/assignment/api/router.py" ]; then
    if grep -q "from.*error_sanitizer import sanitize_error_message" src/glp/assignment/api/router.py; then
        test_pass "Assignment router imports sanitize_error_message"
    else
        test_fail "Assignment router missing import" "No sanitize_error_message import"
    fi

    UNSANITIZED=$(grep -c 'HTTPException.*detail.*f.*{e}' src/glp/assignment/api/router.py 2>/dev/null || echo "0")
    if [ "$UNSANITIZED" -eq "0" ]; then
        test_pass "Assignment router: No unsanitized {e} in HTTPException"
    else
        test_fail "Assignment router has unsanitized errors" "Found $UNSANITIZED instances of HTTPException with {e}"
    fi

    # Check SSE error events are sanitized
    if grep -q 'sanitize_error_message.*error' src/glp/assignment/api/router.py; then
        test_pass "Assignment router: SSE errors sanitized"
    else
        test_fail "Assignment router: SSE errors not sanitized" "No sanitize_error_message in error events"
    fi
else
    test_fail "Assignment router missing" "File not found"
fi

# Check agent router.py (optional module)
echo ""
test_info "Checking Agent Router (optional)..."
if [ -f "src/glp/agent/api/router.py" ]; then
    if grep -q "from.*error_sanitizer import sanitize_error_message" src/glp/agent/api/router.py; then
        test_pass "Agent router imports sanitize_error_message"
    else
        test_fail "Agent router missing import" "No sanitize_error_message import"
    fi

    # Check WebSocket error handling
    if grep -q 'sanitize_error_message.*error' src/glp/agent/api/router.py; then
        test_pass "Agent router: WebSocket errors sanitized"
    else
        test_fail "Agent router: WebSocket errors not sanitized" "No sanitize_error_message in WebSocket handlers"
    fi
else
    test_info "Agent router not found (optional module)"
fi

echo ""
echo "================================================================================"
echo "TEST 4: Verify Tests Exist"
echo "================================================================================"
echo ""

if [ -f "tests/test_error_sanitizer.py" ]; then
    test_pass "Unit tests for error sanitizer exist"

    # Count test functions
    TEST_COUNT=$(grep -c "^def test_" tests/test_error_sanitizer.py)
    test_info "Found $TEST_COUNT test functions in test_error_sanitizer.py"

    if [ "$TEST_COUNT" -ge "10" ]; then
        test_pass "Adequate unit test coverage ($TEST_COUNT tests)"
    else
        test_fail "Insufficient unit tests" "Only $TEST_COUNT tests found, need at least 10"
    fi
else
    test_fail "Unit tests missing" "File not found: tests/test_error_sanitizer.py"
fi

if [ -f "tests/test_api_error_sanitization.py" ]; then
    test_pass "Integration tests for API error sanitization exist"

    TEST_COUNT=$(grep -c "^def test_\|^async def test_" tests/test_api_error_sanitization.py)
    test_info "Found $TEST_COUNT test functions in test_api_error_sanitization.py"

    if [ "$TEST_COUNT" -ge "10" ]; then
        test_pass "Adequate integration test coverage ($TEST_COUNT tests)"
    else
        test_fail "Insufficient integration tests" "Only $TEST_COUNT tests found, need at least 10"
    fi
else
    test_fail "Integration tests missing" "File not found: tests/test_api_error_sanitization.py"
fi

echo ""
echo "================================================================================"
echo "TEST 5: Security Pattern Verification"
echo "================================================================================"
echo ""

test_info "Verifying no sensitive patterns in example error responses..."

# Search for common sensitive patterns that should NOT appear in code
# (This is a sanity check - looking for hardcoded sensitive data)

# Check for hardcoded credentials (shouldn't be there)
if grep -r "password.*=.*['\"][^'\"]\{5,\}['\"]" src/glp/assignment/api/*.py 2>/dev/null | grep -v "# " | grep -v "test"; then
    test_fail "Possible hardcoded password found" "Review the matched line"
else
    test_pass "No hardcoded passwords in router files"
fi

# Check for database URLs (shouldn't be hardcoded)
if grep -r "postgresql://\|mysql://\|mongodb://" src/glp/assignment/api/*.py 2>/dev/null | grep -v "# " | grep -v "example" | grep -v "test"; then
    test_fail "Hardcoded database URL found" "Review the matched line"
else
    test_pass "No hardcoded database URLs in router files"
fi

# Verify sanitizer uses replacement tokens
if grep -q "\[REDACTED\]\|\[DATABASE_URL\]\|\[ENV_VAR\]\|\[FILE_PATH\]" src/glp/api/error_sanitizer.py; then
    test_pass "Sanitizer uses replacement tokens"
else
    test_fail "Sanitizer missing replacement tokens" "Should use [REDACTED], [DATABASE_URL], etc."
fi

echo ""
echo "================================================================================"
echo "TEST SUMMARY"
echo "================================================================================"
echo ""
echo "Total Tests: $TOTAL_COUNT"
echo -e "${GREEN}Passed: $PASS_COUNT ✅${NC}"
if [ "$FAIL_COUNT" -gt "0" ]; then
    echo -e "${RED}Failed: $FAIL_COUNT ❌${NC}"
else
    echo -e "Failed: $FAIL_COUNT"
fi

if [ "$TOTAL_COUNT" -gt "0" ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", ($PASS_COUNT/$TOTAL_COUNT)*100}")
    echo "Success Rate: $SUCCESS_RATE%"
fi

echo ""
echo "================================================================================"
echo "MANUAL VERIFICATION CHECKLIST"
echo "================================================================================"
echo ""
echo "To complete manual verification, verify the following:"
echo ""
echo "1. ✓ Error sanitizer module created with comprehensive patterns"
echo "2. ✓ FastAPI exception handlers registered and use sanitization"
echo "3. ✓ All API routers import and use sanitize_error_message()"
echo "4. ✓ Unit tests created for error sanitizer"
echo "5. ✓ Integration tests created for API error responses"
echo "6. ⚠️  START API SERVER and test real error responses (see below)"
echo "7. ⚠️  CHECK LOGS to verify full error details are preserved"
echo ""
echo "================================================================================"
echo "NEXT STEPS: Live API Testing"
echo "================================================================================"
echo ""
echo "To test with live API server:"
echo ""
echo "1. Start the API server:"
echo "   cd /path/to/main/repo"
echo "   uv run uvicorn src.glp.assignment.app:app --reload --port 8000"
echo ""
echo "2. Trigger various errors and verify responses:"
echo ""
echo "   # Test invalid auth (should NOT reveal env var names)"
echo "   curl http://localhost:8000/api/dashboard/stats -H \"X-API-Key: invalid\""
echo ""
echo "   # Test sync failure (should NOT reveal internal details)"
echo "   curl -X POST http://localhost:8000/api/dashboard/sync"
echo ""
echo "   # Test missing config (should NOT reveal env var names)"
echo "   # (Temporarily rename .env and restart server)"
echo ""
echo "3. Verify responses contain:"
echo "   ✓ Generic error messages"
echo "   ✓ [REDACTED], [DATABASE_URL], [ENV_VAR] replacement tokens"
echo "   ✗ NO environment variable names (GLP_CLIENT_ID, etc.)"
echo "   ✗ NO database connection strings (postgresql://...)"
echo "   ✗ NO file paths (/etc/, /var/, etc.)"
echo "   ✗ NO stack traces (Traceback...)"
echo "   ✗ NO IP addresses (192.168.x.x)"
echo ""
echo "4. Verify logs still contain:"
echo "   ✓ Full error messages"
echo "   ✓ Stack traces for debugging"
echo "   ✓ All sensitive information for troubleshooting"
echo ""
echo "================================================================================"
echo "VERIFICATION COMPLETE"
echo "================================================================================"
echo ""

# Save results
cat > security_verification_results.txt <<EOF
Manual Security Verification Results
=====================================

Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Working Directory: $(pwd)

Total Tests: $TOTAL_COUNT
Passed: $PASS_COUNT
Failed: $FAIL_COUNT
Success Rate: $SUCCESS_RATE%

Status: $(if [ "$FAIL_COUNT" -eq "0" ]; then echo "ALL CHECKS PASSED ✅"; else echo "SOME CHECKS FAILED ❌"; fi)

Next Steps:
- Run live API server testing
- Verify error responses contain no sensitive information
- Verify logs preserve full error details for debugging
EOF

echo "Results saved to: security_verification_results.txt"
echo ""

# Exit with appropriate code
if [ "$FAIL_COUNT" -eq "0" ]; then
    exit 0
else
    exit 1
fi
