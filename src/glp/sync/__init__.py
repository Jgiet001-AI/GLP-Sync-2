"""Sync module - Clean Architecture implementation for GreenLake sync operations.

This module provides a Clean Architecture refactoring of the device and subscription
sync functionality, enabling better testability, maintainability, and separation
of concerns.

Architecture:
    domain/     - Pure domain entities and port interfaces
    use_cases/  - Business logic orchestration
    adapters/   - Infrastructure implementations (PostgreSQL, GLP API)
"""

from .domain.entities import (
    Device,
    DeviceSubscription,
    DeviceTag,
    Subscription,
    SubscriptionTag,
    SyncResult,
    SyncStatistics,
)
from .domain.ports import (
    IDeviceAPI,
    IDeviceRepository,
    IFieldMapper,
    ISubscriptionAPI,
    ISubscriptionFieldMapper,
    ISubscriptionRepository,
)

__all__ = [
    # Device Entities
    "Device",
    "DeviceSubscription",
    "DeviceTag",
    # Subscription Entities
    "Subscription",
    "SubscriptionTag",
    # Result Entities
    "SyncResult",
    "SyncStatistics",
    # Device Ports
    "IDeviceAPI",
    "IDeviceRepository",
    "IFieldMapper",
    # Subscription Ports
    "ISubscriptionAPI",
    "ISubscriptionFieldMapper",
    "ISubscriptionRepository",
]
