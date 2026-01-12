# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HPE GreenLake Device & Subscription Sync - syncs device and subscription inventory from HPE GreenLake Platform (GLP) API to PostgreSQL with OAuth2 authentication, paginated fetching, and automated scheduling.

## Commands

### Development Setup
```bash
uv sync                    # Install dependencies
uv sync --no-dev          # Production dependencies only
```

### Testing
```bash
uv run pytest tests/ -v                                              # All 49 tests
uv run pytest tests/test_auth.py tests/test_devices.py tests/test_subscriptions.py -v  # Unit tests (no DB)
uv run pytest tests/test_database.py -v                              # Database tests (requires PostgreSQL)
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
docker compose up -d                   # Start full stack
docker compose logs -f scheduler       # View logs
docker compose run --rm sync-once      # One-time sync
docker compose down -v                 # Stop and remove data
```

## Architecture

```
GreenLake API
      │
      ▼
TokenManager (OAuth2 - auto-refresh with 5-min buffer)
      │
      ▼
GLPClient (HTTP layer - pagination, rate limits, retries)
      │
      ├──────────────────┐
      ▼                  ▼
DeviceSyncer      SubscriptionSyncer
      │                  │
      └────────┬─────────┘
               ▼
         PostgreSQL
```

**Key Design Principles:**
- GLPClient handles HTTP concerns only (auth, pagination, rate limiting)
- Syncers handle resource-specific logic (field mapping, DB operations)
- TokenManager handles OAuth2 exclusively
- All I/O is async (aiohttp, asyncpg, asyncio)
- Full API responses stored in JSONB `raw_data`, important fields normalized into columns

## Source Structure

- `main.py` - CLI entry point for one-time syncs
- `scheduler.py` - Long-running scheduler (Docker main process)
- `src/glp/api/auth.py` - OAuth2 TokenManager with token caching
- `src/glp/api/client.py` - Generic GLPClient with pagination (devices: 2000/page, subscriptions: 50/page)
- `src/glp/api/devices.py` - DeviceSyncer (fetch + upsert devices)
- `src/glp/api/subscriptions.py` - SubscriptionSyncer (fetch + upsert subscriptions)
- `src/glp/constants.py` - API URLs, cluster configs

## Database

**Tables:** `devices` (28 cols), `subscriptions` (20 cols), `device_subscriptions` (M:M), `device_tags`, `subscription_tags`, `sync_history`

**Views:** `active_devices`, `active_subscriptions`, `devices_expiring_soon`, `subscriptions_expiring_soon`, `device_summary`, `subscription_summary`

**Functions:** `search_devices(query, limit)`, `get_devices_by_tag(key, value)`

Schema files: `db/schema.sql`, `db/subscriptions_schema.sql`

## Environment Variables

Required:
- `GLP_CLIENT_ID`, `GLP_CLIENT_SECRET`, `GLP_TOKEN_URL` - OAuth2 credentials
- `DATABASE_URL` - PostgreSQL connection (not needed for `--json-only`)

Optional:
- `GLP_BASE_URL` - API base (default: `https://global.api.greenlake.hpe.com`)
- `SYNC_INTERVAL_MINUTES` - Scheduler interval (default: 60)
- `SYNC_DEVICES`, `SYNC_SUBSCRIPTIONS` - Enable/disable sync types (default: true)
- `HEALTH_CHECK_PORT` - Health endpoint port (default: 8080)

## Device Assignment Feature

The assignment module provides a web UI for bulk device assignment operations.

### Running the Assignment API
```bash
# Backend (FastAPI)
uv run uvicorn src.glp.assignment.app:app --reload --port 8000

# Frontend (React)
cd frontend && npm install && npm run dev
```

### Assignment Architecture (Clean Architecture)
```
src/glp/assignment/
├── domain/          # Entities (DeviceAssignment, SubscriptionOption) and Ports (interfaces)
├── use_cases/       # ProcessExcel, GetOptions, ApplyAssignments, SyncAndReport
├── adapters/        # PostgreSQL repos, Excel parser, DeviceManager wrapper
└── api/             # FastAPI router and Pydantic schemas
```

### Assignment Workflow
1. **Upload** - Drop Excel file with serials/MACs
2. **Review** - See devices found in DB and their current status
3. **Assign** - Select subscription (by device type), region (shows name, stores app UUID), tags
4. **Apply** - Intelligent patching (only patches what's missing)
5. **Report** - Resync with GreenLake and view summary

### Key Design Decisions
- Region = Application ID (1:1 mapping, user sees region name)
- Intelligent gap detection - only PATCH what's actually missing
- Batch operations - max 25 devices per API call
- New devices - POST to GreenLake first if not in DB

## Performance Profiling

The project includes comprehensive profiling tools for CPU, memory, and database analysis.

### Install Profiling Tools
```bash
uv sync --group profiling    # Install optional profiling dependencies
```

### Quick Benchmarks
```bash
# Mock data benchmark (no external dependencies)
python benchmark.py --mock

# Memory scaling analysis
python benchmark.py --memory

# CPU profiling with visualization
python benchmark.py --cpu --cpu-dump sync.prof
snakeviz sync.prof  # Opens interactive flamegraph

# All profiling modes
python benchmark.py --all --output report.json
```

### Profiling Utilities (`src/glp/profiling.py`)
```python
from src.glp.profiling import (
    profile_async,          # Decorator for async functions
    async_timer,            # Context manager for timing
    memory_profile,         # Context manager for memory tracking
    cpu_profile,            # Context manager for CPU profiling
    QueryProfiler,          # Database query analysis
    AsyncProfiler,          # Comprehensive async profiler
)

# Example: Profile an async function
@profile_async("fetch_devices", include_memory=True)
async def fetch_devices():
    ...

# Example: Time a code block
async with async_timer("db_operation") as t:
    await db_query()
print(f"Took {t.duration_ms:.2f}ms")
```

### Known Performance Bottlenecks
| Issue | Location | Impact |
|-------|----------|--------|
| Per-device transactions | `devices.py:117` | O(N) transactions for N devices |
| N+1 existence checks | `sync_to_postgres()` | SELECT before each INSERT/UPDATE |
| DELETE + INSERT for tags | `_sync_tags()` | Redundant when tags unchanged |

### Optimization Opportunities
- Use `INSERT ... ON CONFLICT` (UPSERT) instead of SELECT + INSERT/UPDATE
- Batch DELETE operations with `WHERE device_id IN (...)`
- Use `executemany()` for bulk inserts
- Increase transaction scope (e.g., 100 devices per transaction)

## Testing Notes

- Unit tests use mocks, no external services required
- Database tests require PostgreSQL (CI provides service container)
- Use pytest-asyncio for async tests
- Assignment tests: `uv run pytest tests/assignment/ -v`
