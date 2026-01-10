"""PostgreSQL adapter for subscription repository.

This adapter implements ISubscriptionRepository using asyncpg
to query the subscriptions table and derive region mappings.
"""

import logging
from typing import Optional
from uuid import UUID

import asyncpg

from ..domain.entities import RegionMapping, SubscriptionOption
from ..domain.ports import ISubscriptionRepository

logger = logging.getLogger(__name__)


class PostgresSubscriptionRepository(ISubscriptionRepository):
    """PostgreSQL implementation of ISubscriptionRepository."""

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with database connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    async def get_available_subscriptions(
        self,
        device_type: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[SubscriptionOption]:
        """Get subscriptions available for assignment.

        Args:
            device_type: Filter by device type (NETWORK, COMPUTE, STORAGE)
            model: Filter by device model (e.g., "6200F-24G-4SFP+")

        Returns:
            List of compatible subscription options
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    key,
                    subscription_type,
                    tier,
                    tier_description,
                    quantity,
                    available_quantity,
                    start_time,
                    end_time
                FROM subscriptions
                WHERE subscription_status = 'STARTED'
                AND available_quantity > 0
                ORDER BY subscription_type, tier, end_time
                """
            )

            subscriptions = [self._row_to_option(row) for row in rows]

            # Filter by device type if specified
            if device_type:
                subscriptions = [
                    s for s in subscriptions if s.is_compatible_with(device_type)
                ]

            # Filter by model if specified (checks model series compatibility)
            if model:
                subscriptions = [
                    s for s in subscriptions if s.is_compatible_with_model(model)
                ]

            return subscriptions

    async def get_region_mappings(self) -> list[RegionMapping]:
        """Get all available region mappings.

        In GreenLake, regions are tied to applications. We derive
        region mappings from devices that have both application_id
        and region set.
        """
        async with self.pool.acquire() as conn:
            # Get distinct application_id -> region mappings from devices
            rows = await conn.fetch(
                """
                SELECT DISTINCT
                    application_id,
                    region
                FROM devices
                WHERE application_id IS NOT NULL
                AND region IS NOT NULL
                AND NOT archived
                ORDER BY region
                """
            )

            mappings = []
            for row in rows:
                # Create a display name from the region
                region = row["region"]
                display_name = self._format_region_display_name(region)

                mappings.append(
                    RegionMapping(
                        application_id=row["application_id"],
                        region=region,
                        display_name=display_name,
                    )
                )

            return mappings

    async def get_subscription_by_id(
        self, subscription_id: UUID
    ) -> Optional[SubscriptionOption]:
        """Get a specific subscription by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    key,
                    subscription_type,
                    tier,
                    tier_description,
                    quantity,
                    available_quantity,
                    start_time,
                    end_time
                FROM subscriptions
                WHERE id = $1
                """,
                subscription_id,
            )

            if row is None:
                return None

            return self._row_to_option(row)

    def _row_to_option(self, row: asyncpg.Record) -> SubscriptionOption:
        """Convert database row to SubscriptionOption."""
        return SubscriptionOption(
            id=row["id"],
            key=row["key"],
            subscription_type=row["subscription_type"],
            tier=row["tier"],
            tier_description=row["tier_description"],
            quantity=row["quantity"],
            available_quantity=row["available_quantity"],
            start_time=row["start_time"],
            end_time=row["end_time"],
        )

    @staticmethod
    def _format_region_display_name(region: str) -> str:
        """Format a region code into a display name.

        Args:
            region: Region code like "us-west", "eu-central"

        Returns:
            Display name like "US West", "EU Central"
        """
        # Common region name mappings
        region_names = {
            "us-west": "US West",
            "us-east": "US East",
            "us-central": "US Central",
            "eu-west": "EU West",
            "eu-central": "EU Central",
            "ap-northeast": "Asia Pacific Northeast",
            "ap-southeast": "Asia Pacific Southeast",
            "ap-south": "Asia Pacific South",
            "ca-central": "Canada Central",
            "sa-east": "South America East",
        }

        # Try exact match first
        if region.lower() in region_names:
            return region_names[region.lower()]

        # Fall back to title case transformation
        return region.replace("-", " ").title()
