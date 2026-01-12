#!/bin/bash
# =============================================================================
# Docker Scout Policy Compliance Check Script
# HPE GreenLake Sync Project
# =============================================================================
# This script validates Docker images against the 7 Docker Scout policy scores:
# 1. No high-profile vulnerabilities
# 2. No fixable critical/high vulnerabilities
# 3. Only approved base images
# 4. Supply chain attestations
# 5. No outdated base images
# 6. No AGPL v3 licenses
# 7. Default non-root user
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CUSTOM_IMAGE="${CUSTOM_IMAGE:-glp-sync:latest}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16-alpine}"
PYTHON_BASE="${PYTHON_BASE:-python:3.11-slim}"
REPORT_DIR="${REPORT_DIR:-./scout-reports}"
DOCKER_ORG="${DOCKER_ORG:-}"  # Set your Docker Scout org if using

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

print_header() {
    echo -e "\n${BLUE}==============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==============================================================================${NC}\n"
}

print_section() {
    echo -e "\n${YELLOW}--- $1 ---${NC}\n"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

print_header "Docker Scout Policy Compliance Check"

# Create report directory
mkdir -p "$REPORT_DIR"

# Check Docker Scout availability
if ! docker scout version &>/dev/null; then
    print_fail "Docker Scout CLI not available"
    echo "Install Docker Scout: https://docs.docker.com/scout/install/"
    exit 1
fi

print_info "Docker Scout version: $(docker scout version 2>&1 | grep 'version:' | head -1)"

# -----------------------------------------------------------------------------
# Policy 1 & 2: Vulnerability Checks
# -----------------------------------------------------------------------------

check_vulnerabilities() {
    local image=$1
    local name=$2

    print_section "Policy 1 & 2: Vulnerability Check - $name"

    # Get CVE summary
    print_info "Scanning $image for vulnerabilities..."

    # Check for critical vulnerabilities
    local crit_count=$(docker scout cves "$image" --only-severity critical --format json 2>/dev/null | jq '.vulnerabilities | length' 2>/dev/null || echo "0")
    local high_count=$(docker scout cves "$image" --only-severity high --format json 2>/dev/null | jq '.vulnerabilities | length' 2>/dev/null || echo "0")

    # Check for fixable vulnerabilities
    local fixable_crit=$(docker scout cves "$image" --only-severity critical --only-fixed --format json 2>/dev/null | jq '.vulnerabilities | length' 2>/dev/null || echo "0")
    local fixable_high=$(docker scout cves "$image" --only-severity high --only-fixed --format json 2>/dev/null | jq '.vulnerabilities | length' 2>/dev/null || echo "0")

    echo "  Critical: $crit_count (Fixable: $fixable_crit)"
    echo "  High: $high_count (Fixable: $fixable_high)"

    # Policy 1: No high-profile vulnerabilities
    if [[ "$crit_count" -eq 0 ]]; then
        print_pass "Policy 1: No critical vulnerabilities in $name"
    else
        print_fail "Policy 1: Found $crit_count critical vulnerabilities in $name"
    fi

    # Policy 2: No fixable critical/high
    if [[ "$fixable_crit" -eq 0 && "$fixable_high" -eq 0 ]]; then
        print_pass "Policy 2: No fixable critical/high vulnerabilities in $name"
    else
        print_fail "Policy 2: Found fixable vulnerabilities in $name (Critical: $fixable_crit, High: $fixable_high)"
    fi

    # Save detailed report
    docker scout cves "$image" --format json > "$REPORT_DIR/${name//[:\/]/_}_cves.json" 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# Policy 3: Approved Base Images
# -----------------------------------------------------------------------------

check_base_images() {
    local image=$1
    local name=$2

    print_section "Policy 3: Approved Base Images - $name"

    # Get base image info
    local base_info=$(docker scout quickview "$image" 2>&1 | grep -E "Base image|digest" || echo "Unknown")
    echo "  Base image info:"
    echo "$base_info" | sed 's/^/    /'

    # Check if using official images
    if echo "$base_info" | grep -qE "(python|postgres|alpine|debian)"; then
        print_pass "Policy 3: $name uses approved official base image"
    else
        print_warn "Policy 3: $name base image should be verified against allowlist"
    fi
}

# -----------------------------------------------------------------------------
# Policy 4: Supply Chain Attestations
# -----------------------------------------------------------------------------

check_attestations() {
    local image=$1
    local name=$2

    print_section "Policy 4: Supply Chain Attestations - $name"

    # Check for SBOM
    local sbom_check=$(docker scout sbom "$image" --format json 2>&1 | head -c 100)
    if [[ "$sbom_check" == *"packages"* ]] || [[ "$sbom_check" == *"source"* ]]; then
        print_pass "Policy 4: SBOM available for $name"
    else
        print_warn "Policy 4: SBOM not available or incomplete for $name"
    fi

    # Check for provenance (from quickview)
    local provenance=$(docker scout quickview "$image" 2>&1 | grep -i "provenance" || echo "")
    if [[ -n "$provenance" ]]; then
        print_pass "Policy 4: Provenance attestation found for $name"
        echo "  $provenance"
    else
        print_warn "Policy 4: Provenance attestation not found for $name"
    fi
}

# -----------------------------------------------------------------------------
# Policy 5: No Outdated Base Images
# -----------------------------------------------------------------------------

check_freshness() {
    local image=$1
    local name=$2

    print_section "Policy 5: Base Image Freshness - $name"

    # Get recommendations
    local recommendations=$(docker scout recommendations "$image" 2>&1 | head -30)

    if echo "$recommendations" | grep -q "up to date"; then
        print_pass "Policy 5: $name base image is up to date"
    elif echo "$recommendations" | grep -q "No recommendations"; then
        print_pass "Policy 5: $name has no update recommendations"
    else
        print_warn "Policy 5: $name may have base image updates available"
        echo "$recommendations" | grep -E "(Tag|Benefits)" | head -10 | sed 's/^/    /'
    fi
}

# -----------------------------------------------------------------------------
# Policy 6: License Check (No AGPL)
# -----------------------------------------------------------------------------

check_licenses() {
    local image=$1
    local name=$2

    print_section "Policy 6: License Compliance - $name"

    # Check for AGPL licenses
    local agpl_check=$(docker scout sbom "$image" 2>/dev/null | grep -iE '"licen' | grep -iE 'agpl' || echo "")

    if [[ -z "$agpl_check" ]]; then
        print_pass "Policy 6: No AGPL licenses found in $name"
    else
        print_fail "Policy 6: AGPL licenses detected in $name"
        echo "$agpl_check" | head -5 | sed 's/^/    /'
    fi
}

# -----------------------------------------------------------------------------
# Policy 7: Non-Root User
# -----------------------------------------------------------------------------

check_nonroot() {
    local image=$1
    local name=$2

    print_section "Policy 7: Non-Root User - $name"

    # Check USER in image config
    local user=$(docker inspect "$image" --format '{{.Config.User}}' 2>/dev/null || echo "")

    if [[ -n "$user" && "$user" != "root" && "$user" != "0" ]]; then
        print_pass "Policy 7: $name runs as non-root user: $user"
    elif [[ -z "$user" ]]; then
        print_warn "Policy 7: $name has no explicit USER set (may use entrypoint to switch)"

        # Additional runtime check
        local runtime_user=$(docker run --rm --entrypoint '' "$image" id -u 2>/dev/null || echo "error")
        if [[ "$runtime_user" != "0" && "$runtime_user" != "error" ]]; then
            print_pass "Policy 7: $name runtime user is non-root (UID: $runtime_user)"
        fi
    else
        print_fail "Policy 7: $name runs as root"
    fi
}

# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------

print_header "Checking Images"

# Check if custom image exists
if docker image inspect "$CUSTOM_IMAGE" &>/dev/null; then
    print_info "Custom image found: $CUSTOM_IMAGE"
    IMAGES_TO_CHECK=("$CUSTOM_IMAGE" "$POSTGRES_IMAGE")
else
    print_warn "Custom image not found: $CUSTOM_IMAGE"
    print_info "Checking base images only"
    IMAGES_TO_CHECK=("$PYTHON_BASE" "$POSTGRES_IMAGE")
fi

# Run all checks
for img in "${IMAGES_TO_CHECK[@]}"; do
    print_header "Analyzing: $img"

    # Pull if needed
    if ! docker image inspect "$img" &>/dev/null; then
        print_info "Pulling image: $img"
        docker pull "$img" 2>&1 | tail -1
    fi

    check_vulnerabilities "$img" "$img"
    check_base_images "$img" "$img"
    check_attestations "$img" "$img"
    check_freshness "$img" "$img"
    check_licenses "$img" "$img"
    check_nonroot "$img" "$img"
done

# -----------------------------------------------------------------------------
# Summary Report
# -----------------------------------------------------------------------------

print_header "Policy Compliance Summary"

echo -e "Results:"
echo -e "  ${GREEN}Passed:${NC}   $PASSED"
echo -e "  ${RED}Failed:${NC}   $FAILED"
echo -e "  ${YELLOW}Warnings:${NC} $WARNINGS"
echo ""

# Calculate compliance score
TOTAL=$((PASSED + FAILED))
if [[ $TOTAL -gt 0 ]]; then
    SCORE=$((PASSED * 100 / TOTAL))
    echo -e "Compliance Score: ${BLUE}${SCORE}%${NC}"
fi

# Save summary
cat > "$REPORT_DIR/summary.json" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "images_checked": ${#IMAGES_TO_CHECK[@]},
  "passed": $PASSED,
  "failed": $FAILED,
  "warnings": $WARNINGS,
  "compliance_score": $SCORE
}
EOF

print_info "Reports saved to: $REPORT_DIR/"

# Exit code based on failures
if [[ $FAILED -gt 0 ]]; then
    echo -e "\n${RED}Policy compliance check FAILED${NC}"
    exit 1
else
    echo -e "\n${GREEN}Policy compliance check PASSED${NC}"
    exit 0
fi
