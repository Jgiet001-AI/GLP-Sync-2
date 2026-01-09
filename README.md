# HPE GreenLake Device & Subscription Sync

Sync device and subscription inventory from HPE GreenLake Platform to PostgreSQL.

## Features

- **OAuth2 Authentication** — Automatic token refresh with 5-minute buffer
- **Paginated Fetching** — Devices: 2,000/page, Subscriptions: 50/page
- **PostgreSQL Sync** — Upsert with JSONB storage + normalized tables
- **Full-Text Search** — Search devices by serial, name, model
- **Scheduler** — Automated sync at configurable intervals
- **Docker Ready** — Production-ready container with health checks

## Quick Start

### Option 1: Interactive Setup (Recommended)

```bash
git clone https://github.com/Jgiet001-AI/Demo_Comcast_GLP.git
cd Demo_Comcast_GLP

chmod +x setup.sh
./setup.sh
```

### Option 2: Docker Compose

```bash
# Create .env file with credentials
cp .env.example .env
# Edit .env with your GreenLake credentials

# Start services
docker compose up -d

# View logs
docker compose logs -f scheduler
```

### Option 3: Local Development

```bash
# Create virtual environment
uv sync

# Configure credentials
cp .env.example .env
# Edit .env

# Run sync
source .venv/bin/activate
python main.py
```

## CLI Usage

```bash
# DEFAULT: syncs both devices AND subscriptions
python main.py

# SYNC ONLY ONE
python main.py --devices              # Devices only
python main.py --subscriptions        # Subscriptions only

# UTILITIES
python main.py --expiring-days 90     # Show expiring subscriptions

# JSON EXPORT (no database needed)
python main.py --json-only            # Export to JSON files

# BACKUPS
python main.py --backup devices.json --subscription-backup subs.json
```

## MCP Server

A read-only MCP (Model Context Protocol) server for AI assistants to query the database.

### Starting the Server

```bash
# stdio transport (default, for Claude Desktop)
python server.py

# HTTP transport (for remote/web access)
python server.py --transport http --port 8000
```

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "greenlake-inventory": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/Demo_Comcast_GLP",
      "env": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/postgres"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
| ---- | ----------- |
| `search_devices` | Full-text search across devices |
| `get_device_by_serial` | Get device by serial number |
| `list_devices` | List devices with filters (type, region, state) |
| `get_device_subscriptions` | Get subscriptions linked to a device |
| `search_subscriptions` | Full-text search across subscriptions |
| `get_subscription_by_key` | Get subscription by key |
| `list_expiring_subscriptions` | Subscriptions expiring within N days |
| `get_device_summary` | Device counts by type and region |
| `get_subscription_summary` | Subscription counts by type/status |
| `run_query` | Execute read-only SQL queries |
| `ask_database` | Natural language database queries (uses sampling) |

### Available MCP Resources

| Resource URI | Description |
| ------------ | ----------- |
| `schema://devices` | Devices table schema with descriptions |
| `schema://subscriptions` | Subscriptions table schema |
| `schema://views` | Available database views documentation |
| `data://valid-values` | Valid values for categorical columns |
| `data://query-examples` | Example SQL queries |

### Available MCP Prompts

| Prompt | Description |
| ------ | ----------- |
| `analyze_device` | Analyze a specific device by serial |
| `analyze_expiring` | Subscription renewal analysis |
| `device_report` | Device inventory report by type |
| `subscription_utilization` | License utilization analysis |

## Docker Commands

```bash
# Start scheduler (syncs every hour by default)
docker compose up -d

# View logs
docker compose logs -f scheduler

# Health check
curl http://localhost:8080/

# Manual one-time sync
docker compose run --rm sync-once

# Check expiring subscriptions
docker compose run --rm check-expiring

# Stop services
docker compose down

# Stop and remove data
docker compose down -v
```

## Environment Variables

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `GLP_CLIENT_ID` | OAuth2 client ID | *required* |
| `GLP_CLIENT_SECRET` | OAuth2 client secret | *required* |
| `GLP_TOKEN_URL` | OAuth2 token endpoint | *required* |
| `GLP_BASE_URL` | GreenLake API base URL | `https://global.api.greenlake.hpe.com` |
| `DATABASE_URL` | PostgreSQL connection | *required for DB sync* |
| `SYNC_INTERVAL_MINUTES` | Minutes between syncs | `60` |
| `SYNC_DEVICES` | Enable device sync | `true` |
| `SYNC_SUBSCRIPTIONS` | Enable subscription sync | `true` |
| `SYNC_ON_STARTUP` | Sync immediately on start | `true` |
| `HEALTH_CHECK_PORT` | Health endpoint port | `8080` |

## Project Structure

```text
├── main.py                      # CLI entry point
├── server.py                    # FastMCP server (read-only database access)
├── scheduler.py                 # Automated sync scheduler
├── Dockerfile                   # Production container
├── docker-compose.yml           # Full stack deployment
├── setup.sh                     # Interactive setup wizard
├── src/glp/api/
│   ├── auth.py                  # OAuth2 token management
│   ├── client.py                # Generic HTTP client
│   ├── devices.py               # Device sync logic
│   └── subscriptions.py         # Subscription sync logic
├── db/
│   ├── schema.sql               # Device tables + LLM helper views
│   ├── subscriptions_schema.sql # Subscription tables
│   └── migrations/              # Schema migrations
└── tests/                       # 49 tests
```

## Database Schema

### Tables

| Table | Purpose |
| ----- | ------- |
| `devices` | Device inventory (28 columns) |
| `subscriptions` | Subscription inventory (20 columns) |
| `device_subscriptions` | Device-subscription relationships |
| `device_tags` | Device tags (normalized) |
| `subscription_tags` | Subscription tags (normalized) |
| `sync_history` | Sync audit log |

### Useful Views

- `active_subscriptions` — Only STARTED subscriptions
- `subscriptions_expiring_soon` — Expiring in 90 days
- `subscription_summary` — Count by type/status

## Testing

```bash
# Run all tests (49 tests)
uv run pytest tests/ -v

# Unit tests only (no database)
uv run pytest tests/test_auth.py tests/test_devices.py tests/test_subscriptions.py -v

# Database tests (requires PostgreSQL)
uv run pytest tests/test_database.py -v
```

## Architecture

```text
┌─────────────────┐     ┌──────────────┐     ┌────────────┐
│  GreenLake API  │────▶│   GLPClient  │────▶│ PostgreSQL │
└─────────────────┘     └──────────────┘     └────────────┘
         │                      │
         │              ┌───────┴───────┐
         │              │               │
         ▼              ▼               ▼
   TokenManager    DeviceSyncer  SubscriptionSyncer
```

## License

MIT
