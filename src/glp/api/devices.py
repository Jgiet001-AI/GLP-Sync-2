#!/usr/bin/env python3
"""HPE GreenLake Device Inventory Synchronization.

This module provides high-performance device inventory synchronization from
the HPE GreenLake Platform API to PostgreSQL. Supports both database sync
and JSON export operations.

Architecture:
    DeviceSyncer composes GLPClient for HTTP concerns and focuses purely on:
    - Device-specific field mappings (all 30+ fields)
    - Database schema operations (devices, device_subscriptions, device_tags)
    - Business logic

The separation of concerns means:
    - GLPClient handles: HTTP, auth, pagination, rate limiting, retries
    - DeviceSyncer handles: device schema, field extraction, related tables

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
from datetime import datetime
from typing import Optional

from .client import DEVICES_PAGINATION, GLPClient


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
    ):
        """Initialize DeviceSyncer.

        Args:
            client: Configured GLPClient instance
            db_pool: asyncpg connection pool (optional for JSON-only mode)
        """
        self.client = client
        self.db_pool = db_pool

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
    # Database Operations
    # ----------------------------------------

    async def sync_to_postgres(self, devices: list[dict]) -> dict:
        """Upsert devices to PostgreSQL.

        For each device:
        1. Insert or update the main devices table
        2. Sync subscriptions to device_subscriptions table
        3. Sync tags to device_tags table

        Args:
            devices: List of device dictionaries from API

        Returns:
            Dict with sync statistics
        """
        if self.db_pool is None:
            raise ValueError("Database connection pool is required")

        inserted = 0
        updated = 0
        errors = 0

        async with self.db_pool.acquire() as conn:
            for device in devices:
                try:
                    exists = await conn.fetchval(
                        "SELECT 1 FROM devices WHERE id = $1",
                        device["id"]
                    )

                    if exists:
                        await self._update_device(conn, device)
                        updated += 1
                    else:
                        await self._insert_device(conn, device)
                        inserted += 1

                except Exception as e:
                    errors += 1
                    print(f"[DeviceSyncer] Error syncing device {device.get('id')}: {e}")

        stats = {
            "total": len(devices),
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
            "synced_at": datetime.utcnow().isoformat(),
        }

        print(f"[DeviceSyncer] Sync complete: {inserted} inserted, {updated} updated, {errors} errors")
        return stats

    async def _insert_device(self, conn, device: dict):
        """Insert a single device into PostgreSQL with all API fields."""
        # Parse timestamps
        created_at = self._parse_timestamp(device.get("createdAt"))
        updated_at = self._parse_timestamp(device.get("updatedAt"))

        # Extract nested objects (handle None gracefully)
        application = device.get("application") or {}
        location = device.get("location") or {}
        dedicated = device.get("dedicatedPlatformWorkspace") or {}

        await conn.execute('''
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
        ''',
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
        )

        # Sync related tables
        await self._sync_subscriptions(conn, device["id"], device.get("subscription") or [])
        await self._sync_tags(conn, device["id"], device.get("tags") or {})

    async def _update_device(self, conn, device: dict):
        """Update a single device in PostgreSQL with all API fields."""
        # Parse timestamp
        updated_at = self._parse_timestamp(device.get("updatedAt"))

        # Extract nested objects (handle None gracefully)
        application = device.get("application") or {}
        location = device.get("location") or {}
        dedicated = device.get("dedicatedPlatformWorkspace") or {}

        await conn.execute('''
            UPDATE devices SET
                mac_address = $2,
                serial_number = $3,
                part_number = $4,
                device_type = $5,
                model = $6,
                region = $7,
                archived = $8,
                device_name = $9,
                secondary_name = $10,
                assigned_state = $11,
                resource_type = $12,
                tenant_workspace_id = $13,
                application_id = $14,
                application_resource_uri = $15,
                dedicated_platform_id = $16,
                location_id = $17,
                location_name = $18,
                location_city = $19,
                location_state = $20,
                location_country = $21,
                location_postal_code = $22,
                location_street_address = $23,
                location_latitude = $24,
                location_longitude = $25,
                location_source = $26,
                updated_at = $27,
                raw_data = $28::jsonb,
                synced_at = NOW()
            WHERE id = $1
        ''',
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
            updated_at,
            json.dumps(device),
        )

        # Sync related tables
        await self._sync_subscriptions(conn, device["id"], device.get("subscription") or [])
        await self._sync_tags(conn, device["id"], device.get("tags") or {})

    async def _sync_subscriptions(self, conn, device_id: str, subscriptions: list):
        """Sync device subscriptions to the device_subscriptions table.

        Strategy: Delete all existing, insert fresh. This ensures we capture
        any subscriptions that were removed from the device.

        Args:
            conn: Database connection
            device_id: UUID of the device
            subscriptions: List of subscription dicts from API
        """
        # Delete existing subscriptions for this device
        await conn.execute(
            'DELETE FROM device_subscriptions WHERE device_id = $1',
            device_id
        )

        # Insert new subscriptions
        for sub in subscriptions:
            if sub.get("id"):
                await conn.execute('''
                    INSERT INTO device_subscriptions (device_id, subscription_id, resource_uri)
                    VALUES ($1, $2, $3)
                ''', device_id, sub.get("id"), sub.get("resourceUri"))

    async def _sync_tags(self, conn, device_id: str, tags: dict):
        """Sync device tags to the device_tags table.

        Strategy: Delete all existing, insert fresh. This ensures we capture
        any tags that were removed from the device.

        Args:
            conn: Database connection
            device_id: UUID of the device
            tags: Dict of tag key-value pairs from API
        """
        # Delete existing tags for this device
        await conn.execute(
            'DELETE FROM device_tags WHERE device_id = $1',
            device_id
        )

        # Insert new tags
        for key, value in tags.items():
            await conn.execute('''
                INSERT INTO device_tags (device_id, tag_key, tag_value)
                VALUES ($1, $2, $3)
            ''', device_id, key, value)

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

        Returns:
            Sync statistics dictionary
        """
        print(f"[DeviceSyncer] Starting sync at {datetime.utcnow().isoformat()}")

        devices = await self.fetch_all_devices()

        if self.db_pool:
            stats = await self.sync_to_postgres(devices)
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
        """
        devices = await self.fetch_all_devices()

        with open(filepath, "w") as f:
            json.dump(devices, f, indent=2)

        print(f"[DeviceSyncer] Saved {len(devices):,} devices to {filepath}")
        return len(devices)


# ============================================
# Backward Compatibility Layer
# ============================================
# These allow the old API to work while transitioning

class APIError(Exception):
    """Raised when API call fails.

    DEPRECATED: Use GLPClientError from client.py instead.
    Kept for backward compatibility.
    """
    pass


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
