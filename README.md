# HPE GreenLake Device & Subscription Sync

Sync device and subscription inventory from HPE GreenLake Platform to PostgreSQL.

## Features

- OAuth2 authentication with automatic token refresh
- Paginated API fetching (devices: 2000/request, subscriptions: 50/request)
- PostgreSQL upsert with JSONB storage + normalized tables
- Full-text search and tag-based queries
- Subscription expiration monitoring
- JSON export mode (no database required)

## CLI Usage

```bash
# DEVICES (default)
python main.py                        # Sync devices to database
python main.py --devices              # Explicit: sync devices only

# SUBSCRIPTIONS
python main.py --subscriptions        # Sync subscriptions only
python main.py --expiring-days 90     # Show subscriptions expiring in 90 days

# BOTH
python main.py --all                  # Sync devices AND subscriptions

# JSON EXPORT (no database needed)
python main.py --json-only            # Export devices to devices.json
python main.py --subscriptions --json-only  # Export subscriptions to subscriptions.json

# BACKUPS (sync to DB + save JSON)
python main.py --backup devices_backup.json
python main.py --subscriptions --subscription-backup subs_backup.json
```

> **Note**: By default (no flags), only devices are synced. Use `--all` to sync both resources.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/Jgiet001-AI/Demo_Comcast_GLP.git
cd Demo_Comcast_GLP

# Create virtual environment
uv sync

# Configure credentials
cp .env.example .env
# Edit .env with your GreenLake API credentials

# Run sync
source .venv/bin/activate
python main.py --all                  # Full sync (devices + subscriptions)
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GLP_CLIENT_ID` | OAuth2 client ID |
| `GLP_CLIENT_SECRET` | OAuth2 client secret |
| `GLP_TOKEN_URL` | OAuth2 token endpoint |
| `GLP_BASE_URL` | GreenLake API base URL |
| `DATABASE_URL` | PostgreSQL connection string |

## Project Structure

```
├── main.py                      # CLI entry point
├── src/glp/api/
│   ├── auth.py                  # OAuth2 token management
│   ├── client.py                # Generic HTTP client with pagination
│   ├── devices.py               # Device sync logic
│   └── subscriptions.py         # Subscription sync logic
├── db/
│   ├── schema.sql               # Device tables
│   ├── subscriptions_schema.sql # Subscription tables
│   └── migrations/              # Schema migrations
└── tests/
    ├── test_auth.py             # Auth unit tests
    ├── test_devices.py          # Device sync tests
    └── test_database.py         # DB integration tests
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Unit tests only (no database)
python -m pytest tests/test_auth.py tests/test_devices.py -v

# Database tests (requires PostgreSQL)
python -m pytest tests/test_database.py -v
```

### Test Isolation

Database tests use transaction rollback for complete isolation:

- Each test runs in a transaction that is rolled back after completion
- No test data persists in the database
- Safe to run against development databases

## CI/CD

GitHub Actions workflow includes:

- **Unit tests**: Run without database
- **Integration tests**: PostgreSQL 16 service container
- **Lint**: Ruff check (non-blocking)

## License

MIT
