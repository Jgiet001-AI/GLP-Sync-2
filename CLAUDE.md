# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HPE GreenLake Device & Subscription Sync - A comprehensive platform for syncing device and subscription inventory from HPE GreenLake Platform (GLP) API to PostgreSQL. Features include a React dashboard, AI chatbot with Anthropic/OpenAI support, Aruba Central integration, and Docker deployment with security hardening.

## Commands

### Development Setup
```bash
uv sync                    # Install all dependencies
uv sync --no-dev          # Production dependencies only
```

### Running Services
```bash
# API Server (FastAPI)
uv run uvicorn src.glp.assignment.app:app --reload --port 8000

# Frontend (React)
cd frontend && npm install && npm run dev

# Scheduler
python scheduler.py

# MCP Server
python server.py --transport http --port 8010
```

### Testing
```bash
uv run pytest tests/ -v                              # All tests
uv run pytest tests/test_auth.py tests/test_devices.py -v  # Unit tests (no DB)
uv run pytest tests/test_database.py -v              # Database tests
uv run pytest tests/assignment/ -v                   # Assignment tests
uv run pytest tests/agent/ -v                        # Agent chatbot tests
uv run pytest tests/sync/ -v                         # Clean sync tests
```

### Linting
```bash
uv run ruff check .
```

### CLI
```bash
python main.py                          # Sync both devices & subscriptions
python main.py --devices               # Devices only
python main.py --subscriptions         # Subscriptions only
python main.py --json-only             # Export to JSON (no DB required)
python main.py --expiring-days 90      # Show expiring subscriptions
```

### Docker
```bash
# Development
docker compose up -d                   # Start full stack
docker compose logs -f                 # View all logs
docker compose run --rm sync-once      # One-time sync
docker compose down -v                 # Stop and remove data

# Production (pre-built images)
docker compose -f docker-compose.prod.yml up -d

# Security-hardened
docker compose -f docker-compose.secure.yml up -d

# Build and push to Docker Hub
docker compose build
docker compose push
```

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
│   (5432)    │    │   (6379)    │       │   (8010)    │
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

**Key Design Principles:**
- Clean Architecture with domain, use_cases, adapters layers
- All I/O is async (aiohttp, asyncpg, asyncio)
- Circuit breaker pattern for API resilience
- Full API responses stored in JSONB `raw_data`, important fields normalized
- Non-root Docker containers with security hardening
- WebSocket ticket authentication for real-time chat

## Source Structure

### Core Sync
- `main.py` - CLI entry point for one-time syncs
- `scheduler.py` - Long-running scheduler with health endpoint
- `server.py` - FastMCP server (27 read-only database tools)

### API Layer (`src/glp/api/`)
- `auth.py` - OAuth2 TokenManager with token caching
- `client.py` - Generic GLPClient with pagination and resilience
- `devices.py` - DeviceSyncer (fetch + upsert devices)
- `subscriptions.py` - SubscriptionSyncer (fetch + upsert subscriptions)
- `resilience.py` - Circuit breaker and retry logic
- `device_manager.py` - Device write operations (v2beta1 API)
- `aruba_*.py` - Aruba Central integration

### Agent Chatbot (`src/glp/agent/`)
- `api/router.py` - WebSocket and REST endpoints
- `api/auth.py` - JWT authentication
- `orchestrator/agent.py` - Main agent logic
- `providers/anthropic.py` - Claude integration
- `providers/openai.py` - GPT integration
- `memory/conversation.py` - Conversation history
- `memory/semantic.py` - Semantic search with embeddings
- `security/ticket_auth.py` - Redis-based WebSocket tickets
- `security/cot_redactor.py` - Chain-of-thought redaction
- `tools/registry.py` - MCP tool registry
- `tools/write_executor.py` - Rate-limited write operations

### Device Assignment (`src/glp/assignment/`)
- `domain/entities.py` - DeviceAssignment, SubscriptionOption
- `domain/ports.py` - Repository interfaces
- `use_cases/apply_assignments.py` - Bulk assignment logic
- `use_cases/sync_and_report.py` - Post-assignment sync
- `adapters/postgres_device_repo.py` - Database operations
- `adapters/excel_parser.py` - Excel file processing
- `api/router.py` - FastAPI endpoints with SSE streaming

### Clean Sync Module (`src/glp/sync/`)
- `domain/entities.py` - Device, Subscription entities
- `domain/ports.py` - Repository and API ports
- `use_cases/sync_devices.py` - Device sync orchestration
- `use_cases/sync_subscriptions.py` - Subscription sync
- `adapters/glp_api_adapter.py` - GreenLake API adapter
- `adapters/postgres_device_repo.py` - Database adapter

### Frontend (`frontend/`)
- `src/pages/` - Dashboard, DevicesList, SubscriptionsList, ClientsPage
- `src/components/chat/` - ChatWidget, ChatMessage
- `src/components/filters/` - Filter panels
- `src/hooks/useChat.ts` - WebSocket chat hook
- `src/hooks/useAssignment.ts` - Assignment workflow

## Database

### Tables
- `devices` (28 cols) - Device inventory with JSONB raw_data
- `subscriptions` (20 cols) - Subscription inventory
- `device_subscriptions` - M:M relationship
- `device_tags`, `subscription_tags` - Normalized tags
- `sync_history` - Audit log
- `agent_conversations` - Chat sessions
- `agent_messages` - Messages with embeddings (pgvector)

### Views
- `active_devices`, `active_subscriptions`
- `devices_expiring_soon`, `subscriptions_expiring_soon`
- `device_summary`, `subscription_summary`

### Functions
- `search_devices(query, limit)` - Full-text search
- `get_devices_by_tag(key, value)` - Tag-based lookup

Schema files: `db/schema.sql`, `db/subscriptions_schema.sql`, `db/migrations/`

## Environment Variables

### Required
- `GLP_CLIENT_ID`, `GLP_CLIENT_SECRET`, `GLP_TOKEN_URL` - GreenLake OAuth2
- `DATABASE_URL` - PostgreSQL connection
- `API_KEY` - Dashboard authentication

### Optional - Core
- `GLP_BASE_URL` - API base (default: `https://global.api.greenlake.hpe.com`)
- `SYNC_INTERVAL_MINUTES` - Scheduler interval (default: 60)
- `SYNC_DEVICES`, `SYNC_SUBSCRIPTIONS` - Enable/disable (default: true)
- `HEALTH_CHECK_PORT` - Health endpoint (default: 8080)

### Optional - Agent
- `JWT_SECRET` - JWT signing secret
- `ANTHROPIC_API_KEY` - Claude API key
- `OPENAI_API_KEY` - GPT API key
- `REDIS_URL` - WebSocket ticket store

### Optional - Aruba Central
- `ARUBA_CLIENT_ID`, `ARUBA_CLIENT_SECRET`, `ARUBA_TOKEN_URL`, `ARUBA_BASE_URL`

## Docker Deployment

### Services
| Service | Port | Description |
|---------|------|-------------|
| postgres | 5432 | PostgreSQL 16 with pgvector |
| redis | 6379 | WebSocket ticket auth |
| scheduler | 8080 | Sync scheduler |
| api-server | 8000 | FastAPI backend |
| mcp-server | 8010 | MCP for AI assistants |
| frontend | 80 | React + nginx |

### Compose Files
- `docker-compose.yml` - Development with local builds
- `docker-compose.prod.yml` - Production with pre-built images
- `docker-compose.secure.yml` - Security-hardened

### Security Features
- Base images pinned by SHA256 digest
- Non-root users (appuser UID 1000, nginx)
- Read-only filesystems (secure compose)
- Dropped capabilities, no-new-privileges
- Resource limits (CPU/memory)
- Ports bound to localhost (prod/secure)

## Testing Notes

- Unit tests use mocks, no external services required
- Database tests require PostgreSQL (CI provides service container)
- Agent tests mock LLM providers
- Use pytest-asyncio for async tests
- Coverage: `uv run pytest --cov=src tests/`

## CI/CD

### GitHub Actions
- `ci.yml` - Tests, linting on push/PR
- `publish.yml` - Multi-arch Docker builds, Trivy scanning, Docker Hub push

### Required Setup
- Secret: `DOCKERHUB_TOKEN`
- Variable: `DOCKERHUB_USERNAME`

## Key Patterns

### Resilience
```python
from src.glp.api.resilience import CircuitBreaker, with_retry

@with_retry(max_attempts=3)
async def fetch_data():
    async with circuit_breaker:
        return await api.get("/devices")
```

### SSE Streaming
```python
@router.post("/apply-stream")
async def apply_stream(request: Request):
    async def generate():
        async for event in apply_assignments():
            yield f"data: {event.json()}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### WebSocket Chat
```python
@router.websocket("/chat")
async def chat(websocket: WebSocket, ticket: str):
    if not await verify_ticket(ticket):
        await websocket.close(code=4001)
        return
    await agent.stream_response(websocket, message)
```
