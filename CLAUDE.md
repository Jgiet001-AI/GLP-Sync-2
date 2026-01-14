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
- `server.py` - FastMCP server (27 read-only + 5 write tools for device management)

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
- `ANTHROPIC_API_KEY` - Claude API key (primary chat provider)
- `OPENAI_API_KEY` - GPT API key (fallback chat + embeddings)
- `OPENAI_EMBEDDING_MODEL` - Embedding model (default: text-embedding-3-large)
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

### Docker Hub Images
- `jgiet001/glp-sync` - Backend API server
- `jgiet001/glp-frontend` - React dashboard
- `jgiet001/glp-mcp-server` - MCP server for AI assistants
- `jgiet001/glp-scheduler` - Automated sync scheduler

### Security Features
- Base images pinned by SHA256 digest (Python 3.12-alpine, Node 22-alpine, nginx 1-alpine)
- Non-root users (appuser UID 1000, nginx)
- Dropped capabilities, no-new-privileges
- Resource limits (CPU/memory)
- PyJWT for secure JWT handling (replaced python-jose)

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

## MCP Server Write Tools

The MCP server (`server.py`) provides 5 write tools for device management operations through the Model Context Protocol. These tools enable AI assistants to perform device operations with built-in rate limiting, confirmation workflows, and error handling.

### Available Write Tools

1. **apply_device_assignments** - Apply subscriptions, applications, and tags to devices
2. **add_devices** - Add new devices to GreenLake Platform
3. **archive_devices** - Archive devices (high-risk operation)
4. **unarchive_devices** - Restore archived devices
5. **update_device_tags** - Bulk update device tags

### Environment Variables Required

Write operations require GreenLake OAuth2 credentials:
- `GLP_CLIENT_ID` - GreenLake client ID
- `GLP_CLIENT_SECRET` - GreenLake client secret
- `GLP_TOKEN_URL` - OAuth2 token endpoint
- `DATABASE_URL` - PostgreSQL connection string

### Tool Usage Examples

#### Apply Device Assignments
Bulk assignment of subscriptions, applications, and tags to devices:

```python
# Via MCP protocol
{
  "name": "apply_device_assignments",
  "arguments": {
    "assignments": [
      {
        "serial_number": "VNT9KWC01V",
        "application_id": "aruba_central",
        "region": "us-west",
        "subscription_key": "PAT4DYYJAEEEJA",
        "tags": {"customer": "Acme Corp", "location": "HQ"}
      }
    ],
    "wait_for_completion": true
  }
}
```

**Response:**
```json
{
  "status": "completed",
  "summary": {
    "total": 1,
    "existing_processed": 1,
    "new_devices_added": 0,
    "succeeded": 1,
    "failed": 0,
    "skipped": 0
  },
  "results": [...],
  "duration_seconds": 5.2
}
```

#### Add Devices
Add new devices to GreenLake Platform:

```python
{
  "name": "add_devices",
  "arguments": {
    "devices": [
      {
        "serial_number": "NEW123456",
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "part_number": "JL253A",
        "device_type": "SWITCH",
        "tags": {"new": "true"}
      }
    ],
    "wait_for_completion": true
  }
}
```

**Limits:** Maximum 25 devices per call for rate limiting.

#### Archive Devices (High-Risk)
Archive devices with confirmation workflow:

```python
# First call - triggers confirmation requirement
{
  "name": "archive_devices",
  "arguments": {
    "device_ids": ["uuid1", "uuid2", "uuid3"],
    "sync_after": true,
    "wait_for_completion": true
  }
}
```

**Response (requires confirmation):**
```json
{
  "status": "confirmation_required",
  "risk_level": "high",
  "operation_type": "archive_devices",
  "device_count": 3,
  "message": "⚠️ Archive 3 devices - This operation will archive devices...",
  "confirmation_hint": "Call again with confirmed=true to proceed"
}
```

**Confirmed call:**
```python
{
  "name": "archive_devices",
  "arguments": {
    "device_ids": ["uuid1", "uuid2", "uuid3"],
    "confirmed": true,
    "wait_for_completion": true
  }
}
```

#### Unarchive Devices
Restore archived devices:

```python
{
  "name": "unarchive_devices",
  "arguments": {
    "device_ids": ["uuid1", "uuid2"],
    "sync_after": true,
    "wait_for_completion": true
  }
}
```

#### Update Device Tags
Bulk update tags across devices:

```python
{
  "name": "update_device_tags",
  "arguments": {
    "device_ids": ["uuid1", "uuid2"],
    "tags": {
      "environment": "production",  # Add/update tag
      "old_tag": null                # Remove tag
    },
    "wait_for_completion": true
  }
}
```

**Limits:** Maximum 25 devices per call.

### Rate Limiting

Write operations are automatically rate-limited to prevent hitting GreenLake API limits:

- **PATCH operations** (apply_assignments, archive, unarchive, update_tags): 3.5s interval (max 17/min, limit is 20/min)
- **POST operations** (add_devices): 2.6s interval (max 23/min, limit is 25/min)

Rate limiting is handled transparently using `SequentialRateLimiter` from `src.glp.api.resilience`.

### Confirmation Workflow

High-risk operations trigger confirmation workflows based on:

**Risk Levels:**
- **LOW**: No confirmation (add_device, update_tags for ≤5 devices)
- **MEDIUM**: Confirmation recommended (apply_assignments, unarchive)
- **HIGH**: Confirmation required (archive_devices)
- **CRITICAL**: Mass operations (>20 devices)

**Risk Elevation:**
- Operations affecting >5 devices: risk level increases
- Operations affecting >20 devices: CRITICAL risk level

**Confirmation Process:**
1. First call returns `status: "confirmation_required"` with risk assessment
2. User reviews operation details
3. Second call with `confirmed: true` executes the operation

### Error Handling

All write tools include comprehensive error handling:

```python
{
  "status": "error",
  "error": "GLP client not initialized. Set GLP_CLIENT_ID and GLP_CLIENT_SECRET.",
  "error_type": "ConfigurationError"
}
```

Common error types:
- `ConfigurationError` - Missing environment variables
- `ValidationError` - Invalid input (e.g., bad UUID, exceeds device limits)
- `GLPAPIError` - GreenLake API errors
- `OperationTimeout` - Operation didn't complete in time

### Best Practices

1. **Use wait_for_completion**: Set to `true` to ensure operations complete and sync results
2. **Check limits**: Don't exceed 25 devices for add_devices and update_device_tags
3. **Confirm high-risk operations**: Always review confirmation messages before proceeding
4. **Handle rate limits**: Tools automatically rate-limit, but avoid tight loops
5. **Validate UUIDs**: Device IDs must be valid UUIDs for archive/unarchive/update operations
6. **Sync after changes**: Use `sync_after: true` for archive/unarchive to ensure database reflects changes

### Integration with Agent Chatbot

The agent chatbot (`src/glp/agent/`) can call these MCP tools through the tool registry:

```python
from src.glp.agent.tools.registry import ToolRegistry

registry = ToolRegistry(mcp_server_url="http://localhost:8010")
result = await registry.call_tool("add_devices", devices=[...])
```

The agent includes additional safeguards:
- Chain-of-thought redaction for security
- Conversation context for multi-turn operations
- Semantic memory for learning from past operations
