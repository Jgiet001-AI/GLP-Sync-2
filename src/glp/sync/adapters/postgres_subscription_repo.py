"""PostgreSQL repository adapter for subscription persistence.

This adapter implements ISubscriptionRepository and handles all database operations
for subscriptions, including the optimized bulk UPSERT and tag sync.

The bulk operations here preserve the performance optimizations from the original
SubscriptionSyncer.
"""

import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..domain.entities import Subscription, SubscriptionTag
from ..domain.ports import ISubscriptionRepository

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class PostgresSubscriptionRepository(ISubscriptionRepository):
    """PostgreSQL implementation of ISubscriptionRepository.

    Provides optimized bulk operations for subscription persistence:
    - UPSERT (INSERT ON CONFLICT) for subscriptions
    - Bulk DELETE with ANY() for tags
    - executemany() for bulk inserts

    All operations can be run within a single transaction for atomicity.
    """

    def __init__(self, pool: "asyncpg.Pool"):
        """Initialize the repository.

        Args:
            pool: asyncpg connection pool for database operations
        """
        self.pool = pool

    async def upsert_subscriptions(self, subscriptions: list[Subscription]) -> int:
        """Bulk upsert subscriptions using INSERT ON CONFLICT.

        This is the optimized UPSERT that eliminates N SELECT queries.
        All subscriptions are inserted/updated in a single batch operation.

        Args:
            subscriptions: List of Subscription entities to upsert

        Returns:
            Number of subscriptions upserted
        """
        if not subscriptions:
            return 0

        # Convert subscriptions to record tuples
        records = [self._subscription_to_record(s) for s in subscriptions]

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
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
                """,
                records,
            )

        return len(records)

    async def sync_tags(
        self,
        subscription_ids: list[UUID],
        tags: list[SubscriptionTag],
    ) -> None:
        """Sync subscription tags (delete old, insert new).

        Uses bulk DELETE with ANY() followed by bulk INSERT.

        Args:
            subscription_ids: List of subscription IDs to sync tags for
            tags: List of SubscriptionTag entities to insert
        """
        if not subscription_ids:
            return

        # Import here to avoid circular imports
        from ...api.database import database_transaction

        async with database_transaction(self.pool) as conn:
            # Delete all existing tags for these subscriptions
            await conn.execute(
                "DELETE FROM subscription_tags WHERE subscription_id = ANY($1)",
                [str(s) for s in subscription_ids],
            )

            # Insert new tags
            if tags:
                records = [
                    (str(t.subscription_id), t.tag_key, t.tag_value)
                    for t in tags
                ]
                await conn.executemany(
                    """
                    INSERT INTO subscription_tags (subscription_id, tag_key, tag_value)
                    VALUES ($1, $2, $3)
                    """,
                    records,
                )

    def _subscription_to_record(self, subscription: Subscription) -> tuple[Any, ...]:
        """Convert Subscription entity to database record tuple.

        Args:
            subscription: Subscription entity

        Returns:
            Tuple of values for database insertion
        """
        return (
            str(subscription.id),
            subscription.key,
            subscription.resource_type,
            subscription.subscription_type,
            subscription.subscription_status,
            subscription.quantity,
            subscription.available_quantity,
            subscription.sku,
            subscription.sku_description,
            subscription.start_time,
            subscription.end_time,
            subscription.tier,
            subscription.tier_description,
            subscription.product_type,
            subscription.is_eval,
            subscription.contract,
            subscription.quote,
            subscription.po,
            subscription.reseller_po,
            subscription.created_at,
            subscription.updated_at,
            json.dumps(subscription.raw_data),
        )
