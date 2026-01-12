"""Sync Subscriptions Use Case - Orchestrates the subscription sync workflow.

This use case implements the business logic for syncing subscriptions from
the GreenLake API to the database. It depends on ports (interfaces)
for all external operations, making it fully testable without
infrastructure.

Workflow:
1. Fetch all subscriptions from API (via ISubscriptionAPI)
2. Map raw responses to domain entities (via ISubscriptionFieldMapper)
3. Extract related data (tags)
4. Upsert subscriptions to database (via ISubscriptionRepository)
5. Sync related data (tags)
6. Return sync statistics
"""

import logging
from datetime import datetime, timezone

from ..domain.entities import (
    Subscription,
    SubscriptionTag,
    SyncResult,
)
from ..domain.ports import ISubscriptionAPI, ISubscriptionFieldMapper, ISubscriptionRepository

logger = logging.getLogger(__name__)


class SyncSubscriptionsUseCase:
    """Orchestrates the subscription sync workflow.

    This use case follows the Clean Architecture pattern:
    - Depends only on port interfaces, not concrete implementations
    - Contains business logic for the sync workflow
    - Returns domain objects (SyncResult), not infrastructure types

    Example:
        use_case = SyncSubscriptionsUseCase(
            subscription_api=GLPSubscriptionAPI(client),
            subscription_repo=PostgresSubscriptionRepository(pool),
            field_mapper=SubscriptionFieldMapper(),
        )
        result = await use_case.execute()
    """

    def __init__(
        self,
        subscription_api: ISubscriptionAPI,
        subscription_repo: ISubscriptionRepository,
        field_mapper: ISubscriptionFieldMapper,
    ):
        """Initialize the use case with its dependencies.

        Args:
            subscription_api: Port for fetching subscriptions from API
            subscription_repo: Port for persisting subscriptions to database
            field_mapper: Port for transforming between formats
        """
        self.api = subscription_api
        self.repo = subscription_repo
        self.mapper = field_mapper

    async def execute(self) -> SyncResult:
        """Execute the subscription sync workflow.

        Steps:
        1. Fetch all subscriptions from API
        2. Map to domain entities
        3. Extract tags
        4. Upsert subscriptions to database
        5. Sync tags

        Returns:
            SyncResult with statistics about the sync operation
        """
        started_at = datetime.now(timezone.utc)
        errors: list[str] = []

        logger.info(f"Starting subscription sync at {started_at.isoformat()}")

        # Step 1: Fetch from API
        try:
            raw_subscriptions = await self.api.fetch_all()
            logger.info(f"Fetched {len(raw_subscriptions)} subscriptions from API")
        except Exception as e:
            logger.error(f"Failed to fetch subscriptions from API: {e}")
            return SyncResult(
                success=False,
                total=0,
                upserted=0,
                errors=1,
                synced_at=started_at,
                error_details=[f"API fetch failed: {e}"],
            )

        if not raw_subscriptions:
            logger.info("No subscriptions to sync")
            return SyncResult(
                success=True,
                total=0,
                upserted=0,
                errors=0,
                synced_at=started_at,
            )

        # Step 2: Map to domain entities
        subscriptions: list[Subscription] = []
        all_tags: list[SubscriptionTag] = []

        for raw in raw_subscriptions:
            try:
                subscription = self.mapper.map_to_entity(raw)
                subscriptions.append(subscription)

                # Extract tags
                tags = self.mapper.extract_tags(subscription, raw)
                all_tags.extend(tags)

            except Exception as e:
                sub_id = raw.get("id", "unknown")
                error_msg = f"Mapping error for subscription {sub_id}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

        logger.info(
            f"Mapped {len(subscriptions)} subscriptions, "
            f"{len(all_tags)} tags"
        )

        # Step 3: Upsert subscriptions to database
        upserted = 0
        try:
            upserted = await self.repo.upsert_subscriptions(subscriptions)
            logger.info(f"Upserted {upserted} subscriptions to database")
        except Exception as e:
            error_msg = f"Database upsert failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Step 4: Sync tags
        try:
            subscription_ids = [s.id for s in subscriptions]
            await self.repo.sync_tags(subscription_ids, all_tags)
            logger.info("Synced subscription tags")
        except Exception as e:
            error_msg = f"Tag sync failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Build result
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()

        logger.info(
            f"Subscription sync completed in {duration:.2f}s: "
            f"{upserted} upserted, {len(errors)} errors"
        )

        return SyncResult(
            success=len(errors) == 0,
            total=len(raw_subscriptions),
            upserted=upserted,
            errors=len(errors),
            synced_at=started_at,
            error_details=errors,
        )

    async def execute_streaming(self) -> SyncResult:
        """Execute subscription sync with streaming to minimize memory usage.

        This method processes subscriptions page by page instead of loading all
        records into memory at once. Ideal for large subscription counts.

        The streaming approach:
        1. Fetches one page of subscriptions at a time via fetch_paginated()
        2. Maps and upserts each page immediately
        3. Syncs related data (tags) per page
        4. Keeps only current page in memory

        Returns:
            SyncResult with statistics about the sync operation
        """
        started_at = datetime.now(timezone.utc)
        errors: list[str] = []
        total_fetched = 0
        total_upserted = 0

        logger.info(f"Starting streaming subscription sync at {started_at.isoformat()}")

        try:
            async for page in self.api.fetch_paginated():
                page_size = len(page)
                total_fetched += page_size

                # Map page to entities
                subscriptions: list[Subscription] = []
                tags: list[SubscriptionTag] = []

                for raw in page:
                    try:
                        subscription = self.mapper.map_to_entity(raw)
                        subscriptions.append(subscription)
                        tags.extend(self.mapper.extract_tags(subscription, raw))
                    except Exception as e:
                        sub_id = raw.get("id", "unknown")
                        error_msg = f"Mapping error for subscription {sub_id}: {e}"
                        logger.warning(error_msg)
                        errors.append(error_msg)

                # Upsert this page immediately
                if subscriptions:
                    try:
                        upserted = await self.repo.upsert_subscriptions(subscriptions)
                        total_upserted += upserted

                        # Sync tags for this page
                        subscription_ids = [s.id for s in subscriptions]
                        await self.repo.sync_tags(subscription_ids, tags)

                    except Exception as e:
                        error_msg = f"Database operation failed for page: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

                logger.debug(
                    f"Processed page: {page_size} subscriptions, {total_fetched} total so far"
                )

        except Exception as e:
            error_msg = f"Streaming sync failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Build result
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()

        logger.info(
            f"Streaming subscription sync completed in {duration:.2f}s: "
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

    @staticmethod
    def summarize_by_status(subscriptions: list[Subscription]) -> dict[str, int]:
        """Summarize subscriptions by status.

        This is a business logic helper that can be used after fetching
        to get a quick status breakdown.

        Args:
            subscriptions: List of Subscription entities

        Returns:
            Dict mapping status to count
        """
        summary: dict[str, int] = {}
        for sub in subscriptions:
            status = sub.subscription_status or "UNKNOWN"
            summary[status] = summary.get(status, 0) + 1
        return summary

    @staticmethod
    def summarize_by_type(subscriptions: list[Subscription]) -> dict[str, int]:
        """Summarize subscriptions by type.

        This is a business logic helper that can be used after fetching
        to get a quick type breakdown.

        Args:
            subscriptions: List of Subscription entities

        Returns:
            Dict mapping subscription type to count
        """
        summary: dict[str, int] = {}
        for sub in subscriptions:
            sub_type = sub.subscription_type or "UNKNOWN"
            summary[sub_type] = summary.get(sub_type, 0) + 1
        return summary
