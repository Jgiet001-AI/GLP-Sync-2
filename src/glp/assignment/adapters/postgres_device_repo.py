"""PostgreSQL adapter for device repository.

This adapter implements IDeviceRepository using asyncpg
to query the devices table.
"""

import logging
from typing import Optional

import asyncpg

from ..domain.entities import DeviceAssignment
from ..domain.ports import IDeviceRepository

logger = logging.getLogger(__name__)


class PostgresDeviceRepository(IDeviceRepository):
    """PostgreSQL implementation of IDeviceRepository."""

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with database connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    async def find_by_serial(self, serial: str) -> Optional[DeviceAssignment]:
        """Find a device by serial number."""
        serial = serial.strip().upper()

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    d.id,
                    d.serial_number,
                    d.mac_address,
                    d.device_type,
                    d.model,
                    d.region,
                    d.application_id,
                    d.raw_data->'tags' as tags,
                    ds.subscription_id,
                    s.key as subscription_key
                FROM devices d
                LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
                LEFT JOIN subscriptions s ON ds.subscription_id = s.id
                WHERE UPPER(d.serial_number) = $1
                AND NOT d.archived
                LIMIT 1
                """,
                serial,
            )

            if row is None:
                return None

            return self._row_to_assignment(row)

    async def find_by_mac(self, mac: str) -> Optional[DeviceAssignment]:
        """Find a device by MAC address."""
        mac = mac.strip().upper()

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    d.id,
                    d.serial_number,
                    d.mac_address,
                    d.device_type,
                    d.model,
                    d.region,
                    d.application_id,
                    d.raw_data->'tags' as tags,
                    ds.subscription_id,
                    s.key as subscription_key
                FROM devices d
                LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
                LEFT JOIN subscriptions s ON ds.subscription_id = s.id
                WHERE UPPER(d.mac_address) = $1
                AND NOT d.archived
                LIMIT 1
                """,
                mac,
            )

            if row is None:
                return None

            return self._row_to_assignment(row)

    async def find_by_serials(self, serials: list[str]) -> list[DeviceAssignment]:
        """Find multiple devices by serial numbers."""
        if not serials:
            return []

        # Normalize serials
        normalized = [s.strip().upper() for s in serials]

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    d.id,
                    d.serial_number,
                    d.mac_address,
                    d.device_type,
                    d.model,
                    d.region,
                    d.application_id,
                    d.raw_data->'tags' as tags,
                    ds.subscription_id,
                    s.key as subscription_key
                FROM devices d
                LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
                LEFT JOIN subscriptions s ON ds.subscription_id = s.id
                WHERE UPPER(d.serial_number) = ANY($1)
                AND NOT d.archived
                """,
                normalized,
            )

            return [self._row_to_assignment(row) for row in rows]

    async def get_all_tags(self) -> list[tuple[str, str]]:
        """Get all unique tag key-value pairs."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT tag_key, tag_value
                FROM device_tags
                ORDER BY tag_key, tag_value
                """
            )

            return [(row["tag_key"], row["tag_value"]) for row in rows]

    def _row_to_assignment(self, row: asyncpg.Record) -> DeviceAssignment:
        """Convert database row to DeviceAssignment."""
        # Parse tags from JSONB
        tags_json = row["tags"]
        current_tags = {}
        if tags_json:
            if isinstance(tags_json, dict):
                current_tags = tags_json
            elif isinstance(tags_json, str):
                import json

                try:
                    current_tags = json.loads(tags_json)
                except json.JSONDecodeError:
                    pass

        return DeviceAssignment(
            serial_number=row["serial_number"],
            mac_address=row["mac_address"],
            device_id=row["id"],
            device_type=row["device_type"],
            model=row["model"],
            region=row["region"],
            current_subscription_id=row["subscription_id"],
            current_subscription_key=row["subscription_key"],
            current_application_id=row["application_id"],
            current_tags=current_tags,
        )
