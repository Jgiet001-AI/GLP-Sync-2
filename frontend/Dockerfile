# =============================================================================
# GLP Frontend - Production Dockerfile
# =============================================================================
# Multi-stage build: Node.js build -> Nginx serve
# Final image: ~25MB (nginx:alpine + static files)
#
# Security Features:
# - Base images pinned by digest for reproducibility
# - Non-root user (nginx)
# - Unprivileged port 8080
# - Minimal attack surface (alpine base)
# - Security headers via nginx.conf
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build the application
# -----------------------------------------------------------------------------
# Pinned by digest for reproducibility and security
FROM node:20-alpine@sha256:658d0f63e501824d6c23e06d4bb95c71e7d704537c9d9272f488ac03a370d448 AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline --no-audit

# Copy source files
COPY . .

# Build the application
# Note: Build-time env vars can be passed via --build-arg
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Serve with Nginx
# -----------------------------------------------------------------------------
# Pinned by digest for reproducibility and security
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS production

# Add labels for provenance tracking
LABEL org.opencontainers.image.title="GLP Frontend"
LABEL org.opencontainers.image.description="React frontend for HPE GreenLake Device Assignment"
LABEL org.opencontainers.image.vendor="HPE"
LABEL org.opencontainers.image.source="https://github.com/hpe/glp-sync"
LABEL org.opencontainers.image.base.name="docker.io/library/nginx:1.27-alpine"

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Ensure correct ownership (nginx user is UID 101 on Alpine)
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html && \
    # Create cache directories with correct permissions
    mkdir -p /var/cache/nginx /var/run && \
    chown -R nginx:nginx /var/cache/nginx /var/run && \
    # Create pid file location with correct permissions
    touch /var/run/nginx.pid && \
    chown nginx:nginx /var/run/nginx.pid

# Use non-root user
USER nginx

# Expose unprivileged port (non-root can't bind to 80)
EXPOSE 8080

# Health check on unprivileged port
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:8080/health || exit 1

# Start nginx in foreground
CMD ["nginx", "-g", "daemon off;"]

# -----------------------------------------------------------------------------
# Build Commands:
#
# Standard build:
#   docker build -t glp-frontend:latest -f frontend/Dockerfile frontend/
#
# Build with custom API URL:
#   docker build \
#     --build-arg VITE_API_URL=https://api.example.com \
#     -t glp-frontend:latest \
#     -f frontend/Dockerfile frontend/
#
# Multi-arch build:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     --push \
#     -t yourorg/glp-frontend:latest \
#     -f frontend/Dockerfile frontend/
# -----------------------------------------------------------------------------
