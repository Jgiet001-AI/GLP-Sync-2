# =============================================================================
# HPE GreenLake Sync - Production Dockerfile (Security Hardened)
# =============================================================================
# Multi-stage build for minimal image size
# Final image: ~150MB (python:3.11-slim + deps)
#
# Security Features:
# - Base images pinned by digest
# - Non-root user (appuser)
# - Minimal attack surface (slim base)
# - No secrets in image layers
# - Health checks enabled
# =============================================================================

# -----------------------------------------------------------------------------
# Build Arguments (for digest updates)
# -----------------------------------------------------------------------------
ARG PYTHON_VERSION=3.11
ARG PYTHON_DIGEST=sha256:1dd3dca85e22886e44fcad1bb7ccab6691dfa83db52214cf9e20696e095f3e36

# -----------------------------------------------------------------------------
# Stage 0: UV installer (workaround for --from not supporting ARG)
# -----------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:latest AS uv

# -----------------------------------------------------------------------------
# Stage 1: Build dependencies
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim@${PYTHON_DIGEST} AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=uv /uv /usr/local/bin/uv

# Copy dependency files (README.md needed by pyproject.toml)
COPY pyproject.toml README.md ./
COPY uv.lock* ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# -----------------------------------------------------------------------------
# Stage 2: Production image
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim@${PYTHON_DIGEST} AS production

# Add labels for provenance tracking
LABEL org.opencontainers.image.title="HPE GreenLake Sync"
LABEL org.opencontainers.image.description="Syncs device and subscription inventory from HPE GreenLake Platform"
LABEL org.opencontainers.image.vendor="HPE"
LABEL org.opencontainers.image.source="https://github.com/hpe/glp-sync"
LABEL org.opencontainers.image.base.name="docker.io/library/python:3.11-slim"
LABEL org.opencontainers.image.base.digest="${PYTHON_DIGEST}"

WORKDIR /app

# Install runtime dependencies only
# ca-certificates required for HTTPS calls to GLP endpoints
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security (Policy 7)
# Using UID 1000 to avoid conflicts and meet policy requirements
# FIX: Use nologin shell to reduce attack surface (Codex recommendation)
RUN useradd --home-dir /app --shell /usr/sbin/nologin --uid 1000 --no-create-home appuser

# Copy virtual environment from builder with correct ownership
# FIX: Use --chown to avoid extra chown layer (Codex recommendation)
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code with correct ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser main.py scheduler.py server.py ./

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/')" || exit 1

# Default environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SYNC_INTERVAL_MINUTES=60 \
    SYNC_DEVICES=true \
    SYNC_SUBSCRIPTIONS=true \
    SYNC_ON_STARTUP=true \
    HEALTH_CHECK_PORT=8080

# Expose health check port
EXPOSE 8080

# Default command: run scheduler
CMD ["python", "scheduler.py"]

# -----------------------------------------------------------------------------
# Build Commands:
#
# Standard build:
#   docker build -t glp-sync:latest .
#
# Build with attestations (requires containerd image store):
#   docker buildx build \
#     --pull \
#     --provenance=mode=max \
#     --sbom=true \
#     --tag glp-sync:latest \
#     --load .
#
# Update base image digest:
#   docker buildx build \
#     --build-arg PYTHON_DIGEST=sha256:NEW_DIGEST \
#     --tag glp-sync:latest .
# -----------------------------------------------------------------------------
