"""Sync Devices Use Case - Orchestrates the device sync workflow.

This use case implements the business logic for syncing devices from
the GreenLake API to the database. It depends on ports (interfaces)
for all external operations, making it fully testable without
infrastructure.

Workflow:
1. Fetch all devices from API (via IDeviceAPI)
2. Map raw responses to domain entities (via IFieldMapper)
3. Extract related data (subscriptions, tags)
4. Upsert devices to database (via IDeviceRepository)
5. Sync related data (subscriptions, tags)
6. Return sync statistics
"""

import logging
from datetime import datetime, timezone

from ..domain.entities import (
    Device,
    DeviceSubscription,
    DeviceTag,
    SyncResult,
)
from ..domain.ports import IDeviceAPI, IDeviceRepository, IFieldMapper

logger = logging.getLogger(__name__)


class SyncDevicesUseCase:
    """Orchestrates the device sync workflow.

    This use case follows the Clean Architecture pattern:
    - Depends only on port interfaces, not concrete implementations
    - Contains business logic for the sync workflow
    - Returns domain objects (SyncResult), not infrastructure types

    Example:
        use_case = SyncDevicesUseCase(
            device_api=GLPDeviceAPI(client),
            device_repo=PostgresDeviceRepository(pool),
            field_mapper=DeviceFieldMapper(),
        )
        result = await use_case.execute()
    """

    def __init__(
        self,
        device_api: IDeviceAPI,
        device_repo: IDeviceRepository,
        field_mapper: IFieldMapper,
    ):
        """Initialize the use case with its dependencies.

        Args:
            device_api: Port for fetching devices from API
            device_repo: Port for persisting devices to database
            field_mapper: Port for transforming between formats
        """
        self.api = device_api
        self.repo = device_repo
        self.mapper = field_mapper

    async def execute(self) -> SyncResult:
        """Execute the device sync workflow.

        Steps:
        1. Fetch all devices from API
        2. Map to domain entities
        3. Extract subscriptions and tags
        4. Upsert devices to database
        5. Sync related data (subscriptions, tags)

        Returns:
            SyncResult with statistics about the sync operation
        """
        started_at = datetime.now(timezone.utc)
        errors: list[str] = []

        logger.info(f"Starting device sync at {started_at.isoformat()}")

        # Step 1: Fetch from API
        try:
            raw_devices = await self.api.fetch_all()
            logger.info(f"Fetched {len(raw_devices)} devices from API")
        except Exception as e:
            logger.error(f"Failed to fetch devices from API: {e}")
            return SyncResult(
                success=False,
                total=0,
                upserted=0,
                errors=1,
                synced_at=started_at,
                error_details=[f"API fetch failed: {e}"],
            )

        if not raw_devices:
            logger.info("No devices to sync")
            return SyncResult(
                success=True,
                total=0,
                upserted=0,
                errors=0,
                synced_at=started_at,
            )

        # Step 2: Map to domain entities
        devices: list[Device] = []
        all_subscriptions: list[DeviceSubscription] = []
        all_tags: list[DeviceTag] = []

        for raw in raw_devices:
            try:
                device = self.mapper.map_to_entity(raw)
                devices.append(device)

                # Extract related data
                subscriptions = self.mapper.extract_subscriptions(device, raw)
                all_subscriptions.extend(subscriptions)

                tags = self.mapper.extract_tags(device, raw)
                all_tags.extend(tags)

            except Exception as e:
                device_id = raw.get("id", "unknown")
                error_msg = f"Mapping error for device {device_id}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

        logger.info(
            f"Mapped {len(devices)} devices, "
            f"{len(all_subscriptions)} subscriptions, "
            f"{len(all_tags)} tags"
        )

        # Step 3: Upsert devices to database
        upserted = 0
        try:
            upserted = await self.repo.upsert_devices(devices)
            logger.info(f"Upserted {upserted} devices to database")
        except Exception as e:
            error_msg = f"Database upsert failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Step 4: Sync related data (subscriptions and tags)
        try:
            device_ids = [d.id for d in devices]
            await self.repo.sync_all_related_data(
                device_ids,
                all_subscriptions,
                all_tags,
            )
            logger.info("Synced subscriptions and tags")
        except Exception as e:
            error_msg = f"Related data sync failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Build result
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()

        logger.info(
            f"Device sync completed in {duration:.2f}s: "
            f"{upserted} upserted, {len(errors)} errors"
        )

        return SyncResult(
            success=len(errors) == 0,
            total=len(raw_devices),
            upserted=upserted,
            errors=len(errors),
            synced_at=started_at,
            error_details=errors,
        )

    async def execute_streaming(self) -> SyncResult:
        """Execute device sync with streaming to minimize memory usage.

        This method processes devices page by page instead of loading all
        records into memory at once. Ideal for large inventories (100K+ devices).

        The streaming approach:
        1. Fetches one page of devices at a time via fetch_paginated()
        2. Maps and upserts each page immediately
        3. Syncs related data (subscriptions, tags) per page
        4. Keeps only current page in memory

        Returns:
            SyncResult with statistics about the sync operation
        """
        started_at = datetime.now(timezone.utc)
        errors: list[str] = []
        total_fetched = 0
        total_upserted = 0

        logger.info(f"Starting streaming device sync at {started_at.isoformat()}")

        try:
            async for page in self.api.fetch_paginated():
                page_size = len(page)
                total_fetched += page_size

                # Map page to entities
                devices: list[Device] = []
                subscriptions: list[DeviceSubscription] = []
                tags: list[DeviceTag] = []

                for raw in page:
                    try:
                        device = self.mapper.map_to_entity(raw)
                        devices.append(device)
                        subscriptions.extend(self.mapper.extract_subscriptions(device, raw))
                        tags.extend(self.mapper.extract_tags(device, raw))
                    except Exception as e:
                        device_id = raw.get("id", "unknown")
                        error_msg = f"Mapping error for device {device_id}: {e}"
                        logger.warning(error_msg)
                        errors.append(error_msg)

                # Upsert this page immediately
                if devices:
                    try:
                        upserted = await self.repo.upsert_devices(devices)
                        total_upserted += upserted

                        # Sync related data for this page
                        device_ids = [d.id for d in devices]
                        await self.repo.sync_all_related_data(device_ids, subscriptions, tags)

                    except Exception as e:
                        error_msg = f"Database operation failed for page: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

                logger.debug(
                    f"Processed page: {page_size} devices, {total_fetched} total so far"
                )

        except Exception as e:
            error_msg = f"Streaming sync failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Build result
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()

        logger.info(
            f"Streaming device sync completed in {duration:.2f}s: "
            f"{total_upserted} upserted, {len(errors)} errors"
        )

        return SyncResult(
            success=len(errors) == 0,
            total=total_fetched,
            upserted=total_upserted,
            errors=len(errors),
            synced_at=started_at,
            error_details=errors,
        )
