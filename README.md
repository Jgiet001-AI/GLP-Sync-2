# HPE GreenLake Device & Subscription Sync

[![CI](https://github.com/Jgiet001-AI/GLP-Sync-2/actions/workflows/ci.yml/badge.svg)](https://github.com/Jgiet001-AI/GLP-Sync-2/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.2.0-green)](https://github.com/Jgiet001-AI/GLP-Sync-2/releases)
[![Docker Hub](https://img.shields.io/badge/docker-jgiet001%2Fglp--sync-blue?logo=docker)](https://hub.docker.com/r/jgiet001/glp-sync)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive platform for syncing device and subscription inventory from HPE GreenLake Platform to PostgreSQL, with a React dashboard, AI chatbot, and Aruba Central integration.

## Table of Contents

- [Features](#features)
  - [Core Sync](#core-sync)
  - [Web Dashboard](#web-dashboard)
  - [AI Agent Chatbot](#ai-agent-chatbot)
  - [Integrations](#integrations)
- [Screenshots](#screenshots)
  - [Dashboard Overview](#dashboard-overview)
  - [Device Assignment Workflow](#device-assignment-workflow)
  - [AI Chatbot Interface](#ai-chatbot-interface)
- [Quick Start](#quick-start)
  - [Option 1: Interactive Setup Wizard](#option-1-interactive-setup-wizard-recommended)
  - [Option 2: Manual Docker Compose](#option-2-manual-docker-compose)
  - [Option 3: Production Deployment](#option-3-production-deployment-docker-hub-images)
- [Docker Architecture](#docker-architecture)
  - [Services](#services)
  - [Docker Hub Images](#docker-hub-images)
  - [Security Features](#security-features)
- [Environment Variables](#environment-variables)
  - [Required](#required)
  - [Optional](#optional)
  - [Aruba Central](#aruba-central-optional)
- [CLI Usage](#cli-usage)
- [API Endpoints](#api-endpoints)
  - [Dashboard API](#dashboard-api-api)
  - [Agent API](#agent-api-apiagent)
  - [MCP Server](#mcp-server-port-8010)
- [Project Structure](#project-structure)
- [Database Schema](#database-schema)
  - [Tables](#tables)
  - [Views](#views)
- [Development](#development)
  - [Local Setup](#local-setup)
  - [Testing](#testing)
  - [Linting](#linting)
- [CI/CD](#cicd)
  - [GitHub Actions](#github-actions)
  - [Required Secrets](#required-secrets)
  - [Required Variables](#required-variables)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
  - [Docker Container Issues](#docker-container-issues)
  - [Database Connection Problems](#database-connection-problems)
  - [GreenLake API Authentication Failures](#greenlake-api-authentication-failures)
  - [Frontend Connection Issues](#frontend-connection-issues)
  - [AI Chatbot Problems](#ai-chatbot-problems)
  - [Performance and Sync Issues](#performance-and-sync-issues)
  - [Setup Wizard Issues](#setup-wizard-issues)
  - [Common Error Messages](#common-error-messages)
  - [Getting Help](#getting-help)
- [Contributing](#contributing)
- [Security](#security)
  - [Environment Variables and Secrets](#environment-variables-and-secrets)
  - [Authentication and Authorization](#authentication-and-authorization)
  - [Database Security](#database-security)
  - [Docker Security Hardening](#docker-security-hardening)
  - [Network Security](#network-security)
  - [WebSocket Security](#websocket-security)
  - [Production Deployment Checklist](#production-deployment-checklist)
  - [CI/CD Security](#cicd-security)
  - [Security Disclosure Policy](#security-disclosure-policy)
  - [Security Best Practices Summary](#security-best-practices-summary)
  - [Additional Resources](#additional-resources)
- [License](#license)

## Features

### Core Sync
- **OAuth2 Authentication** - Automatic token refresh with dynamic buffer (10% of TTL, 30s-5min)
- **Paginated Fetching** - Devices: 2,000/page, Subscriptions: 50/page
- **PostgreSQL Sync** - Upsert with JSONB storage + normalized tables
- **Full-Text Search** - Search devices by serial, name, model
- **Scheduler** - Automated sync at configurable intervals
- **Circuit Breaker** - Resilience layer with automatic recovery

### Web Dashboard
- **React Frontend** - Modern UI with TailwindCSS
- **Device Assignment** - Bulk assign subscriptions, regions, and tags
- **Real-time Progress** - Server-Sent Events for operation tracking
- **Command Palette** - Quick navigation (Cmd+K)

### AI Agent Chatbot
- **Multi-Provider** - Anthropic Claude (primary) and OpenAI GPT (fallback) support
- **OpenAI Embeddings** - Semantic memory search with text-embedding-3-large
- **MCP Tools** - 27 read-only database tools for AI assistants
- **WebSocket Streaming** - Real-time chat with ticket authentication
- **Memory Patterns** - Conversation history and semantic search

### Integrations
- **Aruba Central** - Device and client sync from Aruba
- **Docker Hub** - Automated multi-arch image publishing
- **GitHub Actions** - CI/CD with vulnerability scanning

## Screenshots

### Dashboard Overview
<!--
Screenshot placeholder: Dashboard Overview
- Show the main dashboard with device/subscription counts
- Include filter panel and search functionality
- Display device cards with status indicators
Path: docs/screenshots/dashboard-overview.png
-->

<div align="center">
  <img src="docs/screenshots/dashboard-overview.png" alt="Dashboard Overview" width="800">
  <p><em>Modern React dashboard with device inventory, filters, and real-time search</em></p>
</div>

### Device Assignment Workflow
<!--
Screenshot placeholder: Device Assignment Workflow
- Show Excel upload interface
- Display assignment preview with validation
- Include SSE progress streaming
Path: docs/screenshots/device-assignment.png
-->

<div align="center">
  <img src="docs/screenshots/device-assignment.png" alt="Device Assignment Workflow" width="800">
  <p><em>Bulk device assignment with Excel upload and real-time progress tracking</em></p>
</div>

### AI Chatbot Interface
<!--
Screenshot placeholder: AI Chatbot Interface
- Show chat widget with conversation history
- Display MCP tool integration
- Include example queries and responses
Path: docs/screenshots/ai-chatbot.png
-->

<div align="center">
  <img src="docs/screenshots/ai-chatbot.png" alt="AI Chatbot Interface" width="800">
  <p><em>AI-powered chatbot with semantic memory and 27 database tools</em></p>
</div>

> **Note:** Screenshots will be added once the feature is fully deployed. The placeholders above indicate the planned visual documentation.

## Quick Start

### Option 1: Interactive Setup Wizard (Recommended)

```bash
# Clone the repository
git clone https://github.com/Jgiet001-AI/GLP-Sync-2.git
cd GLP-Sync-2

# Make setup script executable and run it
chmod +x setup.sh
./setup.sh
```

The wizard will guide you through:
- GreenLake API credentials
- PostgreSQL configuration
- API security settings (dev/production mode)
- AI chatbot provider selection
- Deployment mode (local build vs Docker Hub images)

### Option 2: Manual Docker Compose

```bash
# Clone the repository
git clone https://github.com/Jgiet001-AI/GLP-Sync-2.git
cd GLP-Sync-2

# Create .env file from template
cp .env.example .env
nano .env  # Edit with your credentials

# Start all services (development mode - builds locally)
docker compose up -d

# View logs
docker compose logs -f

# Access the dashboard
open http://localhost
```

### Option 3: Production Deployment (Docker Hub Images)

```bash
# Clone the repository
git clone https://github.com/Jgiet001-AI/GLP-Sync-2.git
cd GLP-Sync-2

# Create .env file
cp .env.example .env
nano .env  # Edit with your credentials

# Pull pre-built images from Docker Hub
docker pull jgiet001/glp-sync:latest
docker pull jgiet001/glp-frontend:latest
docker pull jgiet001/glp-mcp-server:latest
docker pull jgiet001/glp-scheduler:latest

# Start all services
docker compose up -d
```

## Docker Architecture

### Services

| Service | Port | Description |
|---------|------|-------------|
| `postgres` | 5432 | PostgreSQL 16 with pgvector |
| `redis` | 6379 | WebSocket ticket authentication |
| `scheduler` | 8080 | Automated sync scheduler |
| `api-server` | 8000 | FastAPI backend |
| `mcp-server` | 8010 | MCP server for AI assistants |
| `frontend` | 80 | React dashboard (nginx) |

### Docker Hub Images

| Image | Description |
|-------|-------------|
| `jgiet001/glp-sync` | Backend API server |
| `jgiet001/glp-frontend` | React dashboard |
| `jgiet001/glp-mcp-server` | MCP server for AI assistants |
| `jgiet001/glp-scheduler` | Automated sync scheduler |

### Security Features

- Base images pinned by SHA256 digest (Python 3.12-alpine, Node 22-alpine, nginx 1-alpine)
- Non-root users (appuser UID 1000, nginx)
- Dropped capabilities and no-new-privileges
- Resource limits (CPU/memory)
- Internal network isolation
- PyJWT for secure token handling (no ecdsa vulnerability)

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GLP_CLIENT_ID` | HPE GreenLake OAuth2 client ID |
| `GLP_CLIENT_SECRET` | HPE GreenLake OAuth2 client secret |
| `GLP_TOKEN_URL` | OAuth2 token endpoint |
| `API_KEY` | API key for dashboard authentication |
| `POSTGRES_PASSWORD` | PostgreSQL password |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GLP_BASE_URL` | `https://global.api.greenlake.hpe.com` | GreenLake API base URL |
| `DATABASE_URL` | Auto-generated | PostgreSQL connection string |
| `SYNC_INTERVAL_MINUTES` | `60` | Minutes between syncs |
| `SYNC_DEVICES` | `true` | Enable device sync |
| `SYNC_SUBSCRIPTIONS` | `true` | Enable subscription sync |
| `JWT_SECRET` | - | Secret for agent API JWT tokens |
| `ANTHROPIC_API_KEY` | - | Anthropic API key for Claude chatbot |
| `OPENAI_API_KEY` | - | OpenAI API key for GPT chatbot |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |

### Aruba Central (Optional)

| Variable | Description |
|----------|-------------|
| `ARUBA_CLIENT_ID` | Aruba Central OAuth2 client ID |
| `ARUBA_CLIENT_SECRET` | Aruba Central OAuth2 client secret |
| `ARUBA_TOKEN_URL` | Aruba Central token endpoint |
| `ARUBA_BASE_URL` | Aruba Central API base URL |

## CLI Usage

```bash
# Sync both devices and subscriptions
python main.py

# Sync specific resources
python main.py --devices              # Devices only
python main.py --subscriptions        # Subscriptions only

# Export to JSON (no database required)
python main.py --json-only

# Show expiring subscriptions
python main.py --expiring-days 90

# Backup data
python main.py --backup devices.json --subscription-backup subs.json
```

## API Endpoints

### Dashboard API (`/api`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/dashboard/stats` | GET | Dashboard statistics |
| `/api/devices` | GET | List devices with filters |
| `/api/subscriptions` | GET | List subscriptions |
| `/api/assignment/upload` | POST | Upload Excel for assignment |
| `/api/assignment/apply` | POST | Apply device assignments |
| `/api/assignment/apply-stream` | POST | Apply with SSE progress |

### Agent API (`/api/agent`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/ws-ticket` | POST | Get WebSocket auth ticket |
| `/api/agent/chat` | WebSocket | Real-time chat with AI |
| `/api/agent/conversations` | GET | List conversations |

### MCP Server (Port 8010)

| Tool | Description |
|------|-------------|
| `search_devices` | Full-text search across devices |
| `get_device_by_serial` | Get device by serial number |
| `list_devices` | List devices with filters |
| `get_device_subscriptions` | Get subscriptions linked to device |
| `search_subscriptions` | Full-text search subscriptions |
| `list_expiring_subscriptions` | Subscriptions expiring within N days |
| `get_device_summary` | Device counts by type/region |
| `get_subscription_summary` | Subscription counts by status |
| `run_query` | Execute read-only SQL queries |
| `ask_database` | Natural language database queries |

## Project Structure

```
├── main.py                      # CLI entry point
├── scheduler.py                 # Automated sync scheduler
├── server.py                    # FastMCP server with REST API bridge
├── Dockerfile                   # Backend container (Python 3.12-alpine)
├── docker-compose.yml           # Full stack with security features
├── nginx.conf                   # Reverse proxy config
├── setup.sh                     # Interactive setup wizard
│
├── frontend/
│   ├── Dockerfile               # Frontend container
│   ├── nginx.conf               # Frontend nginx config
│   └── src/
│       ├── pages/               # Dashboard, Devices, Subscriptions
│       ├── components/          # UI components, chat widget
│       └── hooks/               # React hooks
│
├── src/glp/
│   ├── api/                     # GreenLake & Aruba API clients
│   │   ├── auth.py              # OAuth2 token management
│   │   ├── client.py            # HTTP client with resilience
│   │   ├── devices.py           # Device sync
│   │   ├── subscriptions.py     # Subscription sync
│   │   ├── resilience.py        # Circuit breaker
│   │   └── aruba_*.py           # Aruba Central integration
│   │
│   ├── agent/                   # AI chatbot
│   │   ├── api/                 # WebSocket & REST endpoints
│   │   ├── orchestrator/        # Agent logic
│   │   ├── providers/           # Anthropic, OpenAI
│   │   ├── memory/              # Conversation & semantic memory
│   │   ├── tools/               # MCP tool registry
│   │   └── security/            # Ticket auth, CoT redaction
│   │
│   ├── assignment/              # Device assignment module
│   │   ├── domain/              # Entities and ports
│   │   ├── use_cases/           # Business logic
│   │   ├── adapters/            # PostgreSQL, Excel
│   │   └── api/                 # FastAPI routers
│   │
│   └── sync/                    # Clean architecture sync
│       ├── domain/              # Entities and ports
│       ├── use_cases/           # Sync orchestration
│       └── adapters/            # API and DB adapters
│
├── db/
│   ├── schema.sql               # Device tables
│   ├── subscriptions_schema.sql # Subscription tables
│   └── migrations/              # Schema migrations
│
├── tests/                       # Test suites
│   ├── test_*.py                # Unit tests
│   ├── assignment/              # Assignment tests
│   ├── agent/                   # Agent tests
│   └── sync/                    # Sync tests
│
└── .github/workflows/
    ├── ci.yml                   # Tests and linting
    └── publish.yml              # Docker Hub publishing
```

## Database Schema

### Tables

| Table | Description |
|-------|-------------|
| `devices` | Device inventory (28 columns) |
| `subscriptions` | Subscription inventory (20 columns) |
| `device_subscriptions` | Device-subscription relationships |
| `device_tags` | Device tags (key-value) |
| `subscription_tags` | Subscription tags (key-value) |
| `sync_history` | Sync audit log |
| `agent_conversations` | Chat conversations |
| `agent_messages` | Chat messages with embeddings |

### Views

| View | Description |
|------|-------------|
| `active_devices` | Devices with active subscriptions |
| `active_subscriptions` | STARTED subscriptions only |
| `devices_expiring_soon` | Devices expiring in 90 days |
| `subscriptions_expiring_soon` | Subscriptions expiring in 90 days |
| `device_summary` | Counts by type and region |
| `subscription_summary` | Counts by type and status |

## Development

### Local Setup

```bash
# Install dependencies
uv sync

# Start PostgreSQL and Redis
docker compose up -d postgres redis

# Run API server
uv run uvicorn src.glp.assignment.app:app --reload --port 8000

# Run frontend
cd frontend && npm install && npm run dev
```

### Testing

```bash
# All tests
uv run pytest tests/ -v

# Unit tests only (no database)
uv run pytest tests/test_auth.py tests/test_devices.py -v

# Database tests
uv run pytest tests/test_database.py -v

# Assignment tests
uv run pytest tests/assignment/ -v

# Agent tests
uv run pytest tests/agent/ -v
```

### Linting

```bash
uv run ruff check .
```

## CI/CD

### GitHub Actions

Push to `main` or create a tag to trigger:

1. **CI** - Run tests and linting
2. **Publish** - Build and push Docker images to Docker Hub

### Required Secrets

| Name | Description |
|------|-------------|
| `DOCKERHUB_TOKEN` | Docker Hub access token |

### Required Variables

| Name | Description |
|------|-------------|
| `DOCKERHUB_USERNAME` | Docker Hub username/org |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│                    nginx:8080 → Host:80                          │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Server (FastAPI)                        │
│                         Port 8000                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Dashboard  │  │  Assignment │  │     Agent Chatbot       │  │
│  │     API     │  │     API     │  │  (Anthropic/OpenAI)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────┐    ┌─────────────┐       ┌─────────────┐
│  PostgreSQL │    │   Redis     │       │ MCP Server  │
│    (5432)   │    │   (6379)    │       │   (8010)    │
└─────────────┘    └─────────────┘       └─────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Scheduler Service                           │
│                         Port 8080                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ GreenLake   │  │   Aruba     │  │     Circuit Breaker     │  │
│  │    Sync     │  │   Central   │  │      Resilience         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Docker Container Issues

#### Containers Won't Start

**Problem:** Services fail to start or crash immediately.

```bash
# Check container status
docker compose ps

# View logs for specific service
docker compose logs api-server
docker compose logs scheduler
docker compose logs frontend
```

**Solutions:**

1. **Port conflicts** - Check if ports are already in use:
   ```bash
   # macOS/Linux
   lsof -i :80    # Frontend
   lsof -i :8000  # API server
   lsof -i :5432  # PostgreSQL

   # Stop conflicting services or change ports in docker-compose.yml
   ```

2. **Missing environment variables** - Verify `.env` file exists and contains required values:
   ```bash
   # Check for missing variables
   grep -E "^(GLP_CLIENT_ID|GLP_CLIENT_SECRET|API_KEY|POSTGRES_PASSWORD)=" .env

   # If missing, copy from template
   cp .env.example .env
   nano .env
   ```

3. **Insufficient resources** - Docker needs adequate memory/CPU:
   ```bash
   # Check Docker resource allocation (Docker Desktop)
   # Settings → Resources → Increase Memory to 4GB+
   ```

#### Image Build Failures

**Problem:** `docker compose build` fails with errors.

**Solutions:**

1. **Network issues during build:**
   ```bash
   # Retry with no cache
   docker compose build --no-cache

   # Or pull pre-built images instead
   docker pull jgiet001/glp-sync:latest
   docker pull jgiet001/glp-frontend:latest
   docker compose up -d
   ```

2. **Disk space issues:**
   ```bash
   # Check disk space
   df -h

   # Clean up Docker resources
   docker system prune -a --volumes
   ```

### Database Connection Problems

#### "relation does not exist" Error

**Problem:** API or scheduler fails with `relation "devices" does not exist`.

**Solutions:**

1. **Schema not initialized** - Reset database and apply schema:
   ```bash
   # Stop services
   docker compose down

   # Remove database volume (⚠️ DATA LOSS)
   docker volume rm glp-sync-2_postgres_data

   # Restart - schema will auto-apply
   docker compose up -d

   # Verify schema
   docker compose exec postgres psql -U glp -d greenlake -c "\dt"
   ```

2. **Migration needed** - Apply pending migrations:
   ```bash
   # Check migration status
   docker compose exec postgres psql -U glp -d greenlake \
     -c "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1;"

   # Apply migrations manually
   docker compose exec postgres psql -U glp -d greenlake -f /docker-entrypoint-initdb.d/schema.sql
   ```

#### Connection Refused

**Problem:** `FATAL: password authentication failed for user "glp"`.

**Solutions:**

1. **Password mismatch** - Ensure `.env` matches database password:
   ```bash
   # Check current password in .env
   grep POSTGRES_PASSWORD .env

   # If changed, must recreate database volume
   docker compose down -v
   docker compose up -d
   ```

2. **Database not ready** - Wait for PostgreSQL to initialize:
   ```bash
   # Check database logs
   docker compose logs postgres | tail -20

   # Wait for "database system is ready to accept connections"
   # Then restart dependent services
   docker compose restart api-server scheduler
   ```

### GreenLake API Authentication Failures

#### Invalid Client Credentials

**Problem:** `401 Unauthorized` or `invalid_client` error in scheduler logs.

**Solutions:**

1. **Verify credentials** - Check GreenLake API credentials:
   ```bash
   # Test credentials manually
   curl -X POST https://sso.common.cloud.hpe.com/as/token.oauth2 \
     -d "grant_type=client_credentials" \
     -d "client_id=$GLP_CLIENT_ID" \
     -d "client_secret=$GLP_CLIENT_SECRET"

   # Should return access_token
   ```

2. **Update credentials in .env:**
   ```bash
   nano .env
   # Update GLP_CLIENT_ID and GLP_CLIENT_SECRET

   # Restart scheduler to pick up changes
   docker compose restart scheduler
   ```

3. **Check token URL** - Ensure `GLP_TOKEN_URL` is correct:
   ```bash
   # Should be (default):
   GLP_TOKEN_URL=https://sso.common.cloud.hpe.com/as/token.oauth2
   ```

#### Token Refresh Failures

**Problem:** `Token refresh failed` in logs after initial success.

**Solutions:**

1. **Network connectivity** - Check scheduler can reach HPE endpoints:
   ```bash
   # Test from within scheduler container
   docker compose exec scheduler curl -I https://sso.common.cloud.hpe.com
   docker compose exec scheduler curl -I https://global.api.greenlake.hpe.com
   ```

2. **Circuit breaker open** - Wait for automatic recovery (30-60 seconds):
   ```bash
   # Monitor logs for recovery
   docker compose logs -f scheduler | grep -i "circuit"
   ```

### Frontend Connection Issues

#### Dashboard Shows "Failed to Load Data"

**Problem:** Frontend displays error messages or empty data.

**Solutions:**

1. **API server unreachable** - Verify backend is running:
   ```bash
   # Check API health endpoint
   curl http://localhost:8000/api/health

   # Should return: {"status": "healthy"}

   # If not running, check logs
   docker compose logs api-server
   ```

2. **CORS errors in browser console** - Update allowed origins:
   ```bash
   # Edit .env
   nano .env

   # Add your frontend URL
   CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost

   # Restart API server
   docker compose restart api-server
   ```

3. **Authentication failures** - Check API key configuration:
   ```bash
   # For development, disable auth temporarily
   nano .env
   # Set: DISABLE_AUTH=true

   # For production, ensure API_KEY is set in both .env and frontend config
   ```

#### WebSocket Chat Not Connecting

**Problem:** AI chatbot shows "Connection failed" or "Ticket invalid".

**Solutions:**

1. **Redis not running** - Verify Redis is healthy:
   ```bash
   # Check Redis connection
   docker compose exec redis redis-cli ping
   # Should return: PONG

   # If not running
   docker compose up -d redis
   ```

2. **JWT authentication issues** - Verify JWT secret is configured:
   ```bash
   # Check .env
   grep JWT_SECRET .env

   # If missing, generate and add
   python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))" >> .env

   # Restart API server
   docker compose restart api-server
   ```

3. **WebSocket ticket expired** - Tickets are valid for 60 seconds:
   ```bash
   # Check ticket generation in browser network tab
   # POST /api/agent/ws-ticket should return fresh ticket

   # Ensure system clocks are synchronized (if using distributed setup)
   ```

### AI Chatbot Problems

#### "No LLM Provider Available"

**Problem:** Chatbot returns error: "No LLM provider available".

**Solutions:**

1. **Add API keys** - Configure at least one LLM provider:
   ```bash
   nano .env

   # Option 1: Anthropic Claude (recommended)
   ANTHROPIC_API_KEY=sk-ant-...

   # Option 2: OpenAI GPT
   OPENAI_API_KEY=sk-...

   # Restart API server
   docker compose restart api-server
   ```

2. **Verify provider initialization** - Check API server logs:
   ```bash
   docker compose logs api-server | grep -i "provider"
   # Should see: "Initialized provider: anthropic" or "openai"
   ```

#### MCP Tools Not Working

**Problem:** Chatbot can't access database tools.

**Solutions:**

1. **MCP server not running** - Start MCP server:
   ```bash
   # Check MCP server status
   docker compose ps mcp-server

   # If not running
   docker compose up -d mcp-server

   # Verify health
   curl http://localhost:8010/health
   ```

2. **Database connection from MCP** - Check MCP server logs:
   ```bash
   docker compose logs mcp-server

   # If connection errors, verify DATABASE_URL
   docker compose exec mcp-server env | grep DATABASE_URL
   ```

### Performance and Sync Issues

#### Sync Taking Too Long

**Problem:** Device/subscription sync times out or takes hours.

**Solutions:**

1. **Reduce page size** - Adjust pagination limits:
   ```python
   # In scheduler container, modify:
   # src/glp/api/devices.py (line ~45)
   # Change: per_page=2000 → per_page=500
   ```

2. **Increase timeout** - For large inventories:
   ```bash
   # Edit docker-compose.yml
   # Add to scheduler environment:
   environment:
     - SYNC_TIMEOUT_MINUTES=30

   # Restart
   docker compose up -d scheduler
   ```

3. **Check circuit breaker** - Too many failures slow retries:
   ```bash
   # Monitor scheduler logs
   docker compose logs -f scheduler | grep -E "(circuit|retry|failed)"
   ```

#### Database Growing Too Large

**Problem:** PostgreSQL volume using excessive disk space.

**Solutions:**

1. **Vacuum old data** - Clean up deleted rows:
   ```bash
   docker compose exec postgres psql -U glp -d greenlake -c "VACUUM FULL ANALYZE;"
   ```

2. **Archive old sync history** - Retain recent only:
   ```bash
   # Keep last 90 days
   docker compose exec postgres psql -U glp -d greenlake -c \
     "DELETE FROM sync_history WHERE created_at < NOW() - INTERVAL '90 days';"
   ```

### Setup Wizard Issues

#### Wizard Fails to Create .env

**Problem:** `./setup.sh` exits with error or creates incomplete `.env`.

**Solutions:**

1. **Permission issues** - Ensure script is executable:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

2. **Manual .env creation** - Skip wizard and create manually:
   ```bash
   cp .env.example .env
   nano .env
   # Fill in required variables (see Environment Variables section)

   docker compose up -d
   ```

3. **Shell compatibility** - Run with bash explicitly:
   ```bash
   bash setup.sh
   ```

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `bind: address already in use` | Port conflict | Change port in `docker-compose.yml` or stop conflicting service |
| `no such table: devices` | Schema not applied | Reset database: `docker compose down -v && docker compose up -d` |
| `Invalid token` | API key mismatch | Verify `API_KEY` in `.env` matches frontend config |
| `Connection refused` | Service not ready | Wait 30s for startup, check `docker compose logs <service>` |
| `Rate limit exceeded` | Too many API calls | Enable circuit breaker retry delay (default: 5 minutes) |
| `Out of memory` | Docker resource limit | Increase Docker Desktop memory to 4GB+ |

### Getting Help

If issues persist after troubleshooting:

1. **Check logs** - Gather logs for debugging:
   ```bash
   docker compose logs > debug-logs.txt
   ```

2. **Verify environment** - Share configuration (redact secrets):
   ```bash
   docker compose config > docker-config.txt
   cat .env | grep -v "SECRET\|PASSWORD\|KEY" > env-sanitized.txt
   ```

3. **GitHub Issues** - Open an issue with:
   - Description of the problem
   - Steps to reproduce
   - Relevant log excerpts
   - Environment details (OS, Docker version)

4. **Community Support** - Check existing issues:
   - [GitHub Issues](https://github.com/Jgiet001-AI/GLP-Sync-2/issues)
   - Search for similar problems and solutions

## Contributing

We welcome contributions from the community! Whether you're fixing bugs, adding features, improving documentation, or reporting issues, your help makes this project better.

### Ways to Contribute

- **Code Contributions** - Bug fixes, new features, performance improvements
- **Documentation** - Improve guides, add examples, fix typos
- **Bug Reports** - Detailed issue reports with reproduction steps
- **Feature Requests** - Suggest new capabilities or enhancements
- **Testing** - Write tests, improve test coverage
- **Code Reviews** - Review pull requests and provide feedback

### Getting Started

#### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/GLP-Sync-2.git
cd GLP-Sync-2

# Add upstream remote
git remote add upstream https://github.com/Jgiet001-AI/GLP-Sync-2.git
```

#### 2. Development Setup

We use [uv](https://docs.astral.sh/uv/) for fast, reliable dependency management:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (including dev dependencies)
uv sync --dev

# Verify installation
uv run python --version  # Should be 3.11+
uv run pytest --version
```

#### 3. Create a Branch

```bash
# Create a descriptive branch name
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

### Development Workflow

#### Running Tests

We use `pytest` with separate test suites:

```bash
# Unit tests (no external dependencies)
uv run pytest tests/test_auth.py tests/test_devices.py -v

# Integration tests (requires PostgreSQL)
docker compose up -d postgres
uv run pytest tests/test_database.py -v

# All tests
uv run pytest tests/ -v

# With coverage
uv run pytest --cov=src tests/
```

**Important:** All pull requests must pass CI tests before merging.

#### Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check for linting issues
uv run ruff check .

# Auto-fix issues where possible
uv run ruff check . --fix

# Format code
uv run ruff format .
```

**Code Standards:**
- Python 3.11+ syntax and features
- Line length: 100 characters max
- Type hints encouraged for public APIs
- Async/await for all I/O operations
- Follow existing code patterns and architecture

#### Running Locally

```bash
# Start database
docker compose up -d postgres

# Run API server
uv run uvicorn src.glp.assignment.app:app --reload --port 8000

# Run scheduler (in another terminal)
uv run python scheduler.py

# Run frontend (in another terminal)
cd frontend
npm install
npm run dev
```

### Pull Request Process

1. **Update your branch** with the latest upstream changes:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Write clear commit messages**:
   ```bash
   # Good examples:
   git commit -m "fix: resolve token refresh race condition"
   git commit -m "feat: add Aruba Central device sync"
   git commit -m "docs: update deployment guide with security hardening"

   # Follow conventional commits format:
   # <type>: <description>
   # Types: feat, fix, docs, test, refactor, perf, chore
   ```

3. **Push your changes**:
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Open a Pull Request**:
   - Use a descriptive title
   - Reference related issues (e.g., "Fixes #123")
   - Describe what changed and why
   - Include testing steps if applicable
   - Add screenshots for UI changes

5. **Code Review**:
   - Address reviewer feedback promptly
   - Keep discussions focused and constructive
   - Update your PR based on comments
   - Request re-review when ready

### Code Review Guidelines

**For Authors:**
- Keep PRs focused and reasonably sized (<500 lines when possible)
- Write clear descriptions and testing steps
- Respond to feedback within 48 hours
- Don't take criticism personally—we're all learning!

**For Reviewers:**
- Be respectful and constructive
- Focus on code quality, not personal preferences
- Suggest alternatives when requesting changes
- Approve when requirements are met (CI passes, code quality good)

### Testing Requirements

All contributions should include appropriate tests:

- **Unit Tests** - For business logic, utilities, and pure functions
- **Integration Tests** - For database operations and API interactions
- **Documentation** - For public APIs and complex logic

**Example test structure:**
```python
import pytest
from src.glp.api.auth import TokenManager

@pytest.mark.asyncio
async def test_token_refresh():
    """Test that token manager refreshes expired tokens."""
    manager = TokenManager(client_id="test", client_secret="test")
    # ... test implementation
```

### Documentation

When adding features or making changes:

1. **Update README.md** - Add new sections for significant features
2. **Code Comments** - Explain complex logic or design decisions
3. **Docstrings** - Use clear docstrings for public functions
4. **CLAUDE.md** - Update project guidance for AI assistants

### Reporting Bugs

**Before reporting:**
- Search existing issues to avoid duplicates
- Verify the bug exists on the latest version

**When reporting, include:**
- Clear, descriptive title
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Docker version, Python version)
- Relevant log output (redact secrets!)
- Screenshots if applicable

**Example:**
```markdown
**Bug:** Frontend fails to connect to API server

**Environment:**
- OS: macOS 14.2
- Docker: 24.0.6
- Browser: Chrome 120

**Steps to Reproduce:**
1. Start services with `docker compose up -d`
2. Navigate to http://localhost
3. Open browser console

**Expected:** Dashboard loads successfully
**Actual:** Error: "Failed to fetch /api/devices"

**Logs:**
```
api-server | ERROR: Database connection failed
```
```

### Feature Requests

We love hearing your ideas! When suggesting features:

1. **Check existing issues** - Your idea might already be planned
2. **Describe the use case** - Why is this feature needed?
3. **Propose a solution** - What would the implementation look like?
4. **Consider alternatives** - Are there other approaches?

### Community Guidelines

- **Be respectful** - Treat others with kindness and professionalism
- **Be patient** - Maintainers are volunteers with limited time
- **Be collaborative** - We're building this together
- **Be open** - Accept feedback and different perspectives

### Questions?

- **GitHub Discussions** - For general questions and ideas
- **GitHub Issues** - For bug reports and feature requests
- **Code Questions** - Comment on specific files or PRs

Thank you for contributing to HPE GreenLake Device & Subscription Sync! 🎉

## Security

Security is a top priority for this project. This section outlines best practices, security features, and how to report vulnerabilities.

### Environment Variables and Secrets

**Critical: Never commit `.env` files to version control!**

```bash
# ✅ GOOD - Use .env.example as a template
cp .env.example .env
nano .env  # Add your actual secrets

# ❌ BAD - Never commit .env
git add .env  # DON'T DO THIS!
```

**Generate Secure Secrets:**

```bash
# API Key (32+ characters recommended)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# JWT Secret (64+ characters REQUIRED)
python -c "import secrets; print(secrets.token_urlsafe(48))"

# PostgreSQL Password (32+ characters recommended)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Redis Password (32+ characters recommended)
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Authentication and Authorization

#### Development Mode (Bypass Auth)

For local development and testing:

```bash
# .env configuration
DISABLE_AUTH=true      # Bypass API key authentication
REQUIRE_AUTH=false     # Bypass JWT authentication
```

⚠️ **Warning:** Only use these settings in development environments. Never deploy to production with authentication disabled.

#### Production Mode (Secure Auth)

For production deployments:

```bash
# .env configuration
DISABLE_AUTH=false
REQUIRE_AUTH=true

# Required secure values
API_KEY=<your-secure-api-key-32-chars-minimum>
JWT_SECRET=<your-jwt-secret-64-chars-minimum>
JWT_ALGORITHM=HS256
JWT_CLOCK_SKEW_SECONDS=30

# Optional: Additional JWT validation
JWT_ISSUER=https://your-idp.com
JWT_AUDIENCE=glp-api
```

**JWT Requirements:**
- **Minimum length:** 64 characters (use the generator above)
- **Algorithm:** HS256 (HMAC with SHA-256)
- **Token validation:** Includes signature verification, expiration check, and clock skew tolerance
- **Custom claims:** Configure `JWT_TENANT_ID_CLAIM`, `JWT_USER_ID_CLAIM`, `JWT_SESSION_ID_CLAIM` if your IdP uses different claim names

### Database Security

#### PostgreSQL Configuration

```bash
# .env configuration
POSTGRES_USER=glp
POSTGRES_PASSWORD=<your-secure-password>  # 32+ chars recommended
POSTGRES_DB=greenlake

# Authentication method
POSTGRES_HOST_AUTH_METHOD=scram-sha-256
POSTGRES_INITDB_ARGS="--auth-host=scram-sha-256"
```

**Security Features:**
- **SCRAM-SHA-256** - Strong password-based authentication (replaces legacy MD5)
- **Row-Level Security (RLS)** - Multi-tenant data isolation on `agent_messages` table
- **Connection limits** - Docker Compose restricts PostgreSQL to `127.0.0.1:5432` (localhost only)
- **Prepared statements** - All queries use parameterized SQL to prevent injection attacks

#### Redis Security

```bash
# .env configuration
REDIS_PASSWORD=<your-redis-password>  # 32+ chars recommended
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
```

**Security Features:**
- **Password-protected** - `requirepass` enabled by default
- **Persistence** - AOF (Append-Only File) mode for ticket durability
- **Network isolation** - Not exposed to host (internal Docker network only)

### Docker Security Hardening

This project follows Docker security best practices:

#### Non-Root Users

All containers run as non-root users:

```yaml
# Example from docker-compose.yml
api-server:
  user: "1000:1000"  # Non-root UID/GID
```

**User Mapping:**
- **Backend services** (api-server, scheduler, mcp-server): `appuser` (UID 1000)
- **Frontend** (nginx): `nginx` user
- **PostgreSQL**: Internal `postgres` user
- **Redis**: UID 999

#### Capability Dropping

Containers drop all Linux capabilities and only add back what's required:

```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
cap_add:
  - CHOWN        # PostgreSQL only
  - SETGID       # PostgreSQL only
  - SETUID       # PostgreSQL only
  - DAC_OVERRIDE # PostgreSQL only
  - FOWNER       # PostgreSQL only
```

**Most containers run with ZERO capabilities** (api-server, scheduler, mcp-server, redis, frontend).

#### Read-Only Filesystems

Where possible, containers use read-only root filesystems:

```yaml
api-server:
  read_only: true
  tmpfs:
    - /tmp:mode=1777,size=100M  # Temporary files in memory
```

**Services with read-only FS:**
- `api-server`
- `scheduler`
- `mcp-server`
- `redis`
- `frontend`

#### Resource Limits

All containers have CPU and memory limits to prevent resource exhaustion:

```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 1G
    reservations:
      cpus: '0.25'
      memory: 256M
```

#### Base Image Pinning

All Docker images are pinned by **SHA256 digest** to ensure reproducible builds and prevent supply chain attacks:

```dockerfile
# Pinned by digest (SHA256)
FROM python:3.12-alpine@sha256:<digest>
FROM node:22-alpine@sha256:<digest>
FROM nginx:1-alpine@sha256:<digest>
```

### Network Security

#### Port Exposure

**Default configuration (development):**
- **Frontend:** `80` (HTTP only - use reverse proxy with TLS in production)
- **PostgreSQL:** `127.0.0.1:5432` (localhost only - not exposed externally)
- **Scheduler:** `127.0.0.1:8080` (localhost only - health check endpoint)
- **Redis:** Not exposed (internal network only)
- **MCP Server:** Not exposed by default (optional: `8010`)

**Production recommendations:**
1. **Use a reverse proxy** (nginx, Traefik, Caddy) with TLS termination
2. **Firewall rules** - Restrict ingress to frontend port only
3. **Internal network** - Keep PostgreSQL, Redis, and backend services on private network
4. **VPN/VPC** - Deploy in private cloud network with VPN access for administration

#### CORS Configuration

Configure allowed origins for frontend access:

```bash
# .env configuration
# Development
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Production
CORS_ORIGINS=https://your-domain.com,https://app.your-domain.com
```

### WebSocket Security

The AI chatbot uses a **ticket-based authentication system** for WebSocket connections:

**How it works:**
1. Client authenticates via `/api/agent/ticket` endpoint (JWT required)
2. Server generates a single-use ticket (stored in Redis with 60s TTL)
3. Client uses ticket in WebSocket connection URL
4. Server validates and consumes ticket (one-time use)
5. WebSocket connection established with session context

**Security properties:**
- **Short-lived** - Tickets expire after 60 seconds
- **Single-use** - Ticket is deleted after first use
- **JWT-protected** - Ticket generation requires valid JWT
- **Session-bound** - Ticket encodes tenant, user, and session IDs

### Production Deployment Checklist

Before deploying to production, ensure:

- [ ] **Authentication enabled** - `DISABLE_AUTH=false`, `REQUIRE_AUTH=true`
- [ ] **Secrets rotated** - Use the generators above to create strong secrets
- [ ] **Environment variables secure** - `.env` file has `600` permissions (`chmod 600 .env`)
- [ ] **TLS/HTTPS configured** - Use reverse proxy (nginx, Traefik, Caddy) for TLS termination
- [ ] **Firewall rules** - Restrict ingress to HTTPS (443) and SSH (22) only
- [ ] **Database backups** - Configure automated PostgreSQL backups
- [ ] **Log aggregation** - Send logs to centralized logging (ELK, Splunk, Datadog)
- [ ] **Monitoring** - Set up health check alerts (Prometheus, UptimeRobot)
- [ ] **Update Docker images** - Pull latest security patches regularly
- [ ] **Review CORS origins** - Ensure `CORS_ORIGINS` only includes trusted domains
- [ ] **Vulnerability scanning** - Run `docker scan` or Trivy on images before deployment

### CI/CD Security

#### Automated Vulnerability Scanning

GitHub Actions CI pipeline includes:

```yaml
# .github/workflows/publish.yml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    scan-type: 'image'
    severity: 'CRITICAL,HIGH'
    exit-code: '1'  # Fail build if vulnerabilities found
```

**Scanned on every build:**
- `jgiet001/glp-sync`
- `jgiet001/glp-frontend`
- `jgiet001/glp-mcp-server`
- `jgiet001/glp-scheduler`

#### Dependency Updates

- **Python dependencies** - Managed with `uv` (locked in `uv.lock`)
- **Node dependencies** - Managed with `npm` (locked in `package-lock.json`)
- **Base images** - Pinned by SHA256, updated manually after security review

**Recommendations:**
- Monitor [GitHub Security Advisories](https://github.com/advisories)
- Run `uv sync --upgrade` and `npm audit` regularly
- Subscribe to Docker Hub security notifications

### Security Disclosure Policy

**If you discover a security vulnerability, please DO NOT open a public issue.**

Instead, please report it privately using one of these methods:

#### GitHub Security Advisories (Preferred)

1. Go to [Security Advisories](https://github.com/Jgiet001-AI/GLP-Sync-2/security/advisories)
2. Click "Report a vulnerability"
3. Provide details about the vulnerability
4. We will respond within 48 hours

#### Email (Alternative)

Send details to: **[maintainer email - replace with actual email]**

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if known)

**What to expect:**
- **Acknowledgment** within 48 hours
- **Initial assessment** within 1 week
- **Fix timeline** provided based on severity
- **Public disclosure** coordinated after fix is released
- **Credit** in release notes (if desired)

### Security Best Practices Summary

| Component | Best Practice | Configuration |
|-----------|---------------|---------------|
| **API Key** | 32+ chars, cryptographically random | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| **JWT Secret** | 64+ chars, cryptographically random | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| **PostgreSQL** | SCRAM-SHA-256, localhost only | `POSTGRES_HOST_AUTH_METHOD=scram-sha-256` |
| **Redis** | Password-protected, internal network | `requirepass` enabled, no host port |
| **Docker** | Non-root users, dropped capabilities | `user: "1000:1000"`, `cap_drop: ALL` |
| **Network** | TLS/HTTPS, firewall rules | Reverse proxy with Let's Encrypt |
| **CORS** | Whitelist trusted origins only | `CORS_ORIGINS=https://your-domain.com` |
| **Secrets** | Never commit to Git | `.env` in `.gitignore` |
| **Updates** | Regular dependency updates | `uv sync --upgrade`, `npm audit` |
| **Scanning** | CI/CD vulnerability scanning | Trivy on every build |

### Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/auth-methods.html)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [Python Security Guide](https://python.readthedocs.io/en/latest/library/security_warnings.html)

## License

MIT
