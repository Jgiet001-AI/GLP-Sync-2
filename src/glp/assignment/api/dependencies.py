"""FastAPI dependency injection for assignment API.

This module provides dependency injection functions that create
and return adapter instances for use in API endpoints.
"""

import os
from typing import Optional

import asyncpg

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

# Global connection pool (initialized on startup)
_db_pool: Optional[asyncpg.Pool] = None


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


async def close_db_pool():
    """Close the database connection pool.

    Should be called on application shutdown.
    """
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


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


async def get_device_manager() -> IDeviceManagerPort:
    """Get a device manager instance.

    This requires the GLP client to be configured with authentication.
    """
    from ...api.auth import TokenManager
    from ...api.client import GLPClient
    from ...api.device_manager import DeviceManager

    # Create token manager and client
    token_manager = TokenManager()

    # Note: We need to use the client as an async context manager
    # In a real application, you might want to manage the client lifecycle differently
    async with GLPClient(token_manager) as client:
        device_manager = DeviceManager(client)
        yield GLPDeviceManagerAdapter(device_manager)


async def get_sync_service() -> ISyncService:
    """Get a sync service instance."""
    from ...api.auth import TokenManager
    from ...api.client import GLPClient
    from ...api.devices import DeviceSyncer
    from ...api.subscriptions import SubscriptionSyncer
    from ..adapters import DeviceSyncerAdapter

    pool = get_db_pool()
    token_manager = TokenManager()

    async with GLPClient(token_manager) as client:
        device_syncer = DeviceSyncer(client, pool)
        subscription_syncer = SubscriptionSyncer(client, pool)
        yield DeviceSyncerAdapter(device_syncer, subscription_syncer, db_pool=pool)


def get_report_generator() -> IReportGenerator:
    """Get a report generator instance."""
    return SimpleReportGenerator()
