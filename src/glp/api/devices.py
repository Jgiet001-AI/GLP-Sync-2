#!/usr/bin/env python3
"""HPE GreenLake Device Inventory Synchronization.

This module provides high-performance device inventory synchronization from
the HPE GreenLake Platform API to PostgreSQL. Supports both database sync
and JSON export operations.

Architecture:
    DeviceSyncer now delegates to Clean Architecture use cases internally:
    - SyncDevicesUseCase: Orchestrates the sync workflow
    - PostgresDeviceRepository: Handles database operations
    - GLPDeviceAPI: Handles API operations
    - DeviceFieldMapper: Handles field transformations

    This maintains backward compatibility while enabling:
    - Unit testing without infrastructure
    - Reusable components
    - Clear separation of concerns

The separation of concerns means:
    - GLPClient handles: HTTP, auth, pagination, rate limiting, retries
    - DeviceSyncer handles: device schema, field extraction, related tables
    - Clean Architecture layers handle: testable, pluggable components

Database Tables:
    - devices: Main device inventory with all API fields
    - device_subscriptions: Many-to-many link to subscriptions
    - device_tags: Key-value tags per device

Example:
    async with GLPClient(token_manager) as client:
        syncer = DeviceSyncer(client=client, db_pool=pool)
        stats = await syncer.sync()

Author: HPE GreenLake Team
"""
import json
import logging
from datetime import datetime
from typing import Optional

from .client import DEVICES_PAGINATION, GLPClient
from .database import database_transaction
from .exceptions import (
    ConnectionPoolError,
    DatabaseError,
    ErrorCollector,
    GLPError,
    IntegrityError,
    PartialSyncError,
    SyncError,
)

# Clean Architecture imports
from ..sync.adapters import DeviceFieldMapper, GLPDeviceAPI, PostgresDeviceRepository
from ..sync.use_cases import SyncDevicesUseCase

logger = logging.getLogger(__name__)


class DeviceSyncer:
    """Device inventory synchronizer for GreenLake Platform.

    Fetches device inventory via GLPClient and upserts to PostgreSQL.
    Handles the full device schema including nested objects (application,
    location, dedicatedPlatformWorkspace) and related tables (subscriptions, tags).

    Attributes:
        client: GLPClient instance for API communication
        db_pool: asyncpg connection pool for database operations
    """

    # API endpoint for devices
    ENDPOINT = "/devices/v1/devices"

    def __init__(
        self,
        client: GLPClient,
        db_pool=None,
        *,
        use_clean_architecture: bool = True,
        use_streaming: bool = False,
    ):
        """Initialize DeviceSyncer.

        Args:
            client: Configured GLPClient instance
            db_pool: asyncpg connection pool (optional for JSON-only mode)
            use_clean_architecture: If True, use the new Clean Architecture
                                   use case internally (default: True)
            use_streaming: If True, use streaming mode for memory-efficient
                          sync of large datasets (100K+ devices). Processes
                          page by page instead of loading all into memory.
        """
        self.client = client
        self.db_pool = db_pool
        self._use_clean_architecture = use_clean_architecture
        self._use_streaming = use_streaming

        # Create use case with adapters if db_pool is provided
        self._use_case: SyncDevicesUseCase | None = None
        if db_pool and use_clean_architecture:
            self._use_case = SyncDevicesUseCase(
                device_api=GLPDeviceAPI(client),
                device_repo=PostgresDeviceRepository(db_pool),
                field_mapper=DeviceFieldMapper(),
            )

    # ----------------------------------------
    # Fetching
    # ----------------------------------------

    async def fetch_all_devices(self) -> list[dict]:
        """Fetch all devices from GreenLake API.

        Uses DEVICES_PAGINATION config:
        - page_size: 2000 (API maximum)
        - delay: 0.5s between pages (respects 160 req/min limit)

        Returns:
            List of device dictionaries from the API.
        """
        return await self.client.fetch_all(
            self.ENDPOINT,
            config=DEVICES_PAGINATION,
        )

    async def fetch_devices_generator(self):
        """Yield devices page by page (memory efficient).

        Use this for very large datasets where you want to process
        devices as they arrive rather than loading all into memory.

        Yields:
            Lists of device dictionaries, one page at a time.
        """
        async for page in self.client.paginate(
            self.ENDPOINT,
            config=DEVICES_PAGINATION,
        ):
            yield page

    # ----------------------------------------
    # Database Operations (Optimized with Bulk Operations)
    # ----------------------------------------

    async def sync_to_postgres(self, devices: list[dict]) -> dict:
        """Upsert devices to PostgreSQL using optimized bulk operations.

        Performance optimizations:
        1. Uses UPSERT (INSERT ON CONFLICT) - eliminates N SELECT queries
        2. Bulk DELETE with ANY() - single query for all device IDs
        3. executemany() for bulk inserts - batched subscriptions/tags

        This reduces ~47,000 queries to ~5 queries for 11,000 devices.

        Args:
            devices: List of device dictionaries from API

        Returns:
            Dict with sync statistics

        Raises:
            ConnectionPoolError: If database pool is not available
            PartialSyncError: If sync fails
        """
        if self.db_pool is None:
            raise ConnectionPoolError(
                "Database connection pool is required for sync"
            )

        if not devices:
            return {
                "total": 0,
                "upserted": 0,
                "errors": 0,
                "synced_at": datetime.utcnow().isoformat(),
            }

        error_collector = ErrorCollector()
        upserted = 0

        try:
            async with database_transaction(self.db_pool) as conn:
                # Step 1: Bulk UPSERT all devices
                device_records = self._prepare_device_records(devices)
                upserted = await self._bulk_upsert_devices(conn, device_records)

                # Step 2: Collect all device IDs for bulk operations
                device_ids = [d["id"] for d in devices]

                # Step 3: Bulk DELETE existing subscriptions and tags
                await self._bulk_delete_related(conn, device_ids)

                # Step 4: Bulk INSERT subscriptions
                subscription_records = self._prepare_subscription_records(devices)
                if subscription_records:
                    await self._bulk_insert_subscriptions(conn, subscription_records)

                # Step 5: Bulk INSERT tags
                tag_records = self._prepare_tag_records(devices)
                if tag_records:
                    await self._bulk_insert_tags(conn, tag_records)

        except IntegrityError as e:
            logger.error(f"Integrity error during bulk sync: {e}")
            error_collector.add(e, context={"operation": "bulk_upsert"})

        except DatabaseError as e:
            logger.error(f"Database error during bulk sync: {e}")
            error_collector.add(e, context={"operation": "bulk_upsert"})

        except Exception as e:
            logger.error(f"Unexpected error during bulk sync: {e}")
            error_collector.add(
                SyncError(f"Bulk sync failed: {e}", cause=e),
                context={"operation": "bulk_upsert"}
            )

        stats = {
            "total": len(devices),
            "upserted": upserted,
            "errors": error_collector.count(),
            "synced_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Device sync complete: {upserted} upserted, "
            f"{error_collector.count()} errors"
        )

        if error_collector.has_errors():
            raise PartialSyncError(
                f"Device sync completed with {error_collector.count()} errors",
                succeeded=upserted,
                failed=error_collector.count(),
                errors=[e for e, _ in error_collector.get_errors()],
                details=stats,
            )

        return stats

    def _prepare_device_records(self, devices: list[dict]) -> list[tuple]:
        """Prepare device records for bulk insert.

        Extracts and transforms all fields from API format to database format.

        Args:
            devices: List of device dictionaries from API

        Returns:
            List of tuples ready for executemany()
        """
        records = []
        for device in devices:
            created_at = self._parse_timestamp(device.get("createdAt"))
            updated_at = self._parse_timestamp(device.get("updatedAt"))

            application = device.get("application") or {}
            location = device.get("location") or {}
            dedicated = device.get("dedicatedPlatformWorkspace") or {}

            records.append((
                device["id"],
                device.get("macAddress"),
                device.get("serialNumber"),
                device.get("partNumber"),
                device.get("deviceType"),
                device.get("model"),
                device.get("region"),
                device.get("archived", False),
                device.get("deviceName"),
                device.get("secondaryName"),
                device.get("assignedState"),
                device.get("type"),  # resource_type
                device.get("tenantWorkspaceId"),
                application.get("id"),
                application.get("resourceUri"),
                dedicated.get("id"),
                location.get("id"),
                location.get("locationName"),
                location.get("city"),
                location.get("state"),
                location.get("country"),
                location.get("postalCode"),
                location.get("streetAddress"),
                location.get("latitude"),
                location.get("longitude"),
                location.get("locationSource"),
                created_at,
                updated_at,
                json.dumps(device),
            ))
        return records

    async def _bulk_upsert_devices(self, conn, records: list[tuple]) -> int:
        """Bulk upsert devices using INSERT ON CONFLICT.

        Args:
            conn: Database connection
            records: List of device record tuples

        Returns:
            Number of rows affected
        """
        # Use executemany with UPSERT query
        await conn.executemany('''
            INSERT INTO devices (
                id, mac_address, serial_number, part_number,
                device_type, model, region, archived,
                device_name, secondary_name, assigned_state,
                resource_type, tenant_workspace_id,
                application_id, application_resource_uri,
                dedicated_platform_id,
                location_id, location_name, location_city, location_state,
                location_country, location_postal_code, location_street_address,
                location_latitude, location_longitude, location_source,
                created_at, updated_at, raw_data, synced_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29::jsonb, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                mac_address = EXCLUDED.mac_address,
                serial_number = EXCLUDED.serial_number,
                part_number = EXCLUDED.part_number,
                device_type = EXCLUDED.device_type,
                model = EXCLUDED.model,
                region = EXCLUDED.region,
                archived = EXCLUDED.archived,
                device_name = EXCLUDED.device_name,
                secondary_name = EXCLUDED.secondary_name,
                assigned_state = EXCLUDED.assigned_state,
                resource_type = EXCLUDED.resource_type,
                tenant_workspace_id = EXCLUDED.tenant_workspace_id,
                application_id = EXCLUDED.application_id,
                application_resource_uri = EXCLUDED.application_resource_uri,
                dedicated_platform_id = EXCLUDED.dedicated_platform_id,
                location_id = EXCLUDED.location_id,
                location_name = EXCLUDED.location_name,
                location_city = EXCLUDED.location_city,
                location_state = EXCLUDED.location_state,
                location_country = EXCLUDED.location_country,
                location_postal_code = EXCLUDED.location_postal_code,
                location_street_address = EXCLUDED.location_street_address,
                location_latitude = EXCLUDED.location_latitude,
                location_longitude = EXCLUDED.location_longitude,
                location_source = EXCLUDED.location_source,
                updated_at = EXCLUDED.updated_at,
                raw_data = EXCLUDED.raw_data,
                synced_at = NOW()
        ''', records)

        return len(records)

    async def _bulk_delete_related(self, conn, device_ids: list[str]) -> None:
        """Bulk delete subscriptions and tags for all devices.

        Uses ANY() with array for efficient bulk deletion.

        Args:
            conn: Database connection
            device_ids: List of device UUIDs
        """
        # Delete all subscriptions for these devices in one query
        await conn.execute(
            'DELETE FROM device_subscriptions WHERE device_id = ANY($1)',
            device_ids
        )

        # Delete all tags for these devices in one query
        await conn.execute(
            'DELETE FROM device_tags WHERE device_id = ANY($1)',
            device_ids
        )

    def _prepare_subscription_records(self, devices: list[dict]) -> list[tuple]:
        """Prepare subscription records for bulk insert.

        Args:
            devices: List of device dictionaries

        Returns:
            List of (device_id, subscription_id, resource_uri) tuples
        """
        records = []
        for device in devices:
            device_id = device["id"]
            subscriptions = device.get("subscription") or []
            for sub in subscriptions:
                if sub.get("id"):
                    records.append((
                        device_id,
                        sub.get("id"),
                        sub.get("resourceUri"),
                    ))
        return records

    async def _bulk_insert_subscriptions(self, conn, records: list[tuple]) -> None:
        """Bulk insert device subscriptions.

        Args:
            conn: Database connection
            records: List of subscription record tuples
        """
        await conn.executemany('''
            INSERT INTO device_subscriptions (device_id, subscription_id, resource_uri)
            VALUES ($1, $2, $3)
        ''', records)

    def _prepare_tag_records(self, devices: list[dict]) -> list[tuple]:
        """Prepare tag records for bulk insert.

        Args:
            devices: List of device dictionaries

        Returns:
            List of (device_id, tag_key, tag_value) tuples
        """
        records = []
        for device in devices:
            device_id = device["id"]
            tags = device.get("tags") or {}
            for key, value in tags.items():
                records.append((device_id, key, value))
        return records

    async def _bulk_insert_tags(self, conn, records: list[tuple]) -> None:
        """Bulk insert device tags.

        Args:
            conn: Database connection
            records: List of tag record tuples
        """
        await conn.executemany('''
            INSERT INTO device_tags (device_id, tag_key, tag_value)
            VALUES ($1, $2, $3)
        ''', records)

    @staticmethod
    def _parse_timestamp(iso_string: Optional[str]) -> Optional[datetime]:
        """Parse ISO timestamp string to datetime.

        Handles the 'Z' suffix that Python's fromisoformat doesn't like.
        """
        if not iso_string:
            return None
        return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))

    # ----------------------------------------
    # High-Level Operations
    # ----------------------------------------

    async def sync(self) -> dict:
        """Full sync: fetch all devices and upsert to database.

        When use_clean_architecture=True (default), delegates to SyncDevicesUseCase.
        Otherwise, uses the legacy implementation for backward compatibility.

        When use_streaming=True, uses memory-efficient streaming mode that
        processes devices page by page. Recommended for large inventories.

        Returns:
            Sync statistics dictionary

        Raises:
            GLPError: If API fetch fails
            PartialSyncError: If some devices failed to sync
        """
        # Use Clean Architecture use case if available
        if self._use_case:
            if self._use_streaming:
                logger.info("Using Clean Architecture use case for sync (streaming mode)")
                result = await self._use_case.execute_streaming()
            else:
                logger.info("Using Clean Architecture use case for sync")
                result = await self._use_case.execute()

            # Convert SyncResult to backward-compatible dict format
            stats = result.to_dict()

            # Raise PartialSyncError if there were errors (for backward compatibility)
            if not result.success and result.error_details:
                raise PartialSyncError(
                    f"Device sync completed with {result.errors} errors",
                    succeeded=result.upserted,
                    failed=result.errors,
                    errors=result.error_details,
                    details=stats,
                )

            return stats

        # Legacy implementation (when use_clean_architecture=False or no db_pool)
        logger.info(f"Starting device sync at {datetime.utcnow().isoformat()}")

        try:
            devices = await self.fetch_all_devices()
        except GLPError:
            logger.error("Failed to fetch devices from API")
            raise

        if self.db_pool:
            try:
                stats = await self.sync_to_postgres(devices)
            except PartialSyncError as e:
                # PartialSyncError contains stats, log and return them
                logger.warning(f"Partial sync: {e.succeeded} succeeded, {e.failed} failed")
                return e.details
        else:
            stats = {
                "total": len(devices),
                "note": "No database configured, fetch only",
            }

        return stats

    async def fetch_and_save_json(self, filepath: str = "devices.json") -> int:
        """Fetch all devices and save to JSON file.

        Useful for testing without database or for creating backups.

        Args:
            filepath: Output file path

        Returns:
            Number of devices saved

        Raises:
            GLPError: If API fetch fails
            IOError: If file cannot be written
        """
        import aiofiles

        devices = await self.fetch_all_devices()

        async with aiofiles.open(filepath, "w") as f:
            await f.write(json.dumps(devices, indent=2))

        logger.info(f"Saved {len(devices):,} devices to {filepath}")
        return len(devices)


# ============================================
# Backward Compatibility Layer
# ============================================

# Import APIError from exceptions for backward compatibility
from .exceptions import APIError  # noqa: F401, E402

# ============================================
# Standalone Test
# ============================================

if __name__ == "__main__":
    import asyncio

    from .auth import TokenManager
    from .client import GLPClient

    async def main():
        token_manager = TokenManager()

        async with GLPClient(token_manager) as client:
            syncer = DeviceSyncer(client=client)
            await syncer.fetch_and_save_json("devices_backup.json")

    asyncio.run(main())
