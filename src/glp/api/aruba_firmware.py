#!/usr/bin/env python3
"""Aruba Central Firmware Details Synchronization.

This module provides synchronization of device firmware details from the
Aruba Central API to PostgreSQL, enriching existing device records.

Architecture:
    ArubaFirmwareSyncer fetches firmware details and:
    1. Fetches all firmware details with pagination
    2. Updates existing devices by serial_number
    3. Clears stale firmware data (devices not in response)

Key Design Decisions:
    - Only enriches existing devices (does not create new ones)
    - Uses serial_number as the correlation key
    - Tracks firmware_synced_at for stale data detection
    - Clears firmware columns when device not in API response

Database Columns Updated:
    - firmware_version, firmware_recommended_version
    - firmware_upgrade_status, firmware_classification
    - firmware_last_upgraded_at, firmware_synced_at

Example:
    async with ArubaCentralClient(token_manager) as client:
        syncer = ArubaFirmwareSyncer(client=client, db_pool=pool)
        stats = await syncer.sync()

Author: HPE GreenLake Team
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from .aruba_client import ArubaCentralClient, ArubaPaginationConfig
from .database import database_transaction
from .exceptions import (
    ConnectionPoolError,
    DatabaseError,
    ErrorCollector,
    GLPError,
    PartialSyncError,
    SyncError,
)

logger = logging.getLogger(__name__)


# Pagination config for firmware API (max 100 per page)
FIRMWARE_PAGINATION = ArubaPaginationConfig(
    page_size=100,
    delay_between_pages=0.3,
    max_pages=None,
)


class ArubaFirmwareSyncer:
    """Firmware details synchronizer for Aruba Central.

    Fetches firmware details from Aruba Central and enriches existing
    device records in the database.

    Attributes:
        client: ArubaCentralClient instance for API communication
        db_pool: asyncpg connection pool for database operations
    """

    # API endpoint for firmware details
    ENDPOINT = "/network-services/v1alpha1/firmware-details"

    def __init__(
        self,
        client: ArubaCentralClient,
        db_pool=None,
    ):
        """Initialize ArubaFirmwareSyncer.

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
    def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
        """Parse timestamp from API response.

        Args:
            ts: Timestamp string (ISO format)

        Returns:
            Parsed datetime or None
        """
        if not ts:
            return None
        try:
            if isinstance(ts, str):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return None
        except (ValueError, TypeError):
            return None

    def _prepare_firmware_record(self, firmware_data: dict) -> Optional[tuple]:
        """Prepare a firmware record for database update.

        Args:
            firmware_data: Raw firmware dict from Central API

        Returns:
            Tuple of values for the update query, or None if invalid
        """
        serial = self.normalize_serial(firmware_data.get("serialNumber"))
        if not serial:
            logger.warning(f"Skipping firmware with invalid serial: {firmware_data.get('id')}")
            return None

        return (
            serial,
            firmware_data.get("softwareVersion"),
            firmware_data.get("recommendedVersion"),
            firmware_data.get("upgradeStatus"),
            firmware_data.get("firmwareClassification"),
            self.parse_timestamp(firmware_data.get("lastUpgradedTimeAt")),
        )

    # ----------------------------------------
    # Database Operations
    # ----------------------------------------

    async def _update_firmware_page(
        self, conn, firmware_items: list[dict], sync_timestamp: datetime
    ) -> tuple[int, int, list[str]]:
        """Update firmware info for a page of devices.

        Args:
            conn: Database connection
            firmware_items: List of firmware dicts from Central API
            sync_timestamp: Current sync timestamp

        Returns:
            Tuple of (updated_count, skipped_count, list of serials updated)
        """
        records = []
        serials_updated = []

        for item in firmware_items:
            record = self._prepare_firmware_record(item)
            if record:
                records.append(record)
                serials_updated.append(record[0])  # serial_number

        if not records:
            return 0, len(firmware_items), []

        # Update existing devices with firmware info
        # Using executemany with UPDATE WHERE serial_number matches
        updated_count = 0
        for record in records:
            result = await conn.execute('''
                UPDATE devices SET
                    firmware_version = $2,
                    firmware_recommended_version = $3,
                    firmware_upgrade_status = $4,
                    firmware_classification = $5,
                    firmware_last_upgraded_at = $6,
                    firmware_synced_at = $7,
                    synced_at = NOW()
                WHERE serial_number = $1
            ''', *record, sync_timestamp)

            # Check if update affected a row
            try:
                count = int(result.split()[-1])
                updated_count += count
            except (ValueError, IndexError, AttributeError):
                pass

        skipped = len(firmware_items) - len(records)
        return updated_count, skipped, serials_updated

    async def _clear_stale_firmware(
        self, conn, serials_seen: list[str], sync_timestamp: datetime
    ) -> int:
        """Clear firmware data for devices not seen in this sync.

        This prevents stale firmware data from lingering forever.

        Args:
            conn: Database connection
            serials_seen: List of serial numbers seen in this sync
            sync_timestamp: Current sync timestamp

        Returns:
            Number of devices with firmware data cleared
        """
        if not serials_seen:
            # If no firmware data fetched, don't clear anything
            return 0

        result = await conn.execute('''
            UPDATE devices SET
                firmware_version = NULL,
                firmware_recommended_version = NULL,
                firmware_upgrade_status = NULL,
                firmware_classification = NULL,
                firmware_last_upgraded_at = NULL,
                firmware_synced_at = $1
            WHERE firmware_version IS NOT NULL
              AND serial_number IS NOT NULL
              AND serial_number != ''
              AND serial_number != ALL($2::text[])
        ''', sync_timestamp, serials_seen)

        try:
            return int(result.split()[-1])
        except (ValueError, IndexError, AttributeError):
            return 0

    # ----------------------------------------
    # Sync Operations
    # ----------------------------------------

    async def sync_to_postgres(self) -> dict:
        """Sync all firmware details from Aruba Central.

        Process:
        1. Fetch all firmware details with pagination
        2. Update matching devices by serial_number
        3. Clear stale firmware data

        Returns:
            Dict with sync statistics

        Raises:
            ConnectionPoolError: If database pool is not available
            PartialSyncError: If sync completes with errors
        """
        if self.db_pool is None:
            raise ConnectionPoolError(
                "Database connection pool is required for firmware sync"
            )

        error_collector = ErrorCollector()
        sync_timestamp = datetime.now(timezone.utc)

        total_updated = 0
        total_skipped = 0
        total_pages = 0
        all_serials_seen: list[str] = []

        try:
            async with database_transaction(self.db_pool) as conn:
                # Fetch and update firmware data page by page
                async for page in self.client.paginate(
                    self.ENDPOINT,
                    config=FIRMWARE_PAGINATION,
                ):
                    try:
                        updated, skipped, serials = await self._update_firmware_page(
                            conn, page, sync_timestamp
                        )
                        total_updated += updated
                        total_skipped += skipped
                        total_pages += 1
                        all_serials_seen.extend(serials)

                        logger.debug(
                            f"Firmware page {total_pages}: {updated} updated, {skipped} skipped"
                        )

                    except asyncpg.PostgresError as e:
                        logger.warning(f"Database error on page {total_pages}: {e}")
                        error_collector.add(
                            DatabaseError(str(e), cause=e),
                            context={"page": total_pages}
                        )

                # Clear stale firmware data
                cleared = await self._clear_stale_firmware(
                    conn, all_serials_seen, sync_timestamp
                )
                if cleared > 0:
                    logger.info(f"Cleared stale firmware data from {cleared} devices")

        except GLPError as e:
            logger.error(f"API error during firmware sync: {e}")
            error_collector.add(e, context={"operation": "fetch"})

        except Exception as e:
            logger.error(f"Unexpected error during firmware sync: {e}")
            error_collector.add(
                SyncError(f"Firmware sync failed: {e}", cause=e),
                context={"operation": "sync"}
            )

        stats = {
            "source": "aruba_central_firmware",
            "total_pages": total_pages,
            "total_updated": total_updated,
            "total_skipped": total_skipped,
            "unique_serials": len(set(all_serials_seen)),
            "stale_cleared": cleared if 'cleared' in locals() else 0,
            "errors": error_collector.count(),
            "synced_at": sync_timestamp.isoformat(),
        }

        logger.info(
            f"Firmware sync complete: {total_updated} devices updated, "
            f"{stats.get('stale_cleared', 0)} stale cleared, {error_collector.count()} errors"
        )

        if error_collector.has_errors():
            raise PartialSyncError(
                f"Firmware sync completed with {error_collector.count()} errors",
                succeeded=total_updated,
                failed=error_collector.count(),
                errors=[e for e, _ in error_collector.get_errors()],
                details=stats,
            )

        return stats

    async def sync(self) -> dict:
        """Full sync: fetch all firmware details from Aruba Central.

        This is the main entry point for syncing firmware details.

        Returns:
            Sync statistics dictionary
        """
        logger.info(f"Starting Aruba Central firmware sync at {datetime.utcnow().isoformat()}")
        return await self.sync_to_postgres()

    async def fetch_all_firmware(self) -> list[dict]:
        """Fetch all firmware details (for testing/export).

        Returns:
            List of firmware dictionaries
        """
        return await self.client.fetch_all(
            self.ENDPOINT,
            config=FIRMWARE_PAGINATION,
        )


# ============================================
# Standalone Test
# ============================================

if __name__ == "__main__":
    import asyncio
    import json

    from .aruba_auth import ArubaTokenManager
    from .aruba_client import ArubaCentralClient

    async def main():
        token_manager = ArubaTokenManager()

        async with ArubaCentralClient(token_manager) as client:
            syncer = ArubaFirmwareSyncer(client=client)
            firmware = await syncer.fetch_all_firmware()
            print(f"Fetched {len(firmware)} firmware records")
            if firmware:
                print(json.dumps(firmware[0], indent=2))

    asyncio.run(main())
