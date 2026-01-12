#!/usr/bin/env python3
"""Aruba Central Network Clients Synchronization.

This module provides synchronization of network clients (WiFi/Wired devices
connected to network equipment) from the Aruba Central API to PostgreSQL.

Architecture:
    ArubaClientsSyncer fetches clients per-site and:
    1. Primes the sites table with all known sites
    2. Fetches clients for each site with pagination
    3. Upserts clients using (site_id, mac) as unique key
    4. Marks removed clients (not seen in current sync)

Key Design Decisions:
    - Clients API requires site-id parameter (mandatory)
    - Sites are derived from devices.central_site_id
    - MAC addresses stored as PostgreSQL MACADDR type
    - Removed clients marked with status='REMOVED' (not deleted)

Database Tables Updated:
    - sites: site_id, site_name, last_synced_at
    - clients: All columns from API response

Example:
    async with ArubaCentralClient(token_manager) as client:
        syncer = ArubaClientsSyncer(client=client, db_pool=pool)
        stats = await syncer.sync()

Author: HPE GreenLake Team
"""
import asyncio
import json
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
    IntegrityError,
    PartialSyncError,
    SyncError,
)

logger = logging.getLogger(__name__)


# Pagination config for clients API (max 100 per page)
CLIENTS_PAGINATION = ArubaPaginationConfig(
    page_size=100,
    delay_between_pages=0.3,  # Slightly faster since per-site
    max_pages=None,
)


class ArubaClientsSyncer:
    """Network clients synchronizer for Aruba Central.

    Fetches network clients (WiFi/Wired connected devices) from Aruba Central
    and stores them in the clients table, organized by site.

    Attributes:
        client: ArubaCentralClient instance for API communication
        db_pool: asyncpg connection pool for database operations
    """

    # API endpoint for clients
    ENDPOINT = "/network-monitoring/v1alpha1/clients"

    def __init__(
        self,
        client: ArubaCentralClient,
        db_pool=None,
    ):
        """Initialize ArubaClientsSyncer.

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
    def normalize_mac(mac: Optional[str]) -> Optional[str]:
        """Normalize MAC address for PostgreSQL MACADDR type.

        Args:
            mac: Raw MAC address from API

        Returns:
            Normalized MAC address or None if invalid
        """
        if not mac:
            return None
        # MACADDR accepts various formats, but let's ensure consistency
        mac = str(mac).strip().upper()
        if not mac or len(mac) < 12:
            return None
        return mac

    @staticmethod
    def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
        """Parse timestamp from API response.

        Args:
            ts: Timestamp string (ISO format or 0 for current)

        Returns:
            Parsed datetime or None
        """
        if not ts or ts == "0":
            return None
        try:
            # Handle ISO format
            if isinstance(ts, str):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _sanitize_for_postgres(obj):
        """Recursively sanitize data for PostgreSQL - remove null bytes from strings.

        PostgreSQL cannot handle null bytes (\\x00 or \\u0000) in TEXT or JSONB.
        """
        if isinstance(obj, str):
            return obj.replace('\x00', '')
        elif isinstance(obj, dict):
            return {k: ArubaClientsSyncer._sanitize_for_postgres(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [ArubaClientsSyncer._sanitize_for_postgres(item) for item in obj]
        return obj

    def _prepare_client_record(
        self, client_data: dict, site_id: str
    ) -> Optional[tuple]:
        """Prepare a client record for database upsert.

        Args:
            client_data: Raw client dict from Central API
            site_id: Site ID this client belongs to

        Returns:
            Tuple of values for the upsert query, or None if invalid
        """
        # Sanitize the entire record first to remove null bytes
        client_data = self._sanitize_for_postgres(client_data)

        mac = self.normalize_mac(client_data.get("mac"))
        if not mac:
            logger.warning(f"Skipping client with invalid MAC: {client_data}")
            return None

        # Helper to convert empty strings and "None" to None
        def clean_str(val):
            if val is None or val == "" or val == "None":
                return None
            return val

        # Convert empty strings to None for INET columns (PostgreSQL INET type can't accept '')
        ipv4 = client_data.get("ipv4")
        ipv6 = client_data.get("ipv6")

        # Tunnel has CHECK constraint - must be NULL or in ('Port-based', 'User-based', 'Overlay')
        tunnel = client_data.get("tunnel")
        valid_tunnels = ('Port-based', 'User-based', 'Overlay')
        tunnel = tunnel if tunnel in valid_tunnels else None

        # Map health field - API docs say "health" but actual response uses "experience"
        # Try "health" first, then fall back to "experience"
        # Valid values: Good, Fair, Poor, Unknown
        health_value = client_data.get("health") or client_data.get("experience")
        health = health_value if health_value in ("Good", "Fair", "Poor", "Unknown") else None

        return (
            site_id,
            mac,
            clean_str(client_data.get("name")),
            health,
            clean_str(client_data.get("status")),
            clean_str(client_data.get("statusReason")),
            clean_str(client_data.get("type")),
            ipv4 if ipv4 else None,
            ipv6 if ipv6 else None,
            clean_str(client_data.get("network")),
            clean_str(client_data.get("vlanId")),
            clean_str(client_data.get("port")),
            clean_str(client_data.get("role")),
            clean_str(client_data.get("connectedDeviceSerial")),
            clean_str(client_data.get("connectedTo")),
            self.parse_timestamp(client_data.get("connectedSince")),
            self.parse_timestamp(client_data.get("lastSeenAt")),
            tunnel,
            client_data.get("tunnelId"),
            clean_str(client_data.get("keyManagement")),
            clean_str(client_data.get("authentication")),
            clean_str(client_data.get("capabilities")),
            json.dumps(client_data),  # raw_data - already sanitized above
        )

    # ----------------------------------------
    # Database Operations
    # ----------------------------------------

    async def _prime_sites(self, conn) -> list[tuple[str, Optional[str]]]:
        """Prime the sites table with sites from devices.

        Gets all unique central_site_id values from devices and ensures
        they exist in the sites table.

        Args:
            conn: Database connection

        Returns:
            List of (site_id, site_name) tuples
        """
        # Get unique sites from devices table
        site_rows = await conn.fetch('''
            SELECT DISTINCT
                central_site_id AS site_id,
                central_site_name AS site_name
            FROM devices
            WHERE central_site_id IS NOT NULL
              AND central_site_id != ''
              AND NOT archived
        ''')

        if not site_rows:
            logger.warning("No sites found in devices table")
            return []

        sites = [(row['site_id'], row['site_name']) for row in site_rows]

        # Upsert sites
        await conn.executemany('''
            INSERT INTO sites (site_id, site_name, created_at, updated_at)
            VALUES ($1, $2, NOW(), NOW())
            ON CONFLICT (site_id) DO UPDATE SET
                site_name = COALESCE(EXCLUDED.site_name, sites.site_name),
                updated_at = NOW()
        ''', sites)

        logger.info(f"Primed {len(sites)} sites")
        return sites

    async def _upsert_clients_page(
        self, conn, clients: list[dict], site_id: str, sync_timestamp: datetime
    ) -> tuple[int, int]:
        """Upsert a page of clients to the database.

        Args:
            conn: Database connection
            clients: List of client dicts from Central API
            site_id: Site ID these clients belong to
            sync_timestamp: Current sync timestamp for tracking

        Returns:
            Tuple of (upserted_count, skipped_count)
        """
        records = []

        for client_data in clients:
            record = self._prepare_client_record(client_data, site_id)
            if record:
                records.append(record)

        if not records:
            return 0, len(clients)

        # Upsert clients using (site_id, mac) as unique key
        await conn.executemany('''
            INSERT INTO clients (
                site_id, mac, name, health, status, status_reason,
                type, ipv4, ipv6, network, vlan_id, port, role,
                connected_device_serial, connected_to, connected_since,
                last_seen_at, tunnel, tunnel_id, key_management,
                authentication, capabilities, raw_data,
                created_at, updated_at, synced_at
            ) VALUES (
                $1, $2::macaddr, $3, $4, $5, $6,
                $7, $8::inet, $9::inet, $10, $11, $12, $13,
                $14, $15, $16,
                $17, $18, $19, $20,
                $21, $22, $23::jsonb,
                NOW(), NOW(), $24
            )
            ON CONFLICT (site_id, mac) DO UPDATE SET
                name = EXCLUDED.name,
                health = EXCLUDED.health,
                status = EXCLUDED.status,
                status_reason = EXCLUDED.status_reason,
                type = EXCLUDED.type,
                ipv4 = EXCLUDED.ipv4,
                ipv6 = EXCLUDED.ipv6,
                network = EXCLUDED.network,
                vlan_id = EXCLUDED.vlan_id,
                port = EXCLUDED.port,
                role = EXCLUDED.role,
                connected_device_serial = EXCLUDED.connected_device_serial,
                connected_to = EXCLUDED.connected_to,
                connected_since = EXCLUDED.connected_since,
                last_seen_at = EXCLUDED.last_seen_at,
                tunnel = EXCLUDED.tunnel,
                tunnel_id = EXCLUDED.tunnel_id,
                key_management = EXCLUDED.key_management,
                authentication = EXCLUDED.authentication,
                capabilities = EXCLUDED.capabilities,
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW(),
                synced_at = $24
        ''', [(*r, sync_timestamp) for r in records])

        skipped = len(clients) - len(records)
        return len(records), skipped

    async def _mark_removed_clients(
        self, conn, site_id: str, sync_timestamp: datetime
    ) -> int:
        """Mark clients not seen in this sync as REMOVED.

        Args:
            conn: Database connection
            site_id: Site ID to clean up
            sync_timestamp: Current sync timestamp

        Returns:
            Number of clients marked as removed
        """
        result = await conn.execute('''
            UPDATE clients
            SET status = 'REMOVED', updated_at = NOW()
            WHERE site_id = $1
              AND synced_at < $2
              AND (status IS NULL OR status != 'REMOVED')
        ''', site_id, sync_timestamp)

        try:
            return int(result.split()[-1])
        except (ValueError, IndexError, AttributeError):
            return 0

    async def _update_site_sync_time(self, conn, site_id: str) -> None:
        """Update the last_synced_at timestamp for a site.

        Args:
            conn: Database connection
            site_id: Site ID to update
        """
        await conn.execute('''
            UPDATE sites SET last_synced_at = NOW(), updated_at = NOW()
            WHERE site_id = $1
        ''', site_id)

    # ----------------------------------------
    # Sync Operations
    # ----------------------------------------

    async def _sync_site_clients(
        self, conn, site_id: str, site_name: Optional[str], sync_timestamp: datetime
    ) -> dict:
        """Sync all clients for a single site.

        Args:
            conn: Database connection
            site_id: Site ID to sync
            site_name: Site name for logging
            sync_timestamp: Current sync timestamp

        Returns:
            Stats dict for this site
        """
        display_name = site_name or site_id
        logger.info(f"Syncing clients for site: {display_name}")

        total_upserted = 0
        total_skipped = 0
        pages = 0

        try:
            async for page in self.client.paginate(
                self.ENDPOINT,
                config=CLIENTS_PAGINATION,
                params={"site-id": site_id},
            ):
                upserted, skipped = await self._upsert_clients_page(
                    conn, page, site_id, sync_timestamp
                )
                total_upserted += upserted
                total_skipped += skipped
                pages += 1

            # Mark removed clients
            removed = await self._mark_removed_clients(conn, site_id, sync_timestamp)
            if removed > 0:
                logger.info(f"Site {display_name}: marked {removed} clients as REMOVED")

            # Update site sync time
            await self._update_site_sync_time(conn, site_id)

            logger.info(
                f"Site {display_name}: {total_upserted} clients synced, "
                f"{total_skipped} skipped, {removed} removed"
            )

            return {
                "site_id": site_id,
                "site_name": site_name,
                "upserted": total_upserted,
                "skipped": total_skipped,
                "removed": removed,
                "pages": pages,
            }

        except GLPError as e:
            logger.error(f"API error for site {display_name}: {e}")
            return {
                "site_id": site_id,
                "site_name": site_name,
                "error": str(e),
                "upserted": total_upserted,
                "skipped": total_skipped,
            }

    async def sync_to_postgres(self) -> dict:
        """Sync all clients from Aruba Central.

        Process:
        1. Prime sites table from devices
        2. For each site, sync clients with pagination
        3. Mark removed clients per site
        4. Update site sync timestamps

        Returns:
            Dict with sync statistics

        Raises:
            ConnectionPoolError: If database pool is not available
            PartialSyncError: If sync completes with errors
        """
        if self.db_pool is None:
            raise ConnectionPoolError(
                "Database connection pool is required for clients sync"
            )

        error_collector = ErrorCollector()
        sync_timestamp = datetime.now(timezone.utc)
        site_stats = []

        total_upserted = 0
        total_skipped = 0
        total_removed = 0
        sites_synced = 0
        sites_failed = 0

        try:
            async with database_transaction(self.db_pool) as conn:
                # Step 1: Prime sites
                sites = await self._prime_sites(conn)

                if not sites:
                    logger.warning("No sites to sync clients for")
                    return {
                        "source": "aruba_central_clients",
                        "sites_synced": 0,
                        "total_upserted": 0,
                        "synced_at": sync_timestamp.isoformat(),
                    }

                # Step 2: Sync each site
                for site_id, site_name in sites:
                    try:
                        stats = await self._sync_site_clients(
                            conn, site_id, site_name, sync_timestamp
                        )
                        site_stats.append(stats)

                        if "error" in stats:
                            sites_failed += 1
                            error_collector.add(
                                SyncError(stats["error"]),
                                context={"site_id": site_id}
                            )
                        else:
                            sites_synced += 1
                            total_upserted += stats.get("upserted", 0)
                            total_skipped += stats.get("skipped", 0)
                            total_removed += stats.get("removed", 0)

                    except asyncpg.PostgresError as e:
                        sites_failed += 1
                        logger.error(f"Database error for site {site_id}: {e}")
                        error_collector.add(
                            DatabaseError(str(e), cause=e),
                            context={"site_id": site_id}
                        )

        except GLPError as e:
            logger.error(f"API error during clients sync: {e}")
            error_collector.add(e, context={"operation": "fetch"})

        except Exception as e:
            logger.error(f"Unexpected error during clients sync: {e}")
            error_collector.add(
                SyncError(f"Clients sync failed: {e}", cause=e),
                context={"operation": "sync"}
            )

        stats = {
            "source": "aruba_central_clients",
            "total_sites": len(sites) if 'sites' in locals() else 0,
            "sites_synced": sites_synced,
            "sites_failed": sites_failed,
            "total_upserted": total_upserted,
            "total_skipped": total_skipped,
            "total_removed": total_removed,
            "errors": error_collector.count(),
            "synced_at": sync_timestamp.isoformat(),
            "site_details": site_stats,
        }

        logger.info(
            f"Clients sync complete: {sites_synced}/{len(sites) if 'sites' in locals() else 0} sites, "
            f"{total_upserted} clients upserted, {total_removed} removed"
        )

        if error_collector.has_errors():
            raise PartialSyncError(
                f"Clients sync completed with {error_collector.count()} errors",
                succeeded=total_upserted,
                failed=error_collector.count(),
                errors=[e for e, _ in error_collector.get_errors()],
                details=stats,
            )

        return stats

    async def sync(self) -> dict:
        """Full sync: fetch all clients from Aruba Central.

        This is the main entry point for syncing Aruba Central clients.

        Returns:
            Sync statistics dictionary
        """
        logger.info(f"Starting Aruba Central clients sync at {datetime.utcnow().isoformat()}")
        return await self.sync_to_postgres()

    async def fetch_clients_for_site(self, site_id: str) -> list[dict]:
        """Fetch all clients for a specific site (for testing/export).

        Args:
            site_id: Site ID to fetch clients for

        Returns:
            List of client dictionaries
        """
        all_clients = []
        async for page in self.client.paginate(
            self.ENDPOINT,
            config=CLIENTS_PAGINATION,
            params={"site-id": site_id},
        ):
            all_clients.extend(page)
        return all_clients


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
            syncer = ArubaClientsSyncer(client=client)
            # Without db_pool, just test fetching
            print("Testing client fetch (no DB)...")

    asyncio.run(main())
