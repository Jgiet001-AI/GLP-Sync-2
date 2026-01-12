"""Tests for sync domain entities."""

from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.glp.sync.domain.entities import (
    Device,
    DeviceSubscription,
    DeviceTag,
    Subscription,
    SubscriptionTag,
    SyncResult,
    SyncStatistics,
)


class TestDevice:
    """Tests for Device entity."""

    def test_device_creation_minimal(self):
        """Test creating a device with minimal required fields."""
        device = Device(id=UUID("12345678-1234-1234-1234-123456789012"))

        assert device.id == UUID("12345678-1234-1234-1234-123456789012")
        assert device.serial_number is None
        assert device.archived is False
        assert device.raw_data == {}

    def test_device_creation_full(self):
        """Test creating a device with all fields."""
        device = Device(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            mac_address="AA:BB:CC:DD:EE:FF",
            serial_number="SN12345",
            part_number="PN001",
            device_type="AP",
            model="AP-500",
            region="US-WEST",
            archived=False,
            device_name="Office AP",
            application_id="app-123",
            location_id="loc-456",
            location_name="Building A",
        )

        assert device.mac_address == "AA:BB:CC:DD:EE:FF"
        assert device.serial_number == "SN12345"
        assert device.device_type == "AP"

    def test_device_is_assignable_when_not_archived(self):
        """Test is_assignable property returns True for non-archived devices."""
        device = Device(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            archived=False,
        )
        assert device.is_assignable is True

    def test_device_is_not_assignable_when_archived(self):
        """Test is_assignable property returns False for archived devices."""
        device = Device(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            archived=True,
        )
        assert device.is_assignable is False

    def test_device_has_application(self):
        """Test has_application property."""
        device_with_app = Device(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            application_id="app-123",
        )
        device_without_app = Device(
            id=UUID("12345678-1234-1234-1234-123456789012"),
        )

        assert device_with_app.has_application is True
        assert device_without_app.has_application is False

    def test_device_has_location(self):
        """Test has_location property."""
        device_with_loc = Device(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            location_id="loc-456",
        )
        device_without_loc = Device(
            id=UUID("12345678-1234-1234-1234-123456789012"),
        )

        assert device_with_loc.has_location is True
        assert device_without_loc.has_location is False


class TestDeviceSubscription:
    """Tests for DeviceSubscription entity."""

    def test_device_subscription_creation(self):
        """Test creating a device subscription relationship."""
        sub = DeviceSubscription(
            device_id=UUID("12345678-1234-1234-1234-123456789012"),
            subscription_id=UUID("87654321-4321-4321-4321-210987654321"),
            resource_uri="/subscriptions/sub-123",
        )

        assert sub.device_id == UUID("12345678-1234-1234-1234-123456789012")
        assert sub.subscription_id == UUID("87654321-4321-4321-4321-210987654321")
        assert sub.resource_uri == "/subscriptions/sub-123"


class TestDeviceTag:
    """Tests for DeviceTag entity."""

    def test_device_tag_creation(self):
        """Test creating a device tag."""
        tag = DeviceTag(
            device_id=UUID("12345678-1234-1234-1234-123456789012"),
            tag_key="environment",
            tag_value="production",
        )

        assert tag.device_id == UUID("12345678-1234-1234-1234-123456789012")
        assert tag.tag_key == "environment"
        assert tag.tag_value == "production"


class TestSyncResult:
    """Tests for SyncResult entity."""

    def test_sync_result_success(self):
        """Test creating a successful sync result."""
        synced_at = datetime.now(timezone.utc)
        result = SyncResult(
            success=True,
            total=100,
            upserted=100,
            errors=0,
            synced_at=synced_at,
        )

        assert result.success is True
        assert result.total == 100
        assert result.upserted == 100
        assert result.errors == 0

    def test_sync_result_with_errors(self):
        """Test creating a sync result with errors."""
        synced_at = datetime.now(timezone.utc)
        result = SyncResult(
            success=False,
            total=100,
            upserted=95,
            errors=5,
            synced_at=synced_at,
            error_details=["Error 1", "Error 2"],
        )

        assert result.success is False
        assert result.errors == 5
        assert len(result.error_details) == 2

    def test_sync_result_to_dict(self):
        """Test converting sync result to dictionary."""
        synced_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = SyncResult(
            success=True,
            total=50,
            upserted=50,
            errors=0,
            synced_at=synced_at,
        )

        d = result.to_dict()

        assert d["total"] == 50
        assert d["upserted"] == 50
        assert d["errors"] == 0
        assert "synced_at" in d


class TestSyncStatistics:
    """Tests for SyncStatistics entity."""

    def test_sync_statistics_defaults(self):
        """Test sync statistics default values."""
        stats = SyncStatistics()

        assert stats.devices_processed == 0
        assert stats.devices_inserted == 0
        assert stats.errors == 0
        assert stats.started_at is None

    def test_sync_statistics_duration(self):
        """Test sync statistics duration calculation."""
        started = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2024, 1, 15, 10, 0, 30, tzinfo=timezone.utc)

        stats = SyncStatistics(
            devices_processed=100,
            started_at=started,
            completed_at=completed,
        )

        assert stats.duration_seconds == 30.0

    def test_sync_statistics_duration_none_when_incomplete(self):
        """Test sync statistics duration is None when timestamps missing."""
        stats = SyncStatistics(
            devices_processed=100,
            started_at=datetime.now(timezone.utc),
        )

        assert stats.duration_seconds is None


class TestSubscription:
    """Tests for Subscription entity."""

    def test_subscription_creation_minimal(self):
        """Test creating a subscription with minimal required fields."""
        sub = Subscription(id=UUID("12345678-1234-1234-1234-123456789012"))

        assert sub.id == UUID("12345678-1234-1234-1234-123456789012")
        assert sub.key is None
        assert sub.subscription_status is None
        assert sub.is_eval is False
        assert sub.raw_data == {}

    def test_subscription_creation_full(self):
        """Test creating a subscription with all fields."""
        sub = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            key="SUB-001",
            resource_type="subscriptions/subscription",
            subscription_type="CENTRAL_SWITCH",
            subscription_status="STARTED",
            quantity=100,
            available_quantity=50,
            sku="SKU-123",
            sku_description="Enterprise License",
            tier="ADVANCED",
            is_eval=False,
        )

        assert sub.key == "SUB-001"
        assert sub.subscription_type == "CENTRAL_SWITCH"
        assert sub.quantity == 100
        assert sub.available_quantity == 50

    def test_subscription_is_active_when_started(self):
        """Test is_active property returns True for STARTED status."""
        sub = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            subscription_status="STARTED",
        )
        assert sub.is_active is True

    def test_subscription_is_not_active_when_ended(self):
        """Test is_active property returns False for ENDED status."""
        sub = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            subscription_status="ENDED",
        )
        assert sub.is_active is False

    def test_subscription_is_expired_when_end_time_passed(self):
        """Test is_expired property when end_time is in the past."""
        past_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        sub = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            end_time=past_time,
        )
        assert sub.is_expired is True

    def test_subscription_is_not_expired_when_end_time_future(self):
        """Test is_expired property when end_time is in the future."""
        future_time = datetime(2099, 1, 1, tzinfo=timezone.utc)
        sub = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            end_time=future_time,
        )
        assert sub.is_expired is False

    def test_subscription_is_not_expired_when_no_end_time(self):
        """Test is_expired property returns False when no end_time."""
        sub = Subscription(id=UUID("12345678-1234-1234-1234-123456789012"))
        assert sub.is_expired is False

    def test_subscription_days_until_expiry(self):
        """Test days_until_expiry calculation."""
        from datetime import timedelta
        future_time = datetime.now(timezone.utc) + timedelta(days=30)
        sub = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            end_time=future_time,
        )
        # Should be approximately 30 days
        assert 29 <= sub.days_until_expiry <= 30

    def test_subscription_days_until_expiry_none_when_no_end_time(self):
        """Test days_until_expiry returns None when no end_time."""
        sub = Subscription(id=UUID("12345678-1234-1234-1234-123456789012"))
        assert sub.days_until_expiry is None

    def test_subscription_has_available_quantity(self):
        """Test has_available_quantity property."""
        sub_with_qty = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            available_quantity=10,
        )
        sub_without_qty = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            available_quantity=0,
        )
        sub_none_qty = Subscription(
            id=UUID("12345678-1234-1234-1234-123456789012"),
        )

        assert sub_with_qty.has_available_quantity is True
        assert sub_without_qty.has_available_quantity is False
        assert sub_none_qty.has_available_quantity is False


class TestSubscriptionTag:
    """Tests for SubscriptionTag entity."""

    def test_subscription_tag_creation(self):
        """Test creating a subscription tag."""
        tag = SubscriptionTag(
            subscription_id=UUID("12345678-1234-1234-1234-123456789012"),
            tag_key="environment",
            tag_value="production",
        )

        assert tag.subscription_id == UUID("12345678-1234-1234-1234-123456789012")
        assert tag.tag_key == "environment"
        assert tag.tag_value == "production"
