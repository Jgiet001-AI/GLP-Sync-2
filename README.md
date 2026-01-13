# HPE GreenLake Device & Subscription Sync

[![CI](https://github.com/Jgiet001-AI/GLP-Sync-2/actions/workflows/ci.yml/badge.svg)](https://github.com/Jgiet001-AI/GLP-Sync-2/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.2.0-green)](https://github.com/Jgiet001-AI/GLP-Sync-2/releases)
[![Docker Hub](https://img.shields.io/badge/docker-jgiet001%2Fglp--sync-blue?logo=docker)](https://hub.docker.com/r/jgiet001/glp-sync)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive platform for syncing device and subscription inventory from HPE GreenLake Platform to PostgreSQL, with a React dashboard, AI chatbot, and Aruba Central integration.

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

## License

MIT
