#!/usr/bin/env python3
"""Aruba Central Device Inventory Synchronization.

This module provides device inventory synchronization from the Aruba Central
API to PostgreSQL. It correlates devices with GreenLake using serial_number
as the join key.

Architecture:
    ArubaCentralSyncer fetches devices from Aruba Central and:
    1. Correlates with existing GreenLake devices by serial_number
    2. Updates Central-specific columns (prefixed with central_)
    3. Sets source tracking flags (in_central, last_seen_central)
    4. Creates new records for devices not in GreenLake

Key Design Decisions:
    - Serial number is the correlation key between platforms
    - Platform-specific columns prevent data overwrites
    - Streaming writes process page-by-page (memory efficient)
    - Serial numbers are normalized (stripped, uppercased, NULL filtered)

Database Columns Updated:
    - central_id, central_device_name, central_device_type
    - central_status, central_software_version, central_ipv4
    - central_site_id, central_site_name, central_device_group_*
    - central_deployment, central_device_role, central_device_function
    - central_is_provisioned, central_tier
    - in_central, last_seen_central, central_raw_data

Example:
    async with ArubaCentralClient(token_manager) as client:
        syncer = ArubaCentralSyncer(client=client, db_pool=pool)
        stats = await syncer.sync()

Author: HPE GreenLake Team
"""
import json
import logging
from datetime import datetime
from typing import Optional

import asyncpg

from .aruba_client import ARUBA_DEVICES_PAGINATION, ArubaCentralClient
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

logger = logging.getLogger(__name__)


class ArubaCentralSyncer:
    """Device inventory synchronizer for Aruba Central.

    Fetches device inventory from Aruba Central and merges into the
    devices table using serial_number as the correlation key.

    Attributes:
        client: ArubaCentralClient instance for API communication
        db_pool: asyncpg connection pool for database operations
    """

    # API endpoint for device inventory
    ENDPOINT = "/network-monitoring/v1alpha1/device-inventory"

    def __init__(
        self,
        client: ArubaCentralClient,
        db_pool=None,
    ):
        """Initialize ArubaCentralSyncer.

        Args:
            client: Configured ArubaCentralClient instance
            db_pool: asyncpg connection pool (required for sync)
        """
        self.client = client
        self.db_pool = db_pool

    # ----------------------------------------
    # Field Mapping and Normalization
    # ----------------------------------------

    @staticmethod
    def normalize_serial(serial: Optional[str]) -> Optional[str]:
        """Normalize serial number for consistent matching.

        Args:
            serial: Raw serial number from API

        Returns:
            Normalized serial (stripped, uppercased) or None if invalid
        """
        if not serial:
            return None
        serial = str(serial).strip().upper()
        if not serial or serial in ("NULL", "N/A", "NONE", ""):
            return None
        return serial

    @staticmethod
    def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
        """Parse ISO timestamp from API response.

        Args:
            value: ISO timestamp string or None

        Returns:
            datetime object or None if parsing fails
        """
        if not value:
            return None
        try:
            # Handle various ISO formats
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def _extract_central_fields(self, device: dict) -> dict:
        """Extract and transform ALL fields from Aruba Central API response.

        Args:
            device: Raw device dict from Central API

        Returns:
            Dict with database column names and values
        """
        # Handle isProvisioned - can be bool, string "YES"/"NO", or truthy value
        is_provisioned_raw = device.get("isProvisioned")
        if isinstance(is_provisioned_raw, bool):
            is_provisioned = is_provisioned_raw
        elif isinstance(is_provisioned_raw, str):
            is_provisioned = is_provisioned_raw.upper() in ("YES", "TRUE", "1")
        else:
            is_provisioned = bool(is_provisioned_raw)

        # Parse uptime (can be int or string)
        uptime_raw = device.get("uptimeInMillis")
        uptime_millis = None
        if uptime_raw is not None:
            try:
                uptime_millis = int(uptime_raw)
            except (ValueError, TypeError):
                pass

        return {
            # Core identity
            "central_id": device.get("id"),
            "central_device_name": device.get("deviceName"),
            "central_device_type": device.get("deviceType"),  # ACCESS_POINT, SWITCH, GATEWAY
            # Hardware info
            "central_model": device.get("model"),
            "central_part_number": device.get("partNumber"),
            # Status and connectivity
            "central_status": device.get("status"),  # ONLINE, OFFLINE
            "central_software_version": device.get("softwareVersion"),
            "central_ipv4": device.get("ipv4"),
            "central_ipv6": device.get("ipv6"),
            "central_uptime_millis": uptime_millis,
            "central_last_seen_at": self._parse_timestamp(device.get("lastSeenAt")),
            # Deployment info
            "central_deployment": device.get("deployment"),
            "central_device_role": device.get("role"),
            "central_device_function": device.get("deviceFunction") or device.get("persona"),
            "central_is_provisioned": is_provisioned,
            "central_tier": device.get("tier"),
            # Location info
            "central_site_id": device.get("siteId"),
            "central_site_name": device.get("siteName"),
            "central_building_id": device.get("buildingId"),
            "central_floor_id": device.get("floorId"),
            # Group info
            "central_device_group_id": device.get("deviceGroupId"),
            "central_device_group_name": device.get("deviceGroupName"),
            "central_scope_id": device.get("scopeId"),
            "central_stack_id": device.get("stackId"),
            "central_cluster_name": device.get("clusterName"),
            # Config info
            "central_config_status": device.get("configStatus"),
            "central_config_last_modified_at": self._parse_timestamp(device.get("configLastModifiedAt")),
        }

    def _prepare_upsert_record(self, device: dict) -> Optional[tuple]:
        """Prepare a device record for database upsert.

        Args:
            device: Raw device dict from Central API

        Returns:
            Tuple of values for the upsert query, or None if invalid
        """
        serial = self.normalize_serial(device.get("serialNumber"))
        if not serial:
            logger.warning(f"Skipping device with invalid serial: {device.get('id')}")
            return None

        fields = self._extract_central_fields(device)

        return (
            serial,  # $1 - serial_number (correlation key)
            device.get("macAddress"),  # $2 - mac_address
            fields["central_id"],  # $3
            fields["central_device_name"],  # $4
            fields["central_device_type"],  # $5
            fields["central_model"],  # $6 - NEW
            fields["central_part_number"],  # $7 - NEW
            fields["central_status"],  # $8
            fields["central_software_version"],  # $9
            fields["central_ipv4"],  # $10
            fields["central_ipv6"],  # $11 - NEW
            fields["central_uptime_millis"],  # $12 - NEW
            fields["central_last_seen_at"],  # $13 - NEW
            fields["central_deployment"],  # $14
            fields["central_device_role"],  # $15
            fields["central_device_function"],  # $16
            fields["central_is_provisioned"],  # $17
            fields["central_tier"],  # $18
            fields["central_site_id"],  # $19
            fields["central_site_name"],  # $20
            fields["central_building_id"],  # $21 - NEW
            fields["central_floor_id"],  # $22 - NEW
            fields["central_device_group_id"],  # $23
            fields["central_device_group_name"],  # $24
            fields["central_scope_id"],  # $25
            fields["central_stack_id"],  # $26
            fields["central_cluster_name"],  # $27 - NEW
            fields["central_config_status"],  # $28 - NEW
            fields["central_config_last_modified_at"],  # $29 - NEW
            json.dumps(device),  # $30 - central_raw_data
        )

    # ----------------------------------------
    # Database Operations
    # ----------------------------------------

    async def _upsert_page(self, conn, devices: list[dict]) -> tuple[int, int, list[str]]:
        """Upsert a page of devices to the database.

        Uses UPSERT (INSERT ON CONFLICT) with serial_number as the key.
        - Existing devices: Update Central-specific columns only
        - New devices: Insert with Central data, mark in_greenlake=FALSE

        Args:
            conn: Database connection
            devices: List of device dicts from Central API

        Returns:
            Tuple of (upserted_count, skipped_count, list of serial numbers synced)
        """
        records = []
        serials_synced = []

        for device in devices:
            record = self._prepare_upsert_record(device)
            if record:
                records.append(record)
                serials_synced.append(record[0])  # serial_number

        if not records:
            return 0, len(devices), []

        # UPDATE existing GreenLake devices with Central data
        # This enriches existing records - does NOT create new ones
        # Devices must already exist in GreenLake (synced from GLP API)
        await conn.executemany('''
            UPDATE devices SET
                mac_address = COALESCE(mac_address, $2),
                central_id = $3,
                central_device_name = $4,
                central_device_type = $5,
                central_model = $6,
                central_part_number = $7,
                central_status = $8,
                central_software_version = $9,
                central_ipv4 = $10,
                central_ipv6 = $11,
                central_uptime_millis = $12,
                central_last_seen_at = $13,
                central_deployment = $14,
                central_device_role = $15,
                central_device_function = $16,
                central_is_provisioned = $17,
                central_tier = $18,
                central_site_id = $19,
                central_site_name = $20,
                central_building_id = $21,
                central_floor_id = $22,
                central_device_group_id = $23,
                central_device_group_name = $24,
                central_scope_id = $25,
                central_stack_id = $26,
                central_cluster_name = $27,
                central_config_status = $28,
                central_config_last_modified_at = $29,
                central_raw_data = $30::jsonb,
                in_central = TRUE,
                last_seen_central = NOW(),
                synced_at = NOW()
            WHERE serial_number = $1
        ''', records)

        skipped = len(devices) - len(records)
        return len(records), skipped, serials_synced

    async def _mark_removed_devices(self, conn, serials_seen: list[str]) -> int:
        """Mark devices no longer in Central as removed.

        Sets in_central = FALSE for devices that weren't in this sync.

        Args:
            conn: Database connection
            serials_seen: List of serial numbers seen in this sync

        Returns:
            Number of devices marked as removed
        """
        if not serials_seen:
            return 0

        # Use execute() and check rowcount - RETURNING COUNT(*) is invalid SQL
        result = await conn.execute('''
            UPDATE devices
            SET in_central = FALSE
            WHERE in_central = TRUE
              AND serial_number IS NOT NULL
              AND serial_number != ''
              AND serial_number != ALL($1::text[])
        ''', serials_seen)

        # asyncpg returns "UPDATE N" where N is the row count
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError, AttributeError):
            return 0

    async def sync_to_postgres_streaming(self) -> dict:
        """Sync devices from Aruba Central using streaming writes.

        Processes devices page-by-page to minimize memory usage.
        After sync, marks devices not seen in this run as removed from Central.

        Returns:
            Dict with sync statistics

        Raises:
            ConnectionPoolError: If database pool is not available
            PartialSyncError: If sync completes with errors
        """
        if self.db_pool is None:
            raise ConnectionPoolError(
                "Database connection pool is required for Aruba Central sync"
            )

        error_collector = ErrorCollector()
        total_upserted = 0
        total_skipped = 0
        total_pages = 0
        all_serials_seen: list[str] = []

        try:
            async with database_transaction(self.db_pool) as conn:
                # Stream pages from API and write to DB
                async for page in self.client.paginate(
                    self.ENDPOINT,
                    config=ARUBA_DEVICES_PAGINATION,
                ):
                    try:
                        upserted, skipped, serials = await self._upsert_page(conn, page)
                        total_upserted += upserted
                        total_skipped += skipped
                        total_pages += 1
                        all_serials_seen.extend(serials)

                        logger.debug(
                            f"Page {total_pages}: upserted {upserted}, skipped {skipped}"
                        )

                    except asyncpg.IntegrityConstraintViolationError as e:
                        # Constraint violation (duplicate key, foreign key, etc.)
                        logger.warning(f"Integrity error on page {total_pages}: {e}")
                        error_collector.add(
                            IntegrityError(str(e), cause=e),
                            context={"page": total_pages}
                        )

                    except asyncpg.PostgresError as e:
                        # Other PostgreSQL errors
                        logger.error(f"Database error on page {total_pages}: {e}")
                        error_collector.add(
                            DatabaseError(str(e), cause=e),
                            context={"page": total_pages}
                        )

                # After all pages, mark devices removed from Central
                removed_count = await self._mark_removed_devices(conn, all_serials_seen)
                if removed_count > 0:
                    logger.info(f"Marked {removed_count} devices as removed from Central")

        except GLPError as e:
            logger.error(f"API error during Aruba Central sync: {e}")
            error_collector.add(e, context={"operation": "fetch"})

        except Exception as e:
            logger.error(f"Unexpected error during Aruba Central sync: {e}")
            error_collector.add(
                SyncError(f"Aruba Central sync failed: {e}", cause=e),
                context={"operation": "sync"}
            )

        stats = {
            "source": "aruba_central",
            "total_pages": total_pages,
            "total_upserted": total_upserted,
            "total_skipped": total_skipped,
            "unique_serials": len(set(all_serials_seen)),
            "errors": error_collector.count(),
            "synced_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Aruba Central sync complete: {total_upserted} devices upserted, "
            f"{total_skipped} skipped, {error_collector.count()} errors"
        )

        if error_collector.has_errors():
            raise PartialSyncError(
                f"Aruba Central sync completed with {error_collector.count()} errors",
                succeeded=total_upserted,
                failed=error_collector.count(),
                errors=[e for e, _ in error_collector.get_errors()],
                details=stats,
            )

        return stats

    # ----------------------------------------
    # High-Level Operations
    # ----------------------------------------

    async def sync(self) -> dict:
        """Full sync: fetch all devices from Aruba Central and merge to database.

        This is the main entry point for syncing Aruba Central devices.

        Returns:
            Sync statistics dictionary

        Raises:
            GLPError: If API fetch fails
            PartialSyncError: If some devices failed to sync
        """
        logger.info(f"Starting Aruba Central device sync at {datetime.utcnow().isoformat()}")
        return await self.sync_to_postgres_streaming()

    async def fetch_all_devices(self) -> list[dict]:
        """Fetch all devices from Aruba Central API (for JSON export).

        Use sync() for database operations - this method loads all devices
        into memory and should only be used for exports.

        Returns:
            List of device dictionaries from the API.
        """
        return await self.client.fetch_all(
            self.ENDPOINT,
            config=ARUBA_DEVICES_PAGINATION,
        )

    async def fetch_and_save_json(self, filepath: str = "central_devices.json") -> int:
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
        devices = await self.fetch_all_devices()

        with open(filepath, "w") as f:
            json.dump(devices, f, indent=2)

        logger.info(f"Saved {len(devices):,} Aruba Central devices to {filepath}")
        return len(devices)


# ============================================
# Standalone Test
# ============================================

if __name__ == "__main__":
    import asyncio

    from .aruba_auth import ArubaTokenManager
    from .aruba_client import ArubaCentralClient

    async def main():
        token_manager = ArubaTokenManager()

        async with ArubaCentralClient(token_manager) as client:
            syncer = ArubaCentralSyncer(client=client)
            await syncer.fetch_and_save_json("central_devices_backup.json")

    asyncio.run(main())
