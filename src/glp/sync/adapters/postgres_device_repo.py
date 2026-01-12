"""PostgreSQL repository adapter for device persistence.

This adapter implements IDeviceRepository and handles all database operations
for devices, including the optimized bulk UPSERT, subscription sync, and tag sync.

The bulk operations here preserve the performance optimizations from the original
DeviceSyncer, reducing ~47,000 queries to ~5 queries for 11,000 devices.
"""

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..domain.entities import Device, DeviceSubscription, DeviceTag
from ..domain.ports import IDeviceRepository

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class PostgresDeviceRepository(IDeviceRepository):
    """PostgreSQL implementation of IDeviceRepository.

    Provides optimized bulk operations for device persistence:
    - UPSERT (INSERT ON CONFLICT) for devices
    - Bulk DELETE with ANY() for subscriptions and tags
    - executemany() for bulk inserts

    All operations can be run within a single transaction for atomicity.
    """

    def __init__(self, pool: "asyncpg.Pool"):
        """Initialize the repository.

        Args:
            pool: asyncpg connection pool for database operations
        """
        self.pool = pool

    async def upsert_devices(self, devices: list[Device]) -> int:
        """Bulk upsert devices using INSERT ON CONFLICT.

        This is the optimized UPSERT that eliminates N SELECT queries.
        All devices are inserted/updated in a single batch operation.

        Args:
            devices: List of Device entities to upsert

        Returns:
            Number of devices upserted
        """
        if not devices:
            return 0

        # Convert devices to record tuples
        records = [self._device_to_record(d) for d in devices]

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
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
                """,
                records,
            )

        return len(records)

    async def sync_subscriptions(
        self,
        device_ids: list[UUID],
        subscriptions: list[DeviceSubscription],
    ) -> None:
        """Sync device subscriptions (delete old, insert new).

        Uses bulk DELETE with ANY() followed by bulk INSERT.

        Args:
            device_ids: List of device IDs to sync subscriptions for
            subscriptions: List of DeviceSubscription entities to insert
        """
        if not device_ids:
            return

        async with self.pool.acquire() as conn:
            # Delete all existing subscriptions for these devices
            await conn.execute(
                "DELETE FROM device_subscriptions WHERE device_id = ANY($1)",
                [str(d) for d in device_ids],
            )

            # Insert new subscriptions
            if subscriptions:
                records = [
                    (str(s.device_id), str(s.subscription_id), s.resource_uri)
                    for s in subscriptions
                ]
                await conn.executemany(
                    """
                    INSERT INTO device_subscriptions (device_id, subscription_id, resource_uri)
                    VALUES ($1, $2, $3)
                    """,
                    records,
                )

    async def sync_tags(
        self,
        device_ids: list[UUID],
        tags: list[DeviceTag],
    ) -> None:
        """Sync device tags (delete old, insert new).

        Uses bulk DELETE with ANY() followed by bulk INSERT.

        Args:
            device_ids: List of device IDs to sync tags for
            tags: List of DeviceTag entities to insert
        """
        if not device_ids:
            return

        async with self.pool.acquire() as conn:
            # Delete all existing tags for these devices
            await conn.execute(
                "DELETE FROM device_tags WHERE device_id = ANY($1)",
                [str(d) for d in device_ids],
            )

            # Insert new tags
            if tags:
                records = [(str(t.device_id), t.tag_key, t.tag_value) for t in tags]
                await conn.executemany(
                    """
                    INSERT INTO device_tags (device_id, tag_key, tag_value)
                    VALUES ($1, $2, $3)
                    """,
                    records,
                )

    async def sync_all_related_data(
        self,
        device_ids: list[UUID],
        subscriptions: list[DeviceSubscription],
        tags: list[DeviceTag],
    ) -> None:
        """Sync both subscriptions and tags in a single transaction.

        This is the preferred method for efficiency - it combines
        subscription and tag sync into one transaction.

        Args:
            device_ids: List of device IDs to sync related data for
            subscriptions: List of DeviceSubscription entities
            tags: List of DeviceTag entities
        """
        if not device_ids:
            return

        # Import here to avoid circular imports
        from ...api.database import database_transaction

        async with database_transaction(self.pool) as conn:
            # Delete all existing subscriptions and tags
            device_id_strs = [str(d) for d in device_ids]

            await conn.execute(
                "DELETE FROM device_subscriptions WHERE device_id = ANY($1)",
                device_id_strs,
            )
            await conn.execute(
                "DELETE FROM device_tags WHERE device_id = ANY($1)",
                device_id_strs,
            )

            # Insert new subscriptions
            if subscriptions:
                sub_records = [
                    (str(s.device_id), str(s.subscription_id), s.resource_uri)
                    for s in subscriptions
                ]
                await conn.executemany(
                    """
                    INSERT INTO device_subscriptions (device_id, subscription_id, resource_uri)
                    VALUES ($1, $2, $3)
                    """,
                    sub_records,
                )

            # Insert new tags
            if tags:
                tag_records = [(str(t.device_id), t.tag_key, t.tag_value) for t in tags]
                await conn.executemany(
                    """
                    INSERT INTO device_tags (device_id, tag_key, tag_value)
                    VALUES ($1, $2, $3)
                    """,
                    tag_records,
                )

    def _device_to_record(self, device: Device) -> tuple[Any, ...]:
        """Convert Device entity to database record tuple.

        Args:
            device: Device entity

        Returns:
            Tuple of values for database insertion
        """
        import json

        return (
            str(device.id),
            device.mac_address,
            device.serial_number,
            device.part_number,
            device.device_type,
            device.model,
            device.region,
            device.archived,
            device.device_name,
            device.secondary_name,
            device.assigned_state,
            device.resource_type,
            device.tenant_workspace_id,
            device.application_id,
            device.application_resource_uri,
            device.dedicated_platform_id,
            device.location_id,
            device.location_name,
            device.location_city,
            device.location_state,
            device.location_country,
            device.location_postal_code,
            device.location_street_address,
            device.location_latitude,
            device.location_longitude,
            device.location_source,
            device.created_at,
            device.updated_at,
            json.dumps(device.raw_data),
        )
