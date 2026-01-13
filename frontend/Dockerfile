# =============================================================================
# GLP Frontend - Production Dockerfile (Security Hardened)
# =============================================================================
# Multi-stage build: Node.js build -> Nginx serve
# Final image: ~25MB (nginx:alpine + static files)
#
# Security Features:
# - Alpine base images (minimal CVE surface)
# - Base images pinned by digest
# - Non-root user (nginx)
# - Unprivileged port 8080
# - Security headers via nginx.conf
#
# Docker Scout Target: A/B rating
# =============================================================================

# -----------------------------------------------------------------------------
# Build Arguments (update digests regularly)
# -----------------------------------------------------------------------------
ARG NODE_DIGEST=sha256:0340fa682d72068edf603c305bfbc10e23219fb0e40df58d9ea4d6f33a9798bf
ARG NGINX_DIGEST=sha256:c083c3799197cfff91fe5c3c558db3d2eea65ccbbfd419fa42a64d2c39a24027

# -----------------------------------------------------------------------------
# Stage 1: Build the application
# -----------------------------------------------------------------------------
FROM node:22-alpine@${NODE_DIGEST} AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline --no-audit

# Copy source files
COPY . .

# Build the application
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Serve with Nginx
# -----------------------------------------------------------------------------
FROM nginx:1-alpine@${NGINX_DIGEST} AS production

# Add labels for provenance tracking
LABEL org.opencontainers.image.title="GLP Frontend"
LABEL org.opencontainers.image.description="React frontend for HPE GreenLake Device Assignment"
LABEL org.opencontainers.image.vendor="HPE"
LABEL org.opencontainers.image.source="https://github.com/hpe/glp-sync"
LABEL org.opencontainers.image.base.name="docker.io/library/nginx:1-alpine"
LABEL org.opencontainers.image.base.digest="${NGINX_DIGEST}"

# Copy nginx configuration
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Setup permissions for non-root operation
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html && \
    mkdir -p /var/cache/nginx /var/run && \
    chown -R nginx:nginx /var/cache/nginx /var/run && \
    touch /var/run/nginx.pid && \
    chown nginx:nginx /var/run/nginx.pid && \
    # Create startup script for envsubst (API_KEY injection)
    printf '#!/bin/sh\nif [ -n "$API_KEY" ]; then\n  envsubst "\\$API_KEY" < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf\nfi\nexec nginx -g "daemon off;"\n' > /docker-entrypoint.sh && \
    chmod +x /docker-entrypoint.sh && \
    chown nginx:nginx /docker-entrypoint.sh /etc/nginx/conf.d/default.conf

# Use non-root user
USER nginx

# Expose unprivileged port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:8080/health || exit 1

# Start nginx
CMD ["/docker-entrypoint.sh"]

# =============================================================================
# Update Digests (run periodically for security):
#
#   docker pull node:22-alpine
#   docker inspect node:22-alpine --format='{{index .RepoDigests 0}}'
#
#   docker pull nginx:1-alpine
#   docker inspect nginx:1-alpine --format='{{index .RepoDigests 0}}'
#
# Then update NODE_DIGEST and NGINX_DIGEST above.
# =============================================================================
