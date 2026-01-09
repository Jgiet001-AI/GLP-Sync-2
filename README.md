# HPE GreenLake Device Sync

Sync device inventory from HPE GreenLake Platform to PostgreSQL.

## Features

- OAuth2 authentication with automatic token refresh
- Paginated API fetching (2000 devices/request)
- PostgreSQL upsert with JSONB storage
- Full-text search and tag-based queries
- JSON export mode (no database required)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/YOUR_USERNAME/Demo_Comcast_GLP.git
cd Demo_Comcast_GLP

# Create virtual environment
uv sync

# Configure credentials
cp .env.example .env
# Edit .env with your GreenLake API credentials

# Run sync
source .venv/bin/activate
python main.py                    # Full sync to database
python main.py --json-only        # Export to devices.json
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
├── main.py                 # CLI entry point
├── src/glp/
│   ├── api/
│   │   ├── auth.py         # OAuth2 token management
│   │   └── devices.py      # Device sync logic
│   └── constants.py        # API endpoints
├── db/
│   └── schema.sql          # PostgreSQL schema
└── tests/
    ├── test_auth.py        # Auth unit tests
    ├── test_devices.py     # Device sync tests
    └── test_database.py    # DB integration tests
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
