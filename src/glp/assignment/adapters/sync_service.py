"""Sync service adapter.

This adapter wraps the existing DeviceSyncer and SubscriptionSyncer
to implement the ISyncService interface.

Field Mapping:
    The syncers return: {total, inserted, updated, errors, synced_at}
    This adapter normalizes to: {records_fetched, records_inserted, records_updated, ...}
"""

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from ..domain.ports import ISyncService

if TYPE_CHECKING:
    import asyncpg
    from ...api.devices import DeviceSyncer
    from ...api.subscriptions import SubscriptionSyncer

logger = logging.getLogger(__name__)


def _normalize_sync_result(result: dict) -> dict:
    """Normalize sync result field names.

    The syncers return: {total, inserted, updated, errors, synced_at}
    We normalize to: {records_fetched, records_inserted, records_updated, ...}

    Args:
        result: Raw result from syncer

    Returns:
        Normalized result with consistent field names
    """
    return {
        "records_fetched": result.get("total", 0),
        "records_inserted": result.get("inserted", 0),
        "records_updated": result.get("updated", 0),
        "errors": result.get("errors", 0),
        "synced_at": result.get("synced_at"),
        # Keep original fields for backward compatibility
        "total": result.get("total", 0),
        "inserted": result.get("inserted", 0),
        "updated": result.get("updated", 0),
    }


class DeviceSyncerAdapter(ISyncService):
    """Adapter wrapping existing syncers.

    This adapter:
    - Triggers device and subscription syncs
    - Normalizes result field names
    - Records sync history in database
    - Returns sync statistics
    """

    def __init__(
        self,
        device_syncer: "DeviceSyncer",
        subscription_syncer: "SubscriptionSyncer",
        db_pool: Optional["asyncpg.Pool"] = None,
    ):
        """Initialize with existing syncers.

        Args:
            device_syncer: Configured DeviceSyncer instance
            subscription_syncer: Configured SubscriptionSyncer instance
            db_pool: Optional database pool for recording sync history
        """
        self.device_syncer = device_syncer
        self.subscription_syncer = subscription_syncer
        self.db_pool = db_pool

    async def _record_sync_history(
        self,
        resource_type: str,
        started_at: datetime,
        result: dict,
        status: str,
        duration_ms: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Record sync history in database."""
        if not self.db_pool:
            return

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO sync_history (
                        resource_type, started_at, completed_at, status,
                        records_fetched, records_inserted, records_updated,
                        records_errors, duration_ms, error_message
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    resource_type,
                    started_at,
                    datetime.now(timezone.utc),
                    status,
                    result.get("records_fetched", 0),
                    result.get("records_inserted", 0),
                    result.get("records_updated", 0),
                    result.get("errors", 0),
                    duration_ms,
                    error_message,
                )
        except Exception as e:
            logger.warning(f"Failed to record sync history: {e}")

    async def sync_devices(self) -> dict:
        """Sync all devices from GreenLake to database."""
        logger.info("Starting device sync...")
        started_at = datetime.now(timezone.utc)
        start_time = time.time()

        try:
            raw_result = await self.device_syncer.sync()
            result = _normalize_sync_result(raw_result)
            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Device sync complete: {result['records_fetched']} fetched, "
                f"{result['records_inserted']} inserted, "
                f"{result['records_updated']} updated"
            )

            # Record success in history
            await self._record_sync_history(
                "devices", started_at, result, "success", duration_ms
            )

            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Device sync failed: {e}")

            # Record failure in history
            await self._record_sync_history(
                "devices", started_at, {}, "failed", duration_ms, str(e)
            )
            raise

    async def sync_subscriptions(self) -> dict:
        """Sync all subscriptions from GreenLake to database."""
        logger.info("Starting subscription sync...")
        started_at = datetime.now(timezone.utc)
        start_time = time.time()

        try:
            raw_result = await self.subscription_syncer.sync()
            result = _normalize_sync_result(raw_result)
            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Subscription sync complete: {result['records_fetched']} fetched, "
                f"{result['records_inserted']} inserted, "
                f"{result['records_updated']} updated"
            )

            # Record success in history
            await self._record_sync_history(
                "subscriptions", started_at, result, "success", duration_ms
            )

            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Subscription sync failed: {e}")

            # Record failure in history
            await self._record_sync_history(
                "subscriptions", started_at, {}, "failed", duration_ms, str(e)
            )
            raise
