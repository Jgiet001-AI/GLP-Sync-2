"""FastAPI dependency injection for assignment API.

This module provides dependency injection functions that create
and return adapter instances for use in API endpoints.

Lifecycle Management:
- Database pool: Initialized at startup, shared across requests
- GLP Client: Initialized at startup, shared across requests
- Both are closed at application shutdown

This avoids creating new connections per request, which is
more efficient and respects rate limits.

Security:
- API key authentication required for all endpoints (except /health)
- Set API_KEY environment variable to enable authentication
- If API_KEY is not set, authentication is disabled (development mode)
"""

import logging
import os
import secrets
from typing import Optional

import asyncpg
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from ..adapters import (
    GLPDeviceManagerAdapter,
    OpenpyxlExcelParser,
    PostgresDeviceRepository,
    PostgresSubscriptionRepository,
    SimpleReportGenerator,
)
from ..domain.ports import (
    IDeviceManagerPort,
    IDeviceRepository,
    IExcelParser,
    IReportGenerator,
    ISubscriptionRepository,
    ISyncService,
)

logger = logging.getLogger(__name__)

# ========== API Key Authentication ==========

# API key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Expected API key from environment
_api_key: Optional[str] = None


def _get_api_key() -> Optional[str]:
    """Get the API key from environment (cached)."""
    global _api_key
    if _api_key is None:
        _api_key = os.getenv("API_KEY", "")
    return _api_key if _api_key else None


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> bool:
    """Verify the API key from the request header.

    Security model:
    - If DISABLE_AUTH=true (dev mode): authentication is disabled
    - Otherwise: API_KEY is required (fail-closed)

    Args:
        api_key: API key from X-API-Key header

    Returns:
        True if authenticated

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    # Check if auth is explicitly disabled (dev mode only)
    # Support both DISABLE_AUTH=true and REQUIRE_AUTH=false for backward compatibility
    if (
        os.getenv("DISABLE_AUTH", "").lower() == "true"
        or os.getenv("REQUIRE_AUTH", "").lower() == "false"
    ):
        logger.warning(
            "Authentication disabled (DISABLE_AUTH=true or REQUIRE_AUTH=false). "
            "Only use this in development!"
        )
        return True

    expected_key = _get_api_key()

    # Fail-closed: require API_KEY in production
    if not expected_key:
        logger.error(
            "API_KEY not set - rejecting request. "
            "Set API_KEY environment variable or DISABLE_AUTH=true for development."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: API_KEY not set",
        )

    # Require API key if configured
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return True


# ========== Global State ==========

# Global connection pool (initialized on startup)
_db_pool: Optional[asyncpg.Pool] = None

# Global GLP client and related objects (initialized on startup)
_glp_client = None
_token_manager = None
_device_manager = None
_device_syncer = None
_subscription_syncer = None


async def init_db_pool():
    """Initialize the database connection pool.

    Should be called on application startup.
    """
    global _db_pool

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    _db_pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
    )


async def init_glp_client():
    """Initialize the GLP client and related objects.

    Should be called on application startup after init_db_pool().
    """
    global _glp_client, _token_manager, _device_manager
    global _device_syncer, _subscription_syncer

    from ...api.auth import TokenManager
    from ...api.client import GLPClient
    from ...api.device_manager import DeviceManager
    from ...api.devices import DeviceSyncer
    from ...api.subscriptions import SubscriptionSyncer

    _token_manager = TokenManager()
    _glp_client = GLPClient(_token_manager)
    await _glp_client.__aenter__()

    _device_manager = DeviceManager(_glp_client)

    if _db_pool:
        _device_syncer = DeviceSyncer(_glp_client, _db_pool)
        _subscription_syncer = SubscriptionSyncer(_glp_client, _db_pool)

    logger.info("GLP client initialized")


async def close_db_pool():
    """Close the database connection pool.

    Should be called on application shutdown.
    """
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


async def close_glp_client():
    """Close the GLP client.

    Should be called on application shutdown.
    """
    global _glp_client, _token_manager, _device_manager
    global _device_syncer, _subscription_syncer

    if _glp_client:
        await _glp_client.__aexit__(None, None, None)
        _glp_client = None

    _token_manager = None
    _device_manager = None
    _device_syncer = None
    _subscription_syncer = None

    logger.info("GLP client closed")


def get_db_pool() -> asyncpg.Pool:
    """Get the database connection pool."""
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db_pool() first.")
    return _db_pool


# ========== Dependency Functions ==========


def get_excel_parser() -> IExcelParser:
    """Get an Excel parser instance."""
    return OpenpyxlExcelParser()


def get_device_repo() -> IDeviceRepository:
    """Get a device repository instance."""
    pool = get_db_pool()
    return PostgresDeviceRepository(pool)


def get_subscription_repo() -> ISubscriptionRepository:
    """Get a subscription repository instance."""
    pool = get_db_pool()
    return PostgresSubscriptionRepository(pool)


def get_device_manager() -> IDeviceManagerPort:
    """Get a device manager instance.

    Uses the shared GLPClient initialized at startup.
    This is more efficient than creating a new client per request.
    """
    if _device_manager is None:
        raise RuntimeError(
            "GLP client not initialized. Call init_glp_client() first."
        )
    return GLPDeviceManagerAdapter(_device_manager)


def get_sync_service() -> ISyncService:
    """Get a sync service instance.

    Uses the shared syncers initialized at startup.
    """
    from ..adapters import DeviceSyncerAdapter

    if _device_syncer is None or _subscription_syncer is None:
        raise RuntimeError(
            "GLP client not initialized. Call init_glp_client() first."
        )

    return DeviceSyncerAdapter(
        _device_syncer,
        _subscription_syncer,
        db_pool=_db_pool,
    )


def get_report_generator() -> IReportGenerator:
    """Get a report generator instance."""
    return SimpleReportGenerator()
