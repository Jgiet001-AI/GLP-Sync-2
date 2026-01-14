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
- [FAQ](#faq)
- [Roadmap](#roadmap)
  - [Near Term](#-near-term-q1-q2-2026)
  - [Mid Term](#-mid-term-q3-q4-2026)
  - [Long Term](#-long-term-2027)
  - [Performance & Scalability](#-performance--scalability)
  - [Developer Experience](#-developer-experience)
  - [Community Requests](#-community-requests)
  - [Contributing to the Roadmap](#-contributing-to-the-roadmap)
  - [Release Schedule](#-release-schedule)
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

## FAQ

### What is HPE GreenLake Platform?

[HPE GreenLake Platform](https://www.hpe.com/us/en/greenlake.html) is HPE's as-a-service cloud platform that provides IT infrastructure and services with a pay-per-use consumption model. It offers unified management, monitoring, and provisioning of compute, storage, and networking resources across on-premises, edge, and cloud environments.

This project syncs device inventory, subscription data, and service entitlements from GreenLake's REST API to a local PostgreSQL database for analysis, reporting, and integration with other systems.

### Do I need GreenLake credentials to use this?

**Yes, you need valid GreenLake API credentials** to sync data from the platform:
- **`GLP_CLIENT_ID`** - OAuth2 client ID
- **`GLP_CLIENT_SECRET`** - OAuth2 client secret
- **`GLP_TOKEN_URL`** - OAuth2 token endpoint (usually `https://sso.common.cloud.hpe.com/as/token.oauth2`)

These credentials must be obtained from your GreenLake administrator or through the [HPE GreenLake Developer Portal](https://developer.greenlake.hpe.com/).

**Without credentials:**
- You can still run the dashboard and database components
- The sync services will fail authentication
- Use the `--json-only` CLI mode to test with sample data

**Development mode:** The interactive setup wizard (`./setup.sh`) offers a "demo mode" option that uses mock data for testing the UI without real credentials.

### Can I use this without Docker?

**Yes, but Docker is strongly recommended** for ease of deployment and dependency management.

#### Without Docker (Manual Setup)

**Requirements:**
- Python 3.11+ with `uv` package manager
- PostgreSQL 16+ with `pgvector` extension
- Node.js 22+ with npm
- Redis 7+ (optional, required for AI chatbot)

**Backend setup:**
```bash
# Install Python dependencies
uv sync

# Set up database
psql -U postgres -f db/schema.sql
psql -U postgres -f db/subscriptions_schema.sql
psql -U postgres -f db/migrations/*.sql

# Configure environment
cp .env.example .env
nano .env  # Edit with your credentials

# Run API server
uv run uvicorn src.glp.assignment.app:app --reload --port 8000

# Run scheduler (separate terminal)
python scheduler.py
```

**Frontend setup:**
```bash
cd frontend
npm install
npm run dev  # Development server on port 5173
npm run build  # Production build
```

**Why Docker is recommended:**
- Pre-configured services with correct versions
- Automatic database initialization with migrations
- Network isolation and security hardening
- One-command deployment with `docker compose up`
- Production-ready with security best practices

### Which AI provider should I choose (Claude vs GPT)?

The AI chatbot supports both Anthropic Claude (primary) and OpenAI GPT (fallback). **Choose based on your priorities:**

#### Anthropic Claude (Recommended)

**Best for:**
- Longer context windows (200k tokens)
- Better reasoning and instruction following
- Superior code understanding
- More detailed technical explanations

**Configuration:**
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

**Pricing:** ~$0.015/1k tokens (Claude 3.5 Sonnet)

#### OpenAI GPT

**Best for:**
- Lower cost for simple queries
- Faster response times
- Existing OpenAI infrastructure

**Configuration:**
```bash
OPENAI_API_KEY=sk-...
```

**Pricing:** ~$0.002/1k tokens (GPT-4o mini)

#### Using Both

The chatbot will automatically fall back to OpenAI if Anthropic fails:
```bash
ANTHROPIC_API_KEY=sk-ant-...  # Primary
OPENAI_API_KEY=sk-...          # Fallback
```

**Embeddings:** Regardless of chat provider, semantic memory uses OpenAI's `text-embedding-3-large` model for best accuracy.

**Free tier:** Both providers offer free trial credits for testing.

### How much does it cost to run?

Costs depend on infrastructure choice and usage patterns:

#### Cloud Hosting (AWS/Azure/GCP)

**Minimal deployment (t3.medium equivalent):**
- **Compute:** $30-50/month (2 vCPU, 4GB RAM)
- **Database:** $20-30/month (managed PostgreSQL)
- **Storage:** $5-10/month (50GB SSD)
- **Total:** ~$55-90/month

**Production deployment (t3.large equivalent):**
- **Compute:** $60-100/month (2 vCPU, 8GB RAM)
- **Database:** $40-80/month (managed PostgreSQL with backups)
- **Storage:** $10-20/month (100GB SSD)
- **Load balancer:** $15-20/month
- **Total:** ~$125-220/month

#### Self-Hosted (On-Premises/Homelab)

**Hardware only:**
- **Server:** One-time cost (can use existing hardware)
- **Power:** $5-20/month (depending on usage)
- **Internet:** Included in existing connection
- **Total:** ~$5-20/month (operational costs only)

#### AI Chatbot Costs (Optional)

**Light usage (100k tokens/day):**
- **Claude:** ~$45/month
- **GPT-4o mini:** ~$6/month

**Heavy usage (1M tokens/day):**
- **Claude:** ~$450/month
- **GPT-4o mini:** ~$60/month

**Note:** The AI chatbot is completely optional. Core sync functionality has no per-request API costs.

#### Free Tier (Development)

**Local Docker deployment:**
- **Cost:** $0 (uses local resources)
- **Requirements:** Docker Desktop, 4GB RAM, 10GB disk

### Can I deploy this to production?

**Yes, this project is production-ready** with security hardening, health checks, and multi-arch Docker images.

#### Production Deployment Options

##### 1. Docker Compose (docker-compose.prod.yml)

Uses pre-built multi-arch images from Docker Hub:
```bash
docker compose -f docker-compose.prod.yml up -d
```

**Features:**
- Pre-built images (no local compilation)
- Security hardening enabled by default
- Health checks for all services
- Automatic restarts

##### 2. Kubernetes

Helm charts available in `k8s/` directory:
```bash
helm install glp-sync ./k8s/helm/glp-sync \
  --set env.GLP_CLIENT_ID=$GLP_CLIENT_ID \
  --set env.GLP_CLIENT_SECRET=$GLP_CLIENT_SECRET
```

##### 3. Cloud Platforms

- **AWS ECS/Fargate** - Use Docker images with task definitions
- **Azure Container Instances** - Deploy with ARM templates
- **Google Cloud Run** - Deploy with `gcloud run deploy`

#### Production Checklist

Before deploying to production, ensure:

- [ ] **Strong secrets generated** - Use the security section's generators
- [ ] **Authentication enabled** - `DISABLE_AUTH=false`, `REQUIRE_AUTH=true`
- [ ] **TLS/HTTPS configured** - Use reverse proxy (nginx, Traefik, Caddy)
- [ ] **Database backups** - Configure automated PostgreSQL backups
- [ ] **Environment variables secure** - Never commit `.env` to Git
- [ ] **Monitoring setup** - Health checks, log aggregation, alerts
- [ ] **Resource limits** - Set CPU/memory limits in docker-compose.yml
- [ ] **Firewall rules** - Restrict ingress to HTTPS (443) only
- [ ] **CORS configured** - Set `CORS_ORIGINS` to your frontend domain
- [ ] **Vulnerability scanning** - Run Trivy before deployment

See the [Security](#security) section for detailed best practices.

### How do I backup my data?

PostgreSQL database contains all synced device/subscription data. **Regular backups are critical for production deployments.**

#### Automated Backups (Recommended)

##### Using pg_dump (Logical Backup)

```bash
#!/bin/bash
# backup-db.sh - Run daily via cron

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/glp_sync_$TIMESTAMP.sql.gz"

# Backup database (compressed)
docker compose exec -T postgres pg_dump -U glpuser glp_sync | gzip > "$BACKUP_FILE"

# Keep only last 30 days
find "$BACKUP_DIR" -name "glp_sync_*.sql.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE"
```

**Add to crontab:**
```bash
0 2 * * * /path/to/backup-db.sh >> /var/log/glp-backup.log 2>&1
```

##### Using Docker Volume Snapshots

```bash
# Stop database (ensures consistency)
docker compose stop postgres

# Backup volume
docker run --rm \
  -v glp-sync-2_postgres-data:/source:ro \
  -v /backups:/backup \
  alpine tar czf /backup/postgres-data-$(date +%Y%m%d).tar.gz -C /source .

# Restart database
docker compose start postgres
```

#### Manual Backup (One-Time)

```bash
# Export entire database
docker compose exec postgres pg_dump -U glpuser glp_sync > glp_sync_backup.sql

# Export with data only (no schema)
docker compose exec postgres pg_dump -U glpuser --data-only glp_sync > data_only.sql

# Export compressed
docker compose exec postgres pg_dump -U glpuser glp_sync | gzip > glp_sync_backup.sql.gz
```

#### Restore from Backup

```bash
# Restore full database
docker compose exec -T postgres psql -U glpuser glp_sync < glp_sync_backup.sql

# Restore compressed backup
gunzip < glp_sync_backup.sql.gz | docker compose exec -T postgres psql -U glpuser glp_sync
```

#### Cloud Backup Solutions

- **AWS RDS** - Automated daily snapshots with 7-day retention
- **Azure Database for PostgreSQL** - Point-in-time restore up to 35 days
- **Google Cloud SQL** - Automated backups with configurable retention
- **Managed PostgreSQL** (DigitalOcean, Heroku) - Automated daily backups

#### What to Back Up

| Component | Frequency | Method |
|-----------|-----------|--------|
| **PostgreSQL database** | Daily | `pg_dump` or volume snapshot |
| **Environment variables** | On change | Encrypted secrets vault (Vault, AWS Secrets Manager) |
| **Docker volumes** | Weekly | Volume snapshot |
| **Configuration files** | On change | Git repository (without secrets) |

#### Testing Backups

**Always test your backups regularly:**
```bash
# Restore to test database
createdb glp_sync_test
psql glp_sync_test < glp_sync_backup.sql

# Verify data integrity
psql glp_sync_test -c "SELECT COUNT(*) FROM devices;"
psql glp_sync_test -c "SELECT COUNT(*) FROM subscriptions;"

# Clean up
dropdb glp_sync_test
```

### What ports need to be exposed?

Port requirements depend on deployment mode:

#### Production Deployment (Public Internet)

**Externally exposed (public-facing):**
| Port | Service | Protocol | Required? | Notes |
|------|---------|----------|-----------|-------|
| **80** | Frontend (nginx) | HTTP | Yes | Redirect to HTTPS |
| **443** | Frontend (nginx) | HTTPS | Yes | TLS termination with reverse proxy |

**Internal only (Docker network):**
| Port | Service | Protocol | Purpose |
|------|---------|----------|---------|
| 5432 | PostgreSQL | TCP | Database connections |
| 6379 | Redis | TCP | WebSocket ticket auth |
| 8000 | API Server | HTTP | Backend API (proxied by nginx) |
| 8010 | MCP Server | HTTP | AI assistant tools |
| 8080 | Scheduler | HTTP | Health checks |

#### Development Deployment (Local)

All ports exposed to localhost:
| Port | Service | Access URL |
|------|---------|------------|
| **80** | Frontend | http://localhost |
| 5432 | PostgreSQL | localhost:5432 (for SQL clients) |
| 6379 | Redis | localhost:6379 (for Redis CLI) |
| 8000 | API Server | http://localhost:8000/api |
| 8010 | MCP Server | http://localhost:8010 |
| 8080 | Scheduler | http://localhost:8080/health |

#### Docker Compose Configuration

**Production (docker-compose.prod.yml):**
```yaml
services:
  frontend:
    ports:
      - "80:80"      # Only expose frontend
      - "443:443"    # HTTPS (if configured)

  postgres:
    # No ports exposed (internal only)

  api-server:
    # No ports exposed (proxied by nginx)
```

**Development (docker-compose.yml):**
```yaml
services:
  postgres:
    ports:
      - "5432:5432"  # Expose for database tools
```

#### Firewall Configuration

**Production server:**
```bash
# Allow HTTPS (recommended)
ufw allow 443/tcp

# Allow HTTP (for Let's Encrypt and redirect to HTTPS)
ufw allow 80/tcp

# Allow SSH (for management)
ufw allow 22/tcp

# Block all other inbound traffic
ufw default deny incoming
ufw enable
```

**Cloud security groups (AWS example):**
- **Inbound:** 443/tcp (0.0.0.0/0), 80/tcp (0.0.0.0/0), 22/tcp (your-ip/32)
- **Outbound:** All traffic allowed (for API calls to GreenLake)

### Can I use this with on-premises GreenLake?

**Yes, this works with both HPE GreenLake Cloud and on-premises Private Cloud deployments.**

#### Configuration for On-Premises GreenLake

Update the `GLP_BASE_URL` environment variable to point to your on-premises instance:

```bash
# .env file
GLP_BASE_URL=https://greenlake.your-company.com
GLP_TOKEN_URL=https://greenlake.your-company.com/as/token.oauth2
GLP_CLIENT_ID=your-client-id
GLP_CLIENT_SECRET=your-client-secret
```

#### API Endpoint Requirements

Your on-premises GreenLake must support these API endpoints:
- **OAuth2 token endpoint** - `/as/token.oauth2`
- **Devices API** - `/api/compute/v1beta1/devices` (paginated)
- **Subscriptions API** - `/api/subs-billing/v1/subscriptions` (paginated)
- **Device management API** - `/api/compute/v2beta1/devices` (optional, for write operations)

#### Network Connectivity

Ensure network access from your deployment to GreenLake:
```bash
# Test connectivity
curl -I https://greenlake.your-company.com

# Test OAuth2 endpoint
curl -X POST https://greenlake.your-company.com/as/token.oauth2 \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=your-client-id" \
  -d "client_secret=your-client-secret"
```

**Firewall requirements:**
- Allow outbound HTTPS (443) to your GreenLake instance
- No inbound connections required (sync is pull-based)

#### TLS Certificates

For on-premises deployments with self-signed certificates:
```bash
# Option 1: Trust the certificate (development only)
export CURL_CA_BUNDLE=/path/to/your-ca-bundle.crt

# Option 2: Disable SSL verification (INSECURE - not recommended)
# Add to docker-compose.yml:
environment:
  - PYTHONHTTPSVERIFY=0
```

**Production:** Always use valid TLS certificates (Let's Encrypt, corporate CA)

#### Hybrid Deployments

You can sync from multiple GreenLake instances by running separate deployments:
```bash
# Instance 1 - Cloud
docker compose -f docker-compose.cloud.yml up -d

# Instance 2 - On-premises
docker compose -f docker-compose.onprem.yml up -d
```

Each deployment maintains its own database and can be configured with different credentials.

### How often does the sync run?

Sync frequency is configurable based on your needs:

#### Default Behavior

**Automated sync (scheduler service):**
- **Default interval:** Every 60 minutes
- **Configurable via:** `SYNC_INTERVAL_MINUTES` environment variable
- **Health checks:** Every 30 seconds on port 8080

```bash
# .env file
SYNC_INTERVAL_MINUTES=60  # Sync every hour
```

#### Custom Intervals

**Recommended intervals based on use case:**

| Use Case | Interval | Configuration | Rationale |
|----------|----------|---------------|-----------|
| **Development/Testing** | 5 minutes | `SYNC_INTERVAL_MINUTES=5` | Rapid iteration and testing |
| **Light production** | 60 minutes | `SYNC_INTERVAL_MINUTES=60` | Default (balanced) |
| **Heavy production** | 30 minutes | `SYNC_INTERVAL_MINUTES=30` | More up-to-date data |
| **Low-change environments** | 240 minutes (4 hours) | `SYNC_INTERVAL_MINUTES=240` | Reduce API load |
| **Once daily** | 1440 minutes (24 hours) | `SYNC_INTERVAL_MINUTES=1440` | Nightly batch sync |

**Example configuration:**
```bash
# docker-compose.yml
services:
  scheduler:
    environment:
      - SYNC_INTERVAL_MINUTES=30  # Sync every 30 minutes
```

#### Manual Sync (One-Time)

**CLI (without scheduler):**
```bash
# Sync both devices and subscriptions
python main.py

# Devices only
python main.py --devices

# Subscriptions only
python main.py --subscriptions
```

**Docker one-off sync:**
```bash
# Run sync once and exit
docker compose run --rm sync-once
```

#### Sync Performance

**Typical sync duration:**
- **100 devices:** 10-30 seconds
- **1,000 devices:** 1-3 minutes
- **10,000 devices:** 10-20 minutes
- **Subscriptions:** Usually faster (50 items per page vs 2,000 for devices)

**Factors affecting sync time:**
- GreenLake API response times
- Network latency
- Database write performance
- Number of devices/subscriptions

#### Monitoring Sync Operations

**View sync history:**
```sql
-- Last 10 sync operations
SELECT * FROM sync_history ORDER BY sync_started_at DESC LIMIT 10;

-- Sync statistics
SELECT
  sync_type,
  COUNT(*) as total_runs,
  AVG(items_synced) as avg_items,
  AVG(EXTRACT(EPOCH FROM (sync_completed_at - sync_started_at))) as avg_duration_seconds
FROM sync_history
WHERE sync_status = 'completed'
GROUP BY sync_type;
```

**Health check endpoint:**
```bash
# Check scheduler health
curl http://localhost:8080/health

# Response (healthy):
{
  "status": "healthy",
  "last_sync": "2024-01-13T20:30:00Z",
  "next_sync": "2024-01-13T21:30:00Z"
}
```

#### Best Practices

1. **Start conservative** - Begin with 60-minute intervals and adjust based on observed data change frequency
2. **Monitor API quotas** - Check if your GreenLake API has rate limits
3. **Use circuit breaker** - Built-in resilience layer prevents cascading failures
4. **Schedule off-peak** - For daily syncs, run during low-traffic hours (2-4 AM)
5. **Test incrementally** - Use manual sync to test before enabling automated scheduler

### How do I upgrade to a new version?

Upgrading depends on your deployment method:

#### Docker Compose (Recommended)

**Using Docker Hub images (docker-compose.prod.yml):**
```bash
# Pull latest images
docker compose -f docker-compose.prod.yml pull

# Restart services with new images
docker compose -f docker-compose.prod.yml up -d

# View updated versions
docker compose -f docker-compose.prod.yml images
```

**Building locally (docker-compose.yml):**
```bash
# Pull latest code
git fetch origin
git checkout main
git pull origin main

# Rebuild images
docker compose build --no-cache

# Restart services
docker compose up -d
```

#### Manual Installation

```bash
# Pull latest code
git pull origin main

# Update Python dependencies
uv sync --upgrade

# Update frontend dependencies
cd frontend && npm install && cd ..

# Restart services
# (depends on your process manager - systemd, supervisor, etc.)
```

#### Database Migrations

**Check for pending migrations:**
```bash
# View migration files
ls -la db/migrations/

# Apply migrations manually (if needed)
docker compose exec postgres psql -U glp -d greenlake -f /docker-entrypoint-initdb.d/migrations/XXXX_migration_name.sql
```

**Automatic migrations:** The PostgreSQL container automatically applies schema files on first startup. For existing databases, migrations must be applied manually.

#### Rolling Back

If an upgrade causes issues:
```bash
# Docker Hub images - use specific version tag
docker compose -f docker-compose.prod.yml pull jgiet001/glp-sync:v0.1.0
docker compose -f docker-compose.prod.yml up -d

# Local build - checkout previous commit
git checkout <previous-commit-sha>
docker compose build
docker compose up -d
```

#### Release Notes

Always check the [GitHub Releases](https://github.com/Jgiet001-AI/GLP-Sync-2/releases) page for:
- Breaking changes
- Required migrations
- New environment variables
- Deprecation notices

### How do I reset/delete all data?

To completely reset the database and start fresh:

#### Full Reset (⚠️ DATA LOSS)

```bash
# Stop all services
docker compose down

# Remove database volume
docker volume rm glp-sync-2_postgres_data

# Remove Redis data (WebSocket tickets, cache)
docker volume rm glp-sync-2_redis_data

# Restart services (schema will auto-apply)
docker compose up -d
```

#### Selective Data Deletion

**Delete devices only:**
```sql
-- Connect to database
docker compose exec postgres psql -U glp -d greenlake

-- Delete all devices (cascades to device_tags, device_subscriptions)
TRUNCATE TABLE devices CASCADE;

-- Verify
SELECT COUNT(*) FROM devices;  -- Should return 0
```

**Delete subscriptions only:**
```sql
-- Delete all subscriptions (cascades to subscription_tags)
TRUNCATE TABLE subscriptions CASCADE;
```

**Delete sync history:**
```sql
-- Delete old sync logs (keep last 30 days)
DELETE FROM sync_history WHERE created_at < NOW() - INTERVAL '30 days';

-- Or delete all sync history
TRUNCATE TABLE sync_history;
```

**Delete AI chat history:**
```sql
-- Delete all conversations and messages
TRUNCATE TABLE agent_messages CASCADE;
TRUNCATE TABLE agent_conversations CASCADE;
```

#### Restart from Scratch (Keep Configuration)

```bash
# Stop services
docker compose down

# Remove only data volumes (keeps configuration)
docker volume rm glp-sync-2_postgres_data glp-sync-2_redis_data

# Restart
docker compose up -d

# Run initial sync
docker compose exec scheduler python main.py
```

### Can I run multiple instances/tenants?

**Yes, this supports multi-tenant deployments.** Each tenant should have its own isolated deployment.

#### Option 1: Separate Docker Compose Stacks

```bash
# Tenant 1
cd /opt/glp-sync-tenant1
cp .env.example .env
nano .env  # Configure tenant1 credentials
docker compose -p tenant1 up -d

# Tenant 2
cd /opt/glp-sync-tenant2
cp .env.example .env
nano .env  # Configure tenant2 credentials
docker compose -p tenant2 up -d
```

**Port conflicts:** Modify `docker-compose.yml` to use different host ports:
```yaml
# Tenant 1 - ports 80, 5432, 8000
frontend:
  ports:
    - "80:80"

# Tenant 2 - ports 8081, 5433, 8001
frontend:
  ports:
    - "8081:80"
postgres:
  ports:
    - "5433:5432"
```

#### Option 2: Shared Database with Row-Level Security

**Not currently supported out-of-the-box.** The schema does not include tenant isolation at the database level. For multi-tenant scenarios, use Option 1 (separate stacks).

**Future enhancement:** Planned support for `tenant_id` column with Row-Level Security (RLS) policies.

#### Option 3: Kubernetes Namespaces

```bash
# Deploy to separate namespaces
kubectl create namespace tenant1
kubectl create namespace tenant2

# Install Helm chart for each tenant
helm install glp-sync ./k8s/helm/glp-sync \
  --namespace tenant1 \
  --set env.GLP_CLIENT_ID=$TENANT1_CLIENT_ID

helm install glp-sync ./k8s/helm/glp-sync \
  --namespace tenant2 \
  --set env.GLP_CLIENT_ID=$TENANT2_CLIENT_ID
```

### What browsers are supported?

The React dashboard is built with modern web standards and supports:

#### Fully Supported (Tested)

| Browser | Minimum Version | Notes |
|---------|-----------------|-------|
| **Google Chrome** | 90+ | Recommended for best performance |
| **Microsoft Edge** | 90+ | Chromium-based, full support |
| **Mozilla Firefox** | 88+ | Full support |
| **Safari** | 14+ | macOS/iOS, full support |

#### Partially Supported

| Browser | Minimum Version | Limitations |
|---------|-----------------|-------------|
| **Safari** | 13 | WebSocket may have issues on older versions |
| **Firefox ESR** | 78+ | Older versions may lack ES2020 features |

#### Not Supported

- **Internet Explorer** - All versions (deprecated by Microsoft)
- **Legacy Edge** (pre-Chromium) - Versions <79

#### Required Features

The dashboard requires these modern browser capabilities:
- **ES2020 JavaScript** - `async`/`await`, optional chaining, nullish coalescing
- **WebSocket** - For AI chatbot real-time streaming
- **Fetch API** - For API requests
- **CSS Grid** - For responsive layouts
- **Local Storage** - For persisting user preferences

#### Testing Your Browser

Visit the dashboard and open browser console:
```javascript
// Check WebSocket support
console.log('WebSocket' in window);  // Should be true

// Check Fetch API
console.log('fetch' in window);  // Should be true
```

If the dashboard fails to load, check:
1. Browser version is up-to-date
2. JavaScript is enabled
3. Browser console for errors (F12 or Cmd+Option+I)

### What's the difference between docker-compose.yml and docker-compose.prod.yml?

There are three Docker Compose files for different use cases:

#### docker-compose.yml (Development)

**Best for:** Local development, testing, customization

**Features:**
- **Builds locally** - Compiles code from source (slower startup)
- **All ports exposed** - PostgreSQL, Redis, API server accessible for debugging
- **Live reload** - Frontend auto-refreshes on code changes (with volume mounts)
- **Development mode** - Authentication can be disabled for testing
- **Verbose logging** - More detailed logs for debugging

**Usage:**
```bash
docker compose up -d
```

#### docker-compose.prod.yml (Production)

**Best for:** Production deployments, quick setup, CI/CD

**Features:**
- **Pre-built images** - Pulls from Docker Hub (fast startup)
- **Minimal ports** - Only frontend (80/443) exposed
- **Security hardening** - Non-root users, dropped capabilities, read-only filesystems
- **Resource limits** - CPU/memory constraints to prevent resource exhaustion
- **Health checks** - Automatic restart on failure
- **Production logging** - JSON-formatted, structured logs

**Usage:**
```bash
docker compose -f docker-compose.prod.yml up -d
```

#### docker-compose.secure.yml (Security Hardened)

**Best for:** High-security environments, compliance requirements

**Features:**
- All production features, plus:
- **No host ports** - PostgreSQL/Redis only accessible via Docker network
- **Strict capabilities** - PostgreSQL runs with minimal capabilities
- **Read-only root FS** - All writable areas use tmpfs
- **SCRAM-SHA-256** - Strong PostgreSQL authentication

**Usage:**
```bash
docker compose -f docker-compose.secure.yml up -d
```

#### Comparison Table

| Feature | docker-compose.yml | docker-compose.prod.yml | docker-compose.secure.yml |
|---------|-------------------|------------------------|---------------------------|
| **Image source** | Local build | Docker Hub | Docker Hub |
| **Startup time** | Slow (builds) | Fast (pulls) | Fast (pulls) |
| **PostgreSQL port** | Exposed (5432) | Localhost only | Not exposed |
| **Authentication** | Optional | Required | Required |
| **Security hardening** | Basic | Advanced | Maximum |
| **Resource limits** | None | Moderate | Strict |
| **Best for** | Development | Production | High-security prod |

#### Switching Between Modes

```bash
# From development to production
docker compose down
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# From production to development
docker compose -f docker-compose.prod.yml down
docker compose build
docker compose up -d
```

**Note:** Database data persists across mode switches (stored in Docker volumes).

### Where can I get help?

If you're stuck or need assistance:

#### Documentation

1. **README** - This file contains comprehensive setup and usage guides
2. **CLAUDE.md** - Technical architecture and development patterns
3. **Troubleshooting section** - Common issues and solutions (see above)
4. **API documentation** - OpenAPI spec at `http://localhost:8000/docs`

#### Community Support

- **GitHub Issues** - [Report bugs or request features](https://github.com/Jgiet001-AI/GLP-Sync-2/issues)
- **GitHub Discussions** - [Ask questions and share ideas](https://github.com/Jgiet001-AI/GLP-Sync-2/discussions)
- **Pull Requests** - [Contribute fixes and improvements](https://github.com/Jgiet001-AI/GLP-Sync-2/pulls)

#### Before Asking for Help

**Gather diagnostic information:**

1. **Check logs** - Most issues are explained in logs:
   ```bash
   docker compose logs > debug-logs.txt
   docker compose logs api-server > api-logs.txt
   docker compose logs scheduler > scheduler-logs.txt
   ```

2. **Verify environment** - Share configuration (redact secrets):
   ```bash
   docker compose config > docker-config.txt
   cat .env | grep -v "SECRET\|PASSWORD\|KEY" > env-sanitized.txt
   ```

3. **Test connectivity** - Verify network access:
   ```bash
   curl -I http://localhost:8000/api/health
   curl -I https://global.api.greenlake.hpe.com
   ```

4. **Check versions** - Include in your issue report:
   ```bash
   docker --version
   docker compose version
   python --version
   node --version
   ```

#### Creating a Good Issue Report

Include in your GitHub issue:
- **Clear title** - Summarize the problem
- **Description** - What you expected vs what happened
- **Steps to reproduce** - How to recreate the issue
- **Environment details** - OS, Docker version, deployment mode
- **Logs** - Relevant excerpts (not the entire log file)
- **Screenshots** - For UI issues

**Example:**
```markdown
**Title:** API server fails to start with "Database connection refused"

**Environment:**
- OS: Ubuntu 22.04
- Docker: 24.0.6
- Docker Compose: 2.21.0
- Deployment: docker-compose.yml (local build)

**Steps to reproduce:**
1. Clone repository
2. Copy .env.example to .env
3. Run `docker compose up -d`
4. Check logs: `docker compose logs api-server`

**Expected:** API server starts successfully
**Actual:** Container exits with error "Database connection refused"

**Logs:**
```
api-server | ERROR: could not connect to server: Connection refused
api-server |   Is the server running on host "postgres" (172.18.0.2) and accepting
api-server |   TCP/IP connections on port 5432?
```
```

#### Response Time

- **Bug reports** - Typically within 2-3 days
- **Feature requests** - Discussion within 1 week
- **Security issues** - Within 48 hours (use private reporting)

#### Commercial Support

For enterprise support, custom development, or consulting:
- Contact via GitHub Issues with `[Commercial Support]` tag
- Or email directly (see repository maintainer profile)

**We're here to help!** Don't hesitate to ask questions or report issues. Every issue report helps improve the project for everyone.

## Roadmap

We're actively developing new features and improvements to make HPE GreenLake Device & Subscription Sync more powerful and user-friendly. Here's what's planned for future releases:

### 🎯 Near Term (Q1-Q2 2026)

#### Enhanced Dashboard Experience
- **Interactive Charts** - Click-through navigation from all dashboard elements to filtered views
- **Advanced Command Palette** - Universal search across devices, subscriptions, and Aruba Central clients with keyboard shortcuts
- **Real-Time Updates** - WebSocket-based live data refresh with visual indicators for data freshness
- **Customizable Widgets** - Drag-and-drop dashboard layout with collapsible sections and saved preferences

#### Smart Filtering & Search
- **Faceted Filters** - Multi-select filters with result counts and filter chips for quick clearing
- **Search History** - Persistent search history with recent items carousel and quick actions
- **Advanced Query Builder** - Visual query builder for complex AND/OR/NOT filter combinations
- **View Presets** - Save and share filter configurations as named presets ("Expiring Soon", "Unassigned APs", etc.)

#### Device Assignment Enhancements
- **Bulk Operations** - Assign subscriptions, regions, and tags to hundreds of devices simultaneously
- **Assignment Validation** - Pre-flight checks for compatibility and quota availability
- **Progress Tracking** - Real-time SSE streaming for long-running operations with detailed status updates
- **Rollback Support** - Undo recent assignment changes with one-click rollback

### 🚀 Mid Term (Q3-Q4 2026)

#### Multi-Tenant Architecture
- **Tenant Isolation** - Row-level security in PostgreSQL for secure multi-tenant deployments
- **Per-Tenant Credentials** - Separate GreenLake API credentials and settings per tenant
- **Tenant Dashboard** - Admin panel for managing multiple tenants and viewing aggregate statistics
- **Usage Metering** - Track sync operations, API calls, and storage per tenant

#### Advanced Analytics
- **Subscription Forecasting** - Predict subscription renewal dates and capacity requirements using ML
- **Cost Optimization** - Identify underutilized subscriptions and recommend consolidation opportunities
- **Trend Analysis** - Historical charts showing device growth, subscription utilization, and regional distribution
- **Anomaly Detection** - Alert on unusual patterns (e.g., spike in expiring subscriptions, unexpected device additions)

#### Enhanced AI Chatbot
- **Proactive Insights** - AI-generated summaries of key changes ("10 subscriptions expiring in 7 days")
- **Natural Language Queries** - Ask complex questions in plain English ("Show me all APs in US-West with expiring subscriptions")
- **Automated Reports** - Schedule AI-generated reports delivered via email or Slack
- **Multi-Turn Conversations** - Context-aware follow-up questions with conversation branching

#### Integration Ecosystem
- **ServiceNow Integration** - Sync device inventory to CMDB with bidirectional updates
- **Slack/Teams Notifications** - Real-time alerts for expiring subscriptions and sync failures
- **Webhook Support** - Trigger external workflows on device/subscription changes
- **REST API Expansion** - Public API for third-party integrations with OpenAPI 3.1 spec

### 🔮 Long Term (2027+)

#### Intelligent Automation
- **Auto-Assignment Rules** - Define policies to automatically assign devices to subscriptions based on type, region, or tags
- **Self-Healing Sync** - Automatically retry failed syncs with exponential backoff and circuit breaker recovery
- **Capacity Planning** - Recommend subscription purchases based on forecasted device growth
- **License Optimization** - Suggest subscription tier changes to match actual usage patterns

#### Advanced Visualization
- **Interactive Network Topology** - Visual map of devices, subscriptions, and their relationships
- **Geolocation Mapping** - Plot devices on world map based on region/site data
- **Timeline View** - Visualize device lifecycle events and subscription validity periods
- **Custom Dashboards** - Build personalized dashboards with drag-and-drop widgets and custom metrics

#### Enterprise Features
- **RBAC (Role-Based Access Control)** - Fine-grained permissions for read/write access to devices and subscriptions
- **Audit Logging** - Comprehensive audit trail for all changes with compliance reporting
- **SSO Integration** - OAuth2/SAML support for Okta, Azure AD, Google Workspace
- **High Availability** - Multi-region deployment with automatic failover and data replication
- **Disaster Recovery** - Automated backups with point-in-time recovery and geo-redundant storage

#### Platform Extensions
- **HPE Compute Ops Management** - Sync compute server inventory from COM API
- **HPE Alletra Storage** - Track storage arrays and capacity utilization
- **Aruba EdgeConnect SD-WAN** - Integrate WAN edge devices and policies
- **Custom Connectors** - Plugin architecture for integrating arbitrary data sources

### 📊 Performance & Scalability

#### Optimization Roadmap
- **Incremental Sync** - Delta sync to only fetch changed devices/subscriptions (reduce sync time by 90%)
- **Database Partitioning** - Table partitioning for 100k+ devices with improved query performance
- **Redis Caching** - Cache frequently accessed data with automatic invalidation
- **Read Replicas** - PostgreSQL read replicas for scaling dashboard queries
- **CDN Integration** - Serve frontend assets via CDN for global low-latency access

### 🧪 Developer Experience

#### Tooling & Testing
- **GraphQL API** - Alternative to REST with type-safe queries and schema introspection
- **OpenAPI SDK Generation** - Auto-generated client libraries for Python, TypeScript, Go
- **Local Development Mode** - Mock GreenLake API for offline development and testing
- **Helm Charts** - Production-ready Kubernetes deployment with GitOps support
- **Terraform Modules** - Infrastructure as Code for cloud deployments (AWS, Azure, GCP)

### 💡 Community Requests

We prioritize features based on community feedback. Vote for features or suggest new ones via [GitHub Discussions](https://github.com/Jgiet001-AI/GLP-Sync-2/discussions).

**Most Requested:**
- **Mobile App** - iOS/Android app for on-the-go device management
- **Export to Excel** - Export filtered device/subscription lists to Excel with custom columns
- **Email Reports** - Scheduled email reports with PDF attachments
- **Dark Mode** - Full dark theme support across dashboard and chat
- **Bulk Import** - Upload CSV to create/update devices in bulk

### 🤝 Contributing to the Roadmap

Have an idea for a feature? We'd love to hear it!

1. **Check existing issues** - See if it's already planned: [GitHub Issues](https://github.com/Jgiet001-AI/GLP-Sync-2/issues)
2. **Open a feature request** - Use the feature request template
3. **Join the discussion** - Comment on roadmap items to show support
4. **Contribute code** - See [Contributing](#contributing) section for guidelines

### 📅 Release Schedule

- **Patch releases** (bug fixes, security updates) - Monthly
- **Minor releases** (new features) - Quarterly
- **Major releases** (breaking changes, architecture updates) - Annually

**Latest release:** v0.2.0 ([Changelog](https://github.com/Jgiet001-AI/GLP-Sync-2/releases))

**Next planned release:** v0.3.0 (March 2026) - Enhanced Dashboard Experience

---

*Roadmap items are subject to change based on community feedback, technical feasibility, and business priorities. Dates are estimates and not commitments.*

## License

MIT
