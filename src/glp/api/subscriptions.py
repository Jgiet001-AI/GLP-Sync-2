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
from datetime import datetime, timedelta
from typing import Optional

from .client import GLPClient, SUBSCRIPTIONS_PAGINATION, PaginationConfig


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
    ):
        """Initialize SubscriptionSyncer.
        
        Args:
            client: Configured GLPClient instance
            db_pool: asyncpg connection pool (optional for JSON-only mode)
        """
        self.client = client
        self.db_pool = db_pool
    
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
        
        print(f"[SubscriptionSyncer] Fetching subscriptions expiring before {cutoff_iso}")
        
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
        """
        valid_statuses = {"STARTED", "ENDED", "SUSPENDED", "CANCELLED", "LOCKED", "NOT_STARTED"}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")
        
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
    # Database Operations
    # ----------------------------------------
    
    async def sync_to_postgres(self, subscriptions: list[dict]) -> dict:
        """Upsert subscriptions to PostgreSQL.
        
        NOTE: This assumes a 'subscriptions' table exists. You'll need to
        create the schema first. See db/subscriptions_schema.sql
        
        Args:
            subscriptions: List of subscription dictionaries from API
        
        Returns:
            Dict with sync statistics
        """
        if self.db_pool is None:
            raise ValueError("Database connection pool is required")
        
        inserted = 0
        updated = 0
        errors = 0
        
        async with self.db_pool.acquire() as conn:
            for sub in subscriptions:
                try:
                    exists = await conn.fetchval(
                        "SELECT 1 FROM subscriptions WHERE id = $1",
                        sub["id"]
                    )
                    
                    if exists:
                        await self._update_subscription(conn, sub)
                        updated += 1
                    else:
                        await self._insert_subscription(conn, sub)
                        inserted += 1
                        
                except Exception as e:
                    errors += 1
                    print(f"[SubscriptionSyncer] Error syncing subscription {sub.get('id')}: {e}")
        
        return {
            "total": len(subscriptions),
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
            "synced_at": datetime.utcnow().isoformat(),
        }
    
    async def _insert_subscription(self, conn, sub: dict):
        """Insert a single subscription into PostgreSQL with all API fields."""
        await conn.execute('''
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
        ''',
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
        )
        
        # Sync tags to subscription_tags table
        await self._sync_tags(conn, sub["id"], sub.get("tags") or {})
    
    async def _update_subscription(self, conn, sub: dict):
        """Update a single subscription in PostgreSQL with all API fields."""
        await conn.execute('''
            UPDATE subscriptions SET
                key = $2,
                resource_type = $3,
                subscription_type = $4,
                subscription_status = $5,
                quantity = $6,
                available_quantity = $7,
                sku = $8,
                sku_description = $9,
                start_time = $10,
                end_time = $11,
                tier = $12,
                tier_description = $13,
                product_type = $14,
                is_eval = $15,
                contract = $16,
                quote = $17,
                po = $18,
                reseller_po = $19,
                updated_at = $20,
                raw_data = $21::jsonb,
                synced_at = NOW()
            WHERE id = $1
        ''',
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
            self._parse_timestamp(sub.get("updatedAt")),
            json.dumps(sub),
        )
        
        # Sync tags to subscription_tags table
        await self._sync_tags(conn, sub["id"], sub.get("tags") or {})
    
    async def _sync_tags(self, conn, subscription_id: str, tags: dict):
        """Sync subscription tags to the subscription_tags table.
        
        Strategy: Delete all existing, insert fresh. This ensures we capture
        any tags that were removed from the subscription.
        
        Args:
            conn: Database connection
            subscription_id: UUID of the subscription
            tags: Dict of tag key-value pairs from API
        """
        # Delete existing tags for this subscription
        await conn.execute(
            'DELETE FROM subscription_tags WHERE subscription_id = $1',
            subscription_id
        )
        
        # Insert new tags
        for key, value in tags.items():
            await conn.execute('''
                INSERT INTO subscription_tags (subscription_id, tag_key, tag_value)
                VALUES ($1, $2, $3)
            ''', subscription_id, key, value)
    
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
        
        Returns:
            Sync statistics dictionary
        """
        print(f"[SubscriptionSyncer] Starting sync at {datetime.utcnow().isoformat()}")
        
        subscriptions = await self.fetch_all_subscriptions()
        
        if self.db_pool:
            stats = await self.sync_to_postgres(subscriptions)
        else:
            stats = {
                "total": len(subscriptions),
                "note": "No database configured, fetch only",
            }
        
        print(f"[SubscriptionSyncer] Sync complete: {stats}")
        return stats
    
    async def fetch_and_save_json(self, filepath: str = "subscriptions.json") -> int:
        """Fetch all subscriptions and save to JSON file.
        
        Args:
            filepath: Output file path
        
        Returns:
            Number of subscriptions saved
        """
        subscriptions = await self.fetch_all_subscriptions()
        
        with open(filepath, "w") as f:
            json.dump(subscriptions, f, indent=2)
        
        print(f"[SubscriptionSyncer] Saved {len(subscriptions):,} subscriptions to {filepath}")
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