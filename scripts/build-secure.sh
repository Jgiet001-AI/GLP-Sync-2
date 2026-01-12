#!/bin/bash
# =============================================================================
# Secure Docker Build Script with Attestations
# HPE GreenLake Sync Project
# =============================================================================
# This script builds Docker images with:
# - SBOM attestations
# - SLSA provenance
# - Pinned base image digests
# - Supply chain security metadata
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
IMAGE_NAME="${IMAGE_NAME:-glp-sync}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
REGISTRY="${REGISTRY:-}"  # e.g., ghcr.io/yourorg
PLATFORM="${PLATFORM:-linux/amd64,linux/arm64}"
BUILDER_NAME="glp-secure-builder"

# Build options
PUSH="${PUSH:-false}"
LOAD="${LOAD:-true}"
ATTESTATIONS="${ATTESTATIONS:-true}"

# Pinned digests (update these periodically)
PYTHON_DIGEST="${PYTHON_DIGEST:-sha256:1dd3dca85e22886e44fcad1bb7ccab6691dfa83db52214cf9e20696e095f3e36}"
UV_DIGEST="${UV_DIGEST:-sha256:816fdce3387ed2142e37d2e56e1b1b97ccc1ea87731ba199dc8a25c04e4997c5}"

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# -----------------------------------------------------------------------------
# Prerequisites Check
# -----------------------------------------------------------------------------

check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check Docker
    if ! command -v docker &>/dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    print_info "Docker: $(docker --version)"

    # Check Docker Buildx
    if ! docker buildx version &>/dev/null; then
        print_error "Docker Buildx is not available"
        exit 1
    fi
    print_info "Buildx: $(docker buildx version | head -1)"

    # Check if containerd image store is enabled (required for attestations)
    local storage_driver=$(docker info --format '{{.Driver}}' 2>/dev/null || echo "unknown")
    print_info "Storage driver: $storage_driver"

    # Check Docker Scout
    if docker scout version &>/dev/null; then
        print_info "Docker Scout: $(docker scout version 2>&1 | grep 'version:' | head -1)"
    else
        print_warn "Docker Scout not available - attestation verification will be limited"
    fi
}

# -----------------------------------------------------------------------------
# Setup Buildx Builder
# -----------------------------------------------------------------------------

setup_builder() {
    print_header "Setting Up Buildx Builder"

    # Check if builder exists
    if docker buildx inspect "$BUILDER_NAME" &>/dev/null; then
        print_info "Using existing builder: $BUILDER_NAME"
    else
        print_info "Creating new builder: $BUILDER_NAME"

        # Create builder with docker-container driver (supports attestations)
        docker buildx create \
            --name "$BUILDER_NAME" \
            --driver docker-container \
            --driver-opt network=host \
            --bootstrap

        print_success "Builder created: $BUILDER_NAME"
    fi

    # Use the builder
    docker buildx use "$BUILDER_NAME"
}

# -----------------------------------------------------------------------------
# Build Image
# -----------------------------------------------------------------------------

build_image() {
    print_header "Building Image"

    local full_tag="${IMAGE_NAME}:${IMAGE_TAG}"
    if [[ -n "$REGISTRY" ]]; then
        full_tag="${REGISTRY}/${full_tag}"
    fi

    print_info "Building: $full_tag"
    print_info "Dockerfile: $DOCKERFILE"
    print_info "Platform: $PLATFORM"

    # Build arguments
    local build_args=(
        "--file" "$DOCKERFILE"
        "--tag" "$full_tag"
        "--build-arg" "PYTHON_DIGEST=${PYTHON_DIGEST}"
        "--build-arg" "UV_DIGEST=${UV_DIGEST}"
        "--pull"  # Always pull latest base images
    )

    # Add attestations if enabled
    if [[ "$ATTESTATIONS" == "true" ]]; then
        print_info "Attestations: ENABLED (provenance + SBOM)"
        build_args+=(
            "--provenance=mode=max"
            "--sbom=true"
        )
    else
        print_warn "Attestations: DISABLED"
    fi

    # Add platform for multi-arch builds
    if [[ "$PLATFORM" == *","* ]]; then
        print_info "Multi-platform build: $PLATFORM"
        build_args+=("--platform" "$PLATFORM")
    fi

    # Load vs Push
    if [[ "$PUSH" == "true" ]]; then
        print_info "Will push to registry"
        build_args+=("--push")
    elif [[ "$LOAD" == "true" ]]; then
        print_info "Will load to local Docker"
        build_args+=("--load")

        # Can only load single platform
        if [[ "$PLATFORM" == *","* ]]; then
            print_warn "Multi-platform builds cannot be loaded locally. Using linux/amd64."
            build_args+=("--platform" "linux/amd64")
        fi
    fi

    # Add build context
    build_args+=(".")

    # Execute build
    print_info "Executing: docker buildx build ${build_args[*]}"
    echo ""

    if docker buildx build "${build_args[@]}"; then
        print_success "Build completed: $full_tag"
    else
        print_error "Build failed"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Verify Attestations
# -----------------------------------------------------------------------------

verify_attestations() {
    print_header "Verifying Attestations"

    local full_tag="${IMAGE_NAME}:${IMAGE_TAG}"
    if [[ -n "$REGISTRY" ]]; then
        full_tag="${REGISTRY}/${full_tag}"
    fi

    # Check SBOM
    print_info "Checking SBOM attestation..."
    if docker scout sbom "$full_tag" --format json 2>/dev/null | head -c 100 | grep -q "packages"; then
        print_success "SBOM attestation verified"
    else
        print_warn "SBOM attestation not found or incomplete"
    fi

    # Check provenance
    print_info "Checking provenance..."
    if docker buildx imagetools inspect "$full_tag" 2>/dev/null | grep -q "provenance"; then
        print_success "Provenance attestation verified"
    else
        print_warn "Provenance attestation not found (may require push to registry)"
    fi
}

# -----------------------------------------------------------------------------
# Run Scout Analysis
# -----------------------------------------------------------------------------

run_scout_analysis() {
    print_header "Running Docker Scout Analysis"

    local full_tag="${IMAGE_NAME}:${IMAGE_TAG}"

    if ! docker scout version &>/dev/null; then
        print_warn "Docker Scout not available, skipping analysis"
        return
    fi

    print_info "Quick vulnerability overview:"
    docker scout quickview "$full_tag" 2>&1 || true

    echo ""
    print_info "Critical/High CVEs:"
    docker scout cves "$full_tag" --only-severity critical,high 2>&1 | head -50 || true

    echo ""
    print_info "Base image recommendations:"
    docker scout recommendations "$full_tag" 2>&1 | head -30 || true
}

# -----------------------------------------------------------------------------
# Usage
# -----------------------------------------------------------------------------

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Build Docker image with security attestations.

Options:
    --push              Push to registry instead of loading locally
    --no-attestations   Disable SBOM and provenance attestations
    --tag TAG           Image tag (default: latest)
    --registry REG      Registry prefix (e.g., ghcr.io/org)
    --platform PLAT     Target platform(s) (default: linux/amd64,linux/arm64)
    --dockerfile FILE   Dockerfile to use (default: Dockerfile)
    --help              Show this help message

Environment Variables:
    IMAGE_NAME          Image name (default: glp-sync)
    IMAGE_TAG           Image tag (default: latest)
    PYTHON_DIGEST       Python base image digest
    UV_DIGEST           UV tool image digest

Examples:
    # Build locally with attestations
    $0

    # Build and push to registry
    $0 --push --registry ghcr.io/myorg

    # Build specific tag
    $0 --tag v1.0.0

    # Build without attestations (faster)
    $0 --no-attestations
EOF
    exit 0
}

# -----------------------------------------------------------------------------
# Parse Arguments
# -----------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH=true
            LOAD=false
            shift
            ;;
        --no-attestations)
            ATTESTATIONS=false
            shift
            ;;
        --tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --dockerfile)
            DOCKERFILE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------

print_header "Secure Docker Build - HPE GreenLake Sync"

check_prerequisites

# Check if using attestations with standard driver
if [[ "$ATTESTATIONS" == "true" ]]; then
    # Need docker-container driver for attestations
    setup_builder
fi

build_image

if [[ "$ATTESTATIONS" == "true" ]]; then
    verify_attestations
fi

run_scout_analysis

print_header "Build Complete"
echo -e "${GREEN}Image ready: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"

# Print next steps
echo ""
echo "Next steps:"
echo "  1. Run policy check: ./scripts/docker-scout-check.sh"
echo "  2. Test locally: docker compose up -d"
echo "  3. Push to registry: $0 --push --registry your-registry"
