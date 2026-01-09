# ============================================
# HPE GreenLake Sync - Production Dockerfile
# ============================================
# Multi-stage build for minimal image size
# Final image: ~150MB (python:3.11-slim + deps)

# ----------------------------------------
# Stage 1: Build dependencies
# ----------------------------------------
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml ./
COPY uv.lock* ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# ----------------------------------------
# Stage 2: Production image
# ----------------------------------------
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY src/ ./src/
COPY main.py scheduler.py ./

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
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

# ----------------------------------------
# Alternative: One-time sync (override CMD)
# docker run glp-sync python main.py --all
# ----------------------------------------