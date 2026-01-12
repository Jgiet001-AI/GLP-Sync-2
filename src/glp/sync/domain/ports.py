"""Port interfaces for sync operations.

Ports define the contracts between the domain/use cases and the infrastructure.
These are abstract base classes that adapters must implement.

Following the Hexagonal Architecture (Ports and Adapters) pattern:
- Ports are interfaces defined in the domain layer
- Adapters implement these ports in the adapters layer
- Use cases depend only on ports, not concrete implementations
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from .entities import (
    Device,
    DeviceSubscription,
    DeviceTag,
    Subscription,
    SubscriptionTag,
    SyncResult,
)


class IDeviceRepository(ABC):
    """Port for device persistence operations.

    Implementations handle the specifics of storing devices in a database.
    The use case layer depends on this interface, not the concrete implementation.
    """

    @abstractmethod
    async def upsert_devices(self, devices: list[Device]) -> int:
        """Bulk upsert devices to storage.

        Args:
            devices: List of Device entities to upsert

        Returns:
            Number of devices upserted
        """
        ...

    @abstractmethod
    async def sync_subscriptions(
        self,
        device_ids: list[UUID],
        subscriptions: list[DeviceSubscription],
    ) -> None:
        """Sync device subscriptions (delete old, insert new).

        Args:
            device_ids: List of device IDs to sync subscriptions for
            subscriptions: List of DeviceSubscription entities to insert
        """
        ...

    @abstractmethod
    async def sync_tags(
        self,
        device_ids: list[UUID],
        tags: list[DeviceTag],
    ) -> None:
        """Sync device tags (delete old, insert new).

        Args:
            device_ids: List of device IDs to sync tags for
            tags: List of DeviceTag entities to insert
        """
        ...

    @abstractmethod
    async def sync_all_related_data(
        self,
        device_ids: list[UUID],
        subscriptions: list[DeviceSubscription],
        tags: list[DeviceTag],
    ) -> None:
        """Sync both subscriptions and tags in a single transaction.

        This is the preferred method for efficiency - it combines
        subscription and tag sync into one transaction.

        Args:
            device_ids: List of device IDs to sync related data for
            subscriptions: List of DeviceSubscription entities
            tags: List of DeviceTag entities
        """
        ...


class IDeviceAPI(ABC):
    """Port for device API operations.

    Implementations handle fetching devices from external APIs.
    """

    @abstractmethod
    async def fetch_all(self) -> list[dict[str, Any]]:
        """Fetch all devices from the API.

        Returns:
            List of device dictionaries (raw API responses)
        """
        ...

    @abstractmethod
    async def fetch_paginated(self) -> AsyncIterator[list[dict[str, Any]]]:
        """Fetch devices page by page (memory efficient).

        Yields:
            Lists of device dictionaries, one page at a time
        """
        ...


class IFieldMapper(ABC):
    """Port for field mapping between API responses and domain entities.

    Implementations handle the transformation logic between different
    representations of device data.
    """

    @abstractmethod
    def map_to_entity(self, raw: dict[str, Any]) -> Device:
        """Transform API response dictionary to Device entity.

        Args:
            raw: Raw device dictionary from API

        Returns:
            Device domain entity
        """
        ...

    @abstractmethod
    def map_to_record(self, device: Device) -> tuple[Any, ...]:
        """Transform Device entity to database record tuple.

        The tuple ordering must match the database INSERT statement.

        Args:
            device: Device domain entity

        Returns:
            Tuple of values ready for database insertion
        """
        ...

    @abstractmethod
    def extract_subscriptions(
        self,
        device: Device,
        raw: dict[str, Any],
    ) -> list[DeviceSubscription]:
        """Extract subscription relationships from device data.

        Args:
            device: Device entity (for the device_id)
            raw: Raw device dictionary from API

        Returns:
            List of DeviceSubscription entities
        """
        ...

    @abstractmethod
    def extract_tags(
        self,
        device: Device,
        raw: dict[str, Any],
    ) -> list[DeviceTag]:
        """Extract tags from device data.

        Args:
            device: Device entity (for the device_id)
            raw: Raw device dictionary from API

        Returns:
            List of DeviceTag entities
        """
        ...


class ISyncService(ABC):
    """Port for high-level sync orchestration.

    This port is used by external modules (like the assignment module)
    to trigger syncs without knowing the implementation details.
    """

    @abstractmethod
    async def sync_devices(self) -> SyncResult:
        """Execute a full device sync.

        Returns:
            SyncResult with statistics about the sync operation
        """
        ...


# ============================================
# Subscription Ports
# ============================================


class ISubscriptionRepository(ABC):
    """Port for subscription persistence operations.

    Implementations handle the specifics of storing subscriptions in a database.
    """

    @abstractmethod
    async def upsert_subscriptions(self, subscriptions: list[Subscription]) -> int:
        """Bulk upsert subscriptions to storage.

        Args:
            subscriptions: List of Subscription entities to upsert

        Returns:
            Number of subscriptions upserted
        """
        ...

    @abstractmethod
    async def sync_tags(
        self,
        subscription_ids: list[UUID],
        tags: list[SubscriptionTag],
    ) -> None:
        """Sync subscription tags (delete old, insert new).

        Args:
            subscription_ids: List of subscription IDs to sync tags for
            tags: List of SubscriptionTag entities to insert
        """
        ...


class ISubscriptionAPI(ABC):
    """Port for subscription API operations.

    Implementations handle fetching subscriptions from external APIs.
    """

    @abstractmethod
    async def fetch_all(self) -> list[dict[str, Any]]:
        """Fetch all subscriptions from the API.

        Returns:
            List of subscription dictionaries (raw API responses)
        """
        ...

    @abstractmethod
    async def fetch_paginated(self) -> AsyncIterator[list[dict[str, Any]]]:
        """Fetch subscriptions page by page (memory efficient).

        Yields:
            Lists of subscription dictionaries, one page at a time
        """
        ...

    @abstractmethod
    async def fetch_expiring_soon(self, days: int) -> list[dict[str, Any]]:
        """Fetch subscriptions expiring within N days.

        Args:
            days: Number of days to look ahead

        Returns:
            List of subscriptions expiring within the specified window
        """
        ...

    @abstractmethod
    async def fetch_by_status(self, status: str) -> list[dict[str, Any]]:
        """Fetch subscriptions by status.

        Args:
            status: Subscription status (e.g., STARTED, ENDED)

        Returns:
            List of subscriptions with the specified status
        """
        ...


class ISubscriptionFieldMapper(ABC):
    """Port for field mapping between API responses and Subscription entities.

    Implementations handle the transformation logic between different
    representations of subscription data.
    """

    @abstractmethod
    def map_to_entity(self, raw: dict[str, Any]) -> Subscription:
        """Transform API response dictionary to Subscription entity.

        Args:
            raw: Raw subscription dictionary from API

        Returns:
            Subscription domain entity
        """
        ...

    @abstractmethod
    def map_to_record(self, subscription: Subscription) -> tuple[Any, ...]:
        """Transform Subscription entity to database record tuple.

        The tuple ordering must match the database INSERT statement.

        Args:
            subscription: Subscription domain entity

        Returns:
            Tuple of values ready for database insertion
        """
        ...

    @abstractmethod
    def extract_tags(
        self,
        subscription: Subscription,
        raw: dict[str, Any],
    ) -> list[SubscriptionTag]:
        """Extract tags from subscription data.

        Args:
            subscription: Subscription entity (for the subscription_id)
            raw: Raw subscription dictionary from API

        Returns:
            List of SubscriptionTag entities
        """
        ...
