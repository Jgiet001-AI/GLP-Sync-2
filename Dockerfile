# =============================================================================
# HPE GreenLake Sync - Production Dockerfile (Security Hardened)
# =============================================================================
# Multi-stage build with Alpine base for minimal CVEs
# Final image: ~80MB (python:alpine + deps)
#
# Security Features:
# - Alpine base (minimal CVE surface)
# - Base images pinned by digest
# - Non-root user (appuser)
# - No secrets in image layers
# - Health checks enabled
#
# Docker Scout Target: A/B rating
# =============================================================================

# -----------------------------------------------------------------------------
# Build Arguments (update digests regularly with: docker pull <image>)
# -----------------------------------------------------------------------------
ARG PYTHON_VERSION=3.12
ARG PYTHON_DIGEST=sha256:68d81cd281ee785f48cdadecb6130d05ec6957f1249814570dc90e5100d3b146

# -----------------------------------------------------------------------------
# Stage 0: UV installer
# -----------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:latest AS uv

# -----------------------------------------------------------------------------
# Stage 1: Build dependencies
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-alpine@${PYTHON_DIGEST} AS builder

WORKDIR /app

# Install build dependencies for Python packages with C extensions
# postgresql-dev: for psycopg2
# gcc, musl-dev: for compiling C extensions
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    postgresql-dev

# Install uv for fast dependency management
COPY --from=uv /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml README.md ./
COPY uv.lock* ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# -----------------------------------------------------------------------------
# Stage 2: Production image
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-alpine@${PYTHON_DIGEST} AS production

# Add labels for provenance tracking
LABEL org.opencontainers.image.title="HPE GreenLake Sync"
LABEL org.opencontainers.image.description="Syncs device and subscription inventory from HPE GreenLake Platform"
LABEL org.opencontainers.image.vendor="HPE"
LABEL org.opencontainers.image.source="https://github.com/hpe/glp-sync"
LABEL org.opencontainers.image.base.name="docker.io/library/python:3.12-alpine"
LABEL org.opencontainers.image.base.digest="${PYTHON_DIGEST}"

WORKDIR /app

# Install runtime dependencies only (no build tools)
# libpq: PostgreSQL client library (runtime)
# ca-certificates: for HTTPS calls to GLP/Aruba endpoints
RUN apk add --no-cache \
    libpq \
    ca-certificates \
    && rm -rf /var/cache/apk/*

# Create non-root user for security
RUN adduser -D -h /app -s /sbin/nologin -u 1000 appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
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

# =============================================================================
# Update Digests (run periodically for security):
#
#   docker pull python:3.12-alpine
#   docker inspect python:3.12-alpine --format='{{index .RepoDigests 0}}'
#
# Then update PYTHON_DIGEST above with the new sha256 value.
# =============================================================================
