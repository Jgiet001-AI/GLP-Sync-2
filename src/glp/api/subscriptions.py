#!/usr/bin/env python3
"""HPE GreenLake Subscription Management Synchronization.

This module provides subscription inventory synchronization from the HPE
GreenLake Platform API to PostgreSQL.

API Details:
    - Endpoint: GET /subscriptions/v1/subscriptions
    - Rate Limit: 60 requests/minute
    - Page Size: 50 max
    - Supports OData-style filtering

Architecture:
    SubscriptionSyncer composes GLPClient for HTTP concerns and focuses on:
    - Subscription-specific field mappings
    - Database schema operations
    - Filtering logic (expiring soon, by type, etc.)

Example:
    async with GLPClient(token_manager) as client:
        syncer = SubscriptionSyncer(client=client, db_pool=pool)

        # Fetch all subscriptions
        subs = await syncer.fetch_all_subscriptions()

        # Fetch only expiring subscriptions (using OData filter)
        expiring = await syncer.fetch_expiring_soon(days=90)

Author: HPE GreenLake Team
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from .client import SUBSCRIPTIONS_PAGINATION, GLPClient
from .database import database_transaction
from .exceptions import (
    ConnectionPoolError,
    DatabaseError,
    ErrorCollector,
    GLPError,
    IntegrityError,
    PartialSyncError,
    SyncError,
    ValidationError,
)

# Clean Architecture imports
from ..sync.adapters import GLPSubscriptionAPI, PostgresSubscriptionRepository, SubscriptionFieldMapper
from ..sync.use_cases import SyncSubscriptionsUseCase

logger = logging.getLogger(__name__)


class SubscriptionSyncer:
    """Subscription synchronizer for GreenLake Platform.

    Fetches subscription data via GLPClient and optionally syncs to PostgreSQL.
    Supports rich filtering via the Subscriptions API's OData-style syntax.

    Attributes:
        client: GLPClient instance for API communication
        db_pool: asyncpg connection pool for database operations

    Filtering Examples:
        The Subscriptions API supports powerful filters:

        - By status: filter=subscriptionStatus eq 'STARTED'
        - By type: filter=subscriptionType eq 'CENTRAL_SWITCH'
        - By date: filter=endTime lt '2025-06-01T00:00:00.000Z'
        - Combined: filter=subscriptionStatus eq 'STARTED' and endTime lt '2025-06-01'
    """

    # API endpoint for subscriptions
    ENDPOINT = "/subscriptions/v1/subscriptions"

    def __init__(
        self,
        client: GLPClient,
        db_pool=None,
        *,
        use_clean_architecture: bool = True,
        use_streaming: bool = False,
    ):
        """Initialize SubscriptionSyncer.

        Args:
            client: Configured GLPClient instance
            db_pool: asyncpg connection pool (optional for JSON-only mode)
            use_clean_architecture: If True, use the new Clean Architecture
                                   use case internally (default: True)
            use_streaming: If True, use streaming mode for memory-efficient
                          sync. Processes page by page instead of loading
                          all subscriptions into memory.
        """
        self.client = client
        self.db_pool = db_pool
        self._use_clean_architecture = use_clean_architecture
        self._use_streaming = use_streaming

        # Create use case with adapters if db_pool is provided
        self._use_case: SyncSubscriptionsUseCase | None = None
        if db_pool and use_clean_architecture:
            self._use_case = SyncSubscriptionsUseCase(
                subscription_api=GLPSubscriptionAPI(client),
                subscription_repo=PostgresSubscriptionRepository(db_pool),
                field_mapper=SubscriptionFieldMapper(),
            )

    # ----------------------------------------
    # Fetching: Basic
    # ----------------------------------------

    async def fetch_all_subscriptions(self) -> list[dict]:
        """Fetch all subscriptions from GreenLake API.

        Returns:
            List of subscription dictionaries from the API.
        """
        return await self.client.fetch_all(
            self.ENDPOINT,
            config=SUBSCRIPTIONS_PAGINATION,
        )

    async def fetch_subscriptions_generator(self):
        """Yield subscriptions page by page (memory efficient).

        Use this for very large datasets where you want to process
        subscriptions as they arrive rather than loading all into memory.

        Yields:
            Lists of subscription dictionaries, one page at a time.
        """
        async for page in self.client.paginate(
            self.ENDPOINT,
            config=SUBSCRIPTIONS_PAGINATION,
        ):
            yield page

    async def fetch_subscription_by_id(self, subscription_id: str) -> dict:
        """Fetch a single subscription by ID.

        Args:
            subscription_id: UUID of the subscription

        Returns:
            Subscription dictionary
        """
        return await self.client.get(f"{self.ENDPOINT}/{subscription_id}")

    # ----------------------------------------
    # Fetching: Filtered (OData-style)
    # ----------------------------------------

    async def fetch_with_filter(
        self,
        filter_expr: str,
        sort: Optional[str] = None,
    ) -> list[dict]:
        """Fetch subscriptions with OData-style filter.

        Args:
            filter_expr: OData filter expression
                Examples:
                - "subscriptionStatus eq 'STARTED'"
                - "endTime lt '2025-06-01T00:00:00.000Z'"
                - "subscriptionType in 'CENTRAL_SWITCH', 'CENTRAL_AP'"
            sort: Sort expression (e.g., "endTime asc", "key desc")

        Returns:
            List of matching subscriptions
        """
        params = {"filter": filter_expr}
        if sort:
            params["sort"] = sort

        return await self.client.fetch_all(
            self.ENDPOINT,
            config=SUBSCRIPTIONS_PAGINATION,
            params=params,
        )

    async def fetch_expiring_soon(self, days: int = 90) -> list[dict]:
        """Fetch subscriptions expiring within N days.

        This uses the API's filter capability to only fetch relevant
        subscriptions, rather than fetching everything and filtering locally.

        Args:
            days: Number of days to look ahead (default: 90)

        Returns:
            List of subscriptions expiring within the specified window
        """
        # Calculate the cutoff date
        cutoff = datetime.utcnow() + timedelta(days=days)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT00:00:00.000Z")
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT00:00:00.000Z")

        # Build OData filter:
        # - Subscription is active (STARTED)
        # - End time is in the future (not already expired)
        # - End time is before our cutoff
        filter_expr = (
            f"subscriptionStatus eq 'STARTED' "
            f"and endTime gt '{now_iso}' "
            f"and endTime lt '{cutoff_iso}'"
        )

        logger.info(f"Fetching subscriptions expiring before {cutoff_iso}")

        return await self.fetch_with_filter(
            filter_expr=filter_expr,
            sort="endTime asc",  # Soonest expiring first
        )

    async def fetch_by_status(self, status: str) -> list[dict]:
        """Fetch subscriptions by status.

        Args:
            status: One of STARTED, ENDED, SUSPENDED, CANCELLED, LOCKED, NOT_STARTED

        Returns:
            List of subscriptions with the specified status

        Raises:
            ValidationError: If status is invalid
        """
        valid_statuses = {"STARTED", "ENDED", "SUSPENDED", "CANCELLED", "LOCKED", "NOT_STARTED"}
        if status not in valid_statuses:
            raise ValidationError(
                f"Invalid status: {status}. Must be one of {valid_statuses}",
                field="status",
                status_code=400,
            )

        return await self.fetch_with_filter(f"subscriptionStatus eq '{status}'")

    async def fetch_by_type(self, subscription_type: str) -> list[dict]:
        """Fetch subscriptions by type.

        Args:
            subscription_type: e.g., CENTRAL_SWITCH, CENTRAL_AP, CENTRAL_STORAGE

        Returns:
            List of subscriptions of the specified type
        """
        return await self.fetch_with_filter(f"subscriptionType eq '{subscription_type}'")

    # ----------------------------------------
    # Database Operations (Optimized with Bulk Operations)
    # ----------------------------------------

    async def sync_to_postgres(self, subscriptions: list[dict]) -> dict:
        """Upsert subscriptions to PostgreSQL using optimized bulk operations.

        Performance optimizations:
        1. Uses UPSERT (INSERT ON CONFLICT) - eliminates N SELECT queries
        2. Bulk DELETE with ANY() - single query for all subscription IDs
        3. executemany() for bulk inserts - batched tags

        Args:
            subscriptions: List of subscription dictionaries from API

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

        if not subscriptions:
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
                # Step 1: Bulk UPSERT all subscriptions
                subscription_records = self._prepare_subscription_records(subscriptions)
                upserted = await self._bulk_upsert_subscriptions(conn, subscription_records)

                # Step 2: Collect all subscription IDs for bulk operations
                subscription_ids = [s["id"] for s in subscriptions]

                # Step 3: Bulk DELETE existing tags
                await conn.execute(
                    'DELETE FROM subscription_tags WHERE subscription_id = ANY($1)',
                    subscription_ids
                )

                # Step 4: Bulk INSERT tags
                tag_records = self._prepare_tag_records(subscriptions)
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
            "total": len(subscriptions),
            "upserted": upserted,
            "errors": error_collector.count(),
            "synced_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Subscription sync complete: {upserted} upserted, "
            f"{error_collector.count()} errors"
        )

        if error_collector.has_errors():
            raise PartialSyncError(
                f"Subscription sync completed with {error_collector.count()} errors",
                succeeded=upserted,
                failed=error_collector.count(),
                errors=[e for e, _ in error_collector.get_errors()],
                details=stats,
            )

        return stats

    def _prepare_subscription_records(self, subscriptions: list[dict]) -> list[tuple]:
        """Prepare subscription records for bulk insert.

        Args:
            subscriptions: List of subscription dictionaries from API

        Returns:
            List of tuples ready for executemany()
        """
        records = []
        for sub in subscriptions:
            records.append((
                sub["id"],
                sub.get("key"),
                sub.get("type"),  # resource_type
                sub.get("subscriptionType"),
                sub.get("subscriptionStatus"),
                int(sub.get("quantity", 0)) if sub.get("quantity") else None,
                int(sub.get("availableQuantity", 0)) if sub.get("availableQuantity") else None,
                sub.get("sku"),
                sub.get("skuDescription"),
                self._parse_timestamp(sub.get("startTime")),
                self._parse_timestamp(sub.get("endTime")),
                sub.get("tier"),
                sub.get("tierDescription"),
                sub.get("productType"),
                sub.get("isEval", False),
                sub.get("contract"),
                sub.get("quote"),
                sub.get("po"),
                sub.get("resellerPo"),
                self._parse_timestamp(sub.get("createdAt")),
                self._parse_timestamp(sub.get("updatedAt")),
                json.dumps(sub),
            ))
        return records

    async def _bulk_upsert_subscriptions(self, conn, records: list[tuple]) -> int:
        """Bulk upsert subscriptions using INSERT ON CONFLICT.

        Args:
            conn: Database connection
            records: List of subscription record tuples

        Returns:
            Number of rows affected
        """
        await conn.executemany('''
            INSERT INTO subscriptions (
                id, key, resource_type, subscription_type, subscription_status,
                quantity, available_quantity, sku, sku_description,
                start_time, end_time, tier, tier_description,
                product_type, is_eval, contract, quote, po, reseller_po,
                created_at, updated_at, raw_data, synced_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19,
                $20, $21, $22::jsonb, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                key = EXCLUDED.key,
                resource_type = EXCLUDED.resource_type,
                subscription_type = EXCLUDED.subscription_type,
                subscription_status = EXCLUDED.subscription_status,
                quantity = EXCLUDED.quantity,
                available_quantity = EXCLUDED.available_quantity,
                sku = EXCLUDED.sku,
                sku_description = EXCLUDED.sku_description,
                start_time = EXCLUDED.start_time,
                end_time = EXCLUDED.end_time,
                tier = EXCLUDED.tier,
                tier_description = EXCLUDED.tier_description,
                product_type = EXCLUDED.product_type,
                is_eval = EXCLUDED.is_eval,
                contract = EXCLUDED.contract,
                quote = EXCLUDED.quote,
                po = EXCLUDED.po,
                reseller_po = EXCLUDED.reseller_po,
                updated_at = EXCLUDED.updated_at,
                raw_data = EXCLUDED.raw_data,
                synced_at = NOW()
        ''', records)

        return len(records)

    def _prepare_tag_records(self, subscriptions: list[dict]) -> list[tuple]:
        """Prepare tag records for bulk insert.

        Args:
            subscriptions: List of subscription dictionaries

        Returns:
            List of (subscription_id, tag_key, tag_value) tuples
        """
        records = []
        for sub in subscriptions:
            subscription_id = sub["id"]
            tags = sub.get("tags") or {}
            for key, value in tags.items():
                records.append((subscription_id, key, value))
        return records

    async def _bulk_insert_tags(self, conn, records: list[tuple]) -> None:
        """Bulk insert subscription tags.

        Args:
            conn: Database connection
            records: List of tag record tuples
        """
        await conn.executemany('''
            INSERT INTO subscription_tags (subscription_id, tag_key, tag_value)
            VALUES ($1, $2, $3)
        ''', records)

    @staticmethod
    def _parse_timestamp(iso_string: Optional[str]) -> Optional[datetime]:
        """Parse ISO timestamp string to datetime."""
        if not iso_string:
            return None
        return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))

    # ----------------------------------------
    # High-Level Operations
    # ----------------------------------------

    async def sync(self) -> dict:
        """Full sync: fetch all subscriptions and upsert to database.

        When use_clean_architecture=True (default), delegates to SyncSubscriptionsUseCase.
        Otherwise, uses the legacy implementation for backward compatibility.

        When use_streaming=True, uses memory-efficient streaming mode that
        processes subscriptions page by page.

        Returns:
            Sync statistics dictionary

        Raises:
            GLPError: If API fetch fails
            PartialSyncError: If some subscriptions failed to sync
        """
        # Use Clean Architecture use case if available
        if self._use_case:
            if self._use_streaming:
                logger.info("Using Clean Architecture use case for subscription sync (streaming mode)")
                result = await self._use_case.execute_streaming()
            else:
                logger.info("Using Clean Architecture use case for subscription sync")
                result = await self._use_case.execute()

            # Convert SyncResult to backward-compatible dict format
            stats = result.to_dict()

            # Raise PartialSyncError if there were errors (for backward compatibility)
            if not result.success and result.error_details:
                raise PartialSyncError(
                    f"Subscription sync completed with {result.errors} errors",
                    succeeded=result.upserted,
                    failed=result.errors,
                    errors=result.error_details,
                    details=stats,
                )

            return stats

        # Legacy implementation (when use_clean_architecture=False or no db_pool)
        logger.info(f"Starting subscription sync at {datetime.utcnow().isoformat()}")

        try:
            subscriptions = await self.fetch_all_subscriptions()
        except GLPError:
            logger.error("Failed to fetch subscriptions from API")
            raise

        if self.db_pool:
            try:
                stats = await self.sync_to_postgres(subscriptions)
            except PartialSyncError as e:
                # PartialSyncError contains stats, log and return them
                logger.warning(f"Partial sync: {e.succeeded} succeeded, {e.failed} failed")
                return e.details
        else:
            stats = {
                "total": len(subscriptions),
                "note": "No database configured, fetch only",
            }

        logger.info(f"Subscription sync complete: {stats}")
        return stats

    async def fetch_and_save_json(self, filepath: str = "subscriptions.json") -> int:
        """Fetch all subscriptions and save to JSON file.

        Args:
            filepath: Output file path

        Returns:
            Number of subscriptions saved

        Raises:
            GLPError: If API fetch fails
            IOError: If file cannot be written
        """
        import aiofiles

        subscriptions = await self.fetch_all_subscriptions()

        async with aiofiles.open(filepath, "w") as f:
            await f.write(json.dumps(subscriptions, indent=2))

        logger.info(f"Saved {len(subscriptions):,} subscriptions to {filepath}")
        return len(subscriptions)

    # ----------------------------------------
    # Business Logic Helpers
    # ----------------------------------------

    def summarize_by_status(self, subscriptions: list[dict]) -> dict[str, int]:
        """Summarize subscriptions by status.

        Args:
            subscriptions: List of subscription dicts

        Returns:
            Dict mapping status to count
        """
        summary = {}
        for sub in subscriptions:
            status = sub.get("subscriptionStatus", "UNKNOWN")
            summary[status] = summary.get(status, 0) + 1
        return summary

    def summarize_by_type(self, subscriptions: list[dict]) -> dict[str, int]:
        """Summarize subscriptions by type.

        Args:
            subscriptions: List of subscription dicts

        Returns:
            Dict mapping subscription type to count
        """
        summary = {}
        for sub in subscriptions:
            sub_type = sub.get("subscriptionType", "UNKNOWN")
            summary[sub_type] = summary.get(sub_type, 0) + 1
        return summary


# ============================================
# Standalone Test
# ============================================

if __name__ == "__main__":
    import asyncio

    from .auth import TokenManager
    from .client import GLPClient

    async def main():
        """Demo: Pick ONE of the options below to test."""
        token_manager = TokenManager()

        async with GLPClient(token_manager) as client:
            syncer = SubscriptionSyncer(client=client)

            # --- OPTION 1: Fetch all and save to JSON ---
            await syncer.fetch_and_save_json("subscriptions_backup.json")

            # --- OPTION 2: Fetch only expiring soon (uncomment to use) ---
            # expiring = await syncer.fetch_expiring_soon(days=90)
            # print(f"Found {len(expiring)} subscriptions expiring in next 90 days")

            # --- OPTION 3: Fetch and summarize (uncomment to use) ---
            # all_subs = await syncer.fetch_all_subscriptions()
            # print("By status:", syncer.summarize_by_status(all_subs))
            # print("By type:", syncer.summarize_by_type(all_subs))

    asyncio.run(main())
