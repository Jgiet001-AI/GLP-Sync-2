"""Adapters layer - Infrastructure implementations for sync operations.

This layer contains concrete implementations of the ports defined in the domain layer:
- PostgresDeviceRepository: PostgreSQL implementation of IDeviceRepository
- GLPDeviceAPI: GreenLake Platform API implementation of IDeviceAPI
- DeviceFieldMapper: Field mapping implementation of IFieldMapper
- PostgresSubscriptionRepository: PostgreSQL implementation of ISubscriptionRepository
- GLPSubscriptionAPI: GreenLake Platform API implementation of ISubscriptionAPI
- SubscriptionFieldMapper: Field mapping implementation of ISubscriptionFieldMapper
"""

from .field_mapper import DeviceFieldMapper, SubscriptionFieldMapper
from .glp_api_adapter import GLPDeviceAPI, GLPSubscriptionAPI
from .postgres_device_repo import PostgresDeviceRepository
from .postgres_subscription_repo import PostgresSubscriptionRepository

__all__ = [
    # Device adapters
    "DeviceFieldMapper",
    "GLPDeviceAPI",
    "PostgresDeviceRepository",
    # Subscription adapters
    "GLPSubscriptionAPI",
    "PostgresSubscriptionRepository",
    "SubscriptionFieldMapper",
]
