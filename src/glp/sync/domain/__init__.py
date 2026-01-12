"""Domain layer - Pure domain entities and port interfaces.

This layer contains:
- Entities: Pure data structures representing business objects
- Ports: Abstract interfaces defining contracts for adapters

No infrastructure dependencies allowed in this layer.
"""

from .entities import (
    Device,
    DeviceSubscription,
    DeviceTag,
    Subscription,
    SubscriptionTag,
    SyncResult,
    SyncStatistics,
)
from .ports import (
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
