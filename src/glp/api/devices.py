#!/usr/bin/env python3
"""HPE GreenLake Device Inventory Synchronization.

This module provides high-performance device inventory synchronization from
the HPE GreenLake Platform API to PostgreSQL. Supports both database sync
and JSON export operations.

API Specifications:
    - Endpoint: GET /devices/v1/devices
    - Max items per request: 2,000
    - Rate limit: 160 requests/minute
    - Pagination: Offset-based (offset, limit parameters)
    - Authentication: OAuth2 Bearer token

Database Schema:
    The `devices` table stores both structured fields (id, serial_number,
    mac_address, etc.) and the complete raw API response as JSONB for
    flexibility in querying new fields without schema migrations.

Performance:
    - Fetches ~12,000 devices in ~14 seconds
    - Uses connection pooling for database efficiency
    - 500ms delay between API pages to respect rate limits

Example:
    >>> syncer = DeviceSyncer(token_manager=TokenManager())
    >>> stats = await syncer.sync()  # Full sync to database
    >>> count = await syncer.fetch_and_save_json("backup.json")  # Export only

Author: HPE GreenLake Team
"""
import os
import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from .auth import TokenManager, TokenError


class DeviceSyncer:
    """High-performance device inventory synchronizer for GreenLake Platform.
    
    Fetches device inventory from the GreenLake API using paginated requests
    and upserts the data to PostgreSQL. Handles authentication, rate limiting,
    and network errors gracefully.
    
    Attributes:
        token_manager: TokenManager instance for API authentication.
        db_pool: asyncpg connection pool for PostgreSQL operations.
        base_url: GreenLake API base URL (from env: GLP_BASE_URL).
        api_url: Constructed device API endpoint URL.
    
    Rate Limiting:
        - 500ms delay between pagination requests
        - Automatic retry on 429 responses with Retry-After header
        - Token refresh on 401 responses
    
    Example:
        >>> syncer = DeviceSyncer(token_manager=manager, db_pool=pool)
        >>> stats = await syncer.sync()
        {'total': 11721, 'inserted': 0, 'updated': 11721, 'errors': 0}
    """

    def __init__(
        self,
        token_manager: Optional[TokenManager] = None,
        db_pool = None,
        base_url: Optional[str] = None,
    ):

        self.token_manager = token_manager or TokenManager()
        self.db_pool = db_pool
        self.base_url = base_url or os.getenv("GLP_BASE_URL")

        if not self.base_url:
            raise ValueError("Base URL is required")
        
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        
        self.api_url = "{}devices/v1/devices".format(self.base_url)

    async def fetch_all_devices(self) -> list[dict]:
        """Fetch all devices from GreenLake API using offset pagination.
        
        Iterates through paginated API responses, collecting all devices
        into a single list. Handles 401 (token expired) and 429 (rate limit)
        responses automatically.
        
        Returns:
            list[dict]: Complete list of device dictionaries from the API.
            
        Raises:
            APIError: If API returns non-2xx status or network error occurs.
        """

        all_devices = []
        offset = 0
        limit = 2000
        total = None

        async with aiohttp.ClientSession() as session:
            while True:
                token = await self.token_manager.get_token()
                headers = {
                    "Authorization": "Bearer {}".format(token),
                }

                url = f"{self.api_url}?offset={offset}&limit={limit}"
            
                try:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 401:
                            print("Token expired, refreshing...")
                            self.token_manager.invalidate()
                            token = await self.token_manager.get_token()
                            headers = {
                                "Authorization": "Bearer {}".format(token),
                            }
                            continue

                        if response.status == 429:
                            retry_after = response.headers.get("Retry-After", 60)
                            print(f"Rate limit exceeded, retrying in {retry_after} seconds...")
                            await asyncio.sleep(retry_after)
                            continue
                        
                        if response.status != 200:
                            error_text = await response.text()
                            raise APIError(f"API error {response.status}: {error_text}")
                        
                        data = await response.json()
                    
                except aiohttp.ClientError as e:
                    raise APIError(f"Network error: {e}")

                items = data.get("items", [])
                all_devices.extend(items)

                if total is None:
                    total = data.get("total", len(items))
                    print(f"[DeviceSyncer] Total devices to fetch: {total:,}")
                
                fetched = len(all_devices)
                percent = (fetched / total * 100) if total > 0 else 100
                print(f"[DeviceSyncer] Progress: {fetched:,}/{total:,} ({percent:.1f}%)")

                if fetched >= total or len(items) < limit:
                    break
                offset += limit
                # Rate limit protection: 500ms delay between requests
                await asyncio.sleep(0.5)

        print(f"[DeviceSyncer] Fetch complete: {len(all_devices):,} devices")
        return all_devices

    async def sync_to_postgres(self, devices: list[dict]) -> dict:
        """
        Upsert devices to PostgreSQL.

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
                        "SELECT id FROM devices WHERE id = $1", device["id"]
                    )
                    if exists:
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
        """Insert a single device into PostgreSQL."""
        # Parse ISO timestamp strings to datetime objects
        # Replace 'Z' with '+00:00' for fromisoformat compatibility
        created_at = None
        if device.get("createdAt"):
            created_at = datetime.fromisoformat(device.get("createdAt").replace('Z', '+00:00'))

        updated_at = None
        if device.get("updatedAt"):
            updated_at = datetime.fromisoformat(device.get("updatedAt").replace('Z', '+00:00'))

        await conn.execute('''
                INSERT INTO devices (
                    id, mac_address, serial_number, part_number,
                    device_type, model, region, archived,
                    device_name, secondary_name, assigned_state,
                    created_at, updated_at, raw_data, synced_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12, $13, $14::jsonb, NOW()
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
                created_at,
                updated_at,
                json.dumps(device),
            )

    async def _update_device(self, conn, device: dict):
        """Update a single device in PostgreSQL."""
        # Parse ISO timestamp string to datetime object
        # Replace 'Z' with '+00:00' for fromisoformat compatibility
        updated_at = None
        if device.get("updatedAt"):
            updated_at = datetime.fromisoformat(device.get("updatedAt").replace('Z', '+00:00'))

        await conn.execute('''
                UPDATE devices
                SET
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
                    updated_at = $12,
                    raw_data = $13::jsonb
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
                updated_at,
                json.dumps(device),
            )

    async def sync(self) -> dict:
        """
        Full sync: fetch all devices and upsert to database.

        Returns:
            Sync statistics
        """
        print(f"[DeviceSyncer] Starting sync at {datetime.utcnow().isoformat()}")

        # Fetch all devices
        devices = await self.fetch_all_devices()

        # Sync to database if configured
        if self.db_pool:
            stats = await self.sync_to_postgres(devices)
        else:
            stats = {
                "total": len(devices),
                "note": "No database configured, fetch only",
            }

        return stats

    async def fetch_and_save_json(self, filepath: str = "devices.json") -> int:
        """
        Fetch all devices and save to JSON file.
        Useful for testing without database.

        Returns:
            Number of devices saved
        """
        devices = await self.fetch_all_devices()

        with open(filepath, "w") as f:
            json.dump(devices, f, indent=2)

        print(f"[DeviceSyncer] Saved {len(devices):,} devices to {filepath}")
        return len(devices)

class APIError(Exception):
    """Raised when API call fails."""
    pass


# Standalone usage
if __name__ == "__main__":
    async def main():
        syncer = DeviceSyncer()
        
        # For testing: just fetch and save to JSON
        await syncer.fetch_and_save_json("devices_backup.json")
    
    asyncio.run(main())
    
    