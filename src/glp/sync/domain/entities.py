"""Domain entities for sync operations.

These are pure data structures with no infrastructure dependencies.
They represent the core business objects used in sync operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class Device:
    """Domain entity representing a GreenLake device.

    All fields match the database schema in db/schema.sql.
    The raw_data field preserves the full API response for auditability.
    """

    # Primary identifier
    id: UUID

    # Core device info
    mac_address: str | None = None
    serial_number: str | None = None
    part_number: str | None = None
    device_type: str | None = None
    model: str | None = None
    region: str | None = None
    archived: bool = False

    # Naming
    device_name: str | None = None
    secondary_name: str | None = None

    # State and classification
    assigned_state: str | None = None
    resource_type: str | None = None  # API field: "type"
    tenant_workspace_id: str | None = None

    # Application assignment
    application_id: str | None = None
    application_resource_uri: str | None = None

    # Dedicated platform
    dedicated_platform_id: str | None = None

    # Location info (flattened from nested object)
    location_id: str | None = None
    location_name: str | None = None
    location_city: str | None = None
    location_state: str | None = None
    location_country: str | None = None
    location_postal_code: str | None = None
    location_street_address: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    location_source: str | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Full API response for auditability
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_assignable(self) -> bool:
        """Business rule: can this device be assigned?"""
        return not self.archived

    @property
    def has_application(self) -> bool:
        """Check if device has an application assigned."""
        return self.application_id is not None

    @property
    def has_location(self) -> bool:
        """Check if device has location info."""
        return self.location_id is not None


@dataclass
class DeviceSubscription:
    """Represents a device-subscription relationship.

    Maps to the device_subscriptions junction table.
    """

    device_id: UUID
    subscription_id: UUID
    resource_uri: str | None = None


@dataclass
class DeviceTag:
    """Represents a device tag key-value pair.

    Maps to the device_tags table.
    """

    device_id: UUID
    tag_key: str
    tag_value: str


@dataclass
class SyncResult:
    """Result of a sync operation.

    Contains statistics about the sync operation and any errors encountered.
    """

    success: bool
    total: int
    upserted: int
    errors: int
    synced_at: datetime
    error_details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses and backward compatibility."""
        return {
            "total": self.total,
            "upserted": self.upserted,
            "errors": self.errors,
            "synced_at": self.synced_at.isoformat(),
        }


@dataclass
class SyncStatistics:
    """Detailed statistics about a sync operation.

    Provides breakdown of operations performed during sync.
    """

    devices_processed: int = 0
    devices_inserted: int = 0
    devices_updated: int = 0
    subscriptions_synced: int = 0
    tags_synced: int = 0
    errors: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate sync duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


# ============================================
# Subscription Entities
# ============================================


@dataclass
class Subscription:
    """Domain entity representing a GreenLake subscription.

    All fields match the database schema in db/subscriptions_schema.sql.
    The raw_data field preserves the full API response for auditability.
    """

    # Primary identifier
    id: UUID

    # Core subscription info
    key: str | None = None
    resource_type: str | None = None  # API field: "type"
    subscription_type: str | None = None
    subscription_status: str | None = None

    # Quantity info
    quantity: int | None = None
    available_quantity: int | None = None

    # SKU info
    sku: str | None = None
    sku_description: str | None = None

    # Time info
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Tier info
    tier: str | None = None
    tier_description: str | None = None

    # Product info
    product_type: str | None = None
    is_eval: bool = False

    # Contract/order info
    contract: str | None = None
    quote: str | None = None
    po: str | None = None
    reseller_po: str | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Full API response for auditability
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Business rule: is this subscription currently active?"""
        return self.subscription_status == "STARTED"

    @property
    def is_expired(self) -> bool:
        """Check if subscription has expired."""
        if self.end_time is None:
            return False
        from datetime import timezone
        return self.end_time < datetime.now(timezone.utc)

    @property
    def days_until_expiry(self) -> int | None:
        """Calculate days until subscription expires."""
        if self.end_time is None:
            return None
        from datetime import timezone
        delta = self.end_time - datetime.now(timezone.utc)
        return max(0, delta.days)

    @property
    def has_available_quantity(self) -> bool:
        """Check if subscription has available quantity."""
        return (self.available_quantity or 0) > 0


@dataclass
class SubscriptionTag:
    """Represents a subscription tag key-value pair.

    Maps to the subscription_tags table.
    """

    subscription_id: UUID
    tag_key: str
    tag_value: str
