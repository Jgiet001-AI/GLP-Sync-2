"""Tests for the DeviceFieldMapper adapter."""

from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.glp.sync.adapters.field_mapper import DeviceFieldMapper, SubscriptionFieldMapper
from src.glp.sync.domain.entities import Device, Subscription


class TestDeviceFieldMapper:
    """Tests for DeviceFieldMapper."""

    @pytest.fixture
    def mapper(self):
        """Create a DeviceFieldMapper instance."""
        return DeviceFieldMapper()

    @pytest.fixture
    def raw_device_minimal(self):
        """Minimal raw device data from API."""
        return {
            "id": "12345678-1234-1234-1234-123456789012",
        }

    @pytest.fixture
    def raw_device_full(self):
        """Full raw device data from API with all fields."""
        return {
            "id": "12345678-1234-1234-1234-123456789012",
            "macAddress": "AA:BB:CC:DD:EE:FF",
            "serialNumber": "SN12345",
            "partNumber": "PN001",
            "deviceType": "AP",
            "model": "AP-500",
            "region": "US-WEST",
            "archived": False,
            "deviceName": "Office AP",
            "secondaryName": "Floor 2",
            "assignedState": "ASSIGNED",
            "type": "devices/device",
            "tenantWorkspaceId": "workspace-123",
            "application": {
                "id": "app-123",
                "resourceUri": "/apps/app-123",
            },
            "dedicatedPlatformWorkspace": {
                "id": "platform-456",
            },
            "location": {
                "id": "loc-789",
                "locationName": "Building A",
                "city": "San Jose",
                "state": "CA",
                "country": "USA",
                "postalCode": "95134",
                "streetAddress": "123 Main St",
                "latitude": 37.3382,
                "longitude": -121.8863,
                "locationSource": "manual",
            },
            "createdAt": "2024-01-15T10:30:00Z",
            "updatedAt": "2024-01-15T11:00:00Z",
            "subscription": [
                {
                    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "resourceUri": "/subscriptions/sub-001",
                },
                {
                    "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    "resourceUri": "/subscriptions/sub-002",
                },
            ],
            "tags": {
                "environment": "production",
                "team": "networking",
            },
        }

    def test_map_to_entity_minimal(self, mapper, raw_device_minimal):
        """Test mapping minimal device data to entity."""
        device = mapper.map_to_entity(raw_device_minimal)

        assert isinstance(device, Device)
        assert device.id == UUID("12345678-1234-1234-1234-123456789012")
        assert device.serial_number is None
        assert device.archived is False

    def test_map_to_entity_full(self, mapper, raw_device_full):
        """Test mapping full device data to entity."""
        device = mapper.map_to_entity(raw_device_full)

        # Basic fields
        assert device.id == UUID("12345678-1234-1234-1234-123456789012")
        assert device.mac_address == "AA:BB:CC:DD:EE:FF"
        assert device.serial_number == "SN12345"
        assert device.device_type == "AP"
        assert device.model == "AP-500"
        assert device.archived is False

        # Nested application fields
        assert device.application_id == "app-123"
        assert device.application_resource_uri == "/apps/app-123"

        # Nested location fields
        assert device.location_id == "loc-789"
        assert device.location_name == "Building A"
        assert device.location_city == "San Jose"
        assert device.location_latitude == 37.3382

        # resource_type (API uses "type")
        assert device.resource_type == "devices/device"

        # Raw data preserved
        assert device.raw_data == raw_device_full

    def test_map_to_entity_handles_missing_nested_objects(self, mapper):
        """Test mapping handles missing nested objects gracefully."""
        raw = {
            "id": "12345678-1234-1234-1234-123456789012",
            "application": None,
            "location": None,
            "dedicatedPlatformWorkspace": None,
        }

        device = mapper.map_to_entity(raw)

        assert device.application_id is None
        assert device.location_id is None
        assert device.dedicated_platform_id is None

    def test_map_to_entity_parses_timestamps(self, mapper, raw_device_full):
        """Test timestamp parsing."""
        device = mapper.map_to_entity(raw_device_full)

        assert device.created_at is not None
        assert isinstance(device.created_at, datetime)
        assert device.created_at.year == 2024
        assert device.created_at.month == 1
        assert device.created_at.day == 15

    def test_map_to_record(self, mapper, raw_device_full):
        """Test mapping entity to database record tuple."""
        device = mapper.map_to_entity(raw_device_full)
        record = mapper.map_to_record(device)

        # Should be a tuple with 29 elements
        assert isinstance(record, tuple)
        assert len(record) == 29

        # Check some key fields
        assert record[0] == "12345678-1234-1234-1234-123456789012"  # id
        assert record[1] == "AA:BB:CC:DD:EE:FF"  # mac_address
        assert record[2] == "SN12345"  # serial_number

    def test_extract_subscriptions(self, mapper, raw_device_full):
        """Test extracting subscriptions from device data."""
        device = mapper.map_to_entity(raw_device_full)
        subscriptions = mapper.extract_subscriptions(device, raw_device_full)

        assert len(subscriptions) == 2
        assert subscriptions[0].device_id == device.id
        assert subscriptions[0].subscription_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        assert subscriptions[0].resource_uri == "/subscriptions/sub-001"

    def test_extract_subscriptions_empty(self, mapper, raw_device_minimal):
        """Test extracting subscriptions when none exist."""
        device = mapper.map_to_entity(raw_device_minimal)
        subscriptions = mapper.extract_subscriptions(device, raw_device_minimal)

        assert subscriptions == []

    def test_extract_subscriptions_skips_invalid(self, mapper):
        """Test extracting subscriptions skips entries without id."""
        raw = {
            "id": "12345678-1234-1234-1234-123456789012",
            "subscription": [
                {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "resourceUri": "/subs/1"},
                {"resourceUri": "/subs/2"},  # No id - should be skipped
                {"id": None, "resourceUri": "/subs/3"},  # None id - should be skipped
            ],
        }

        device = mapper.map_to_entity(raw)
        subscriptions = mapper.extract_subscriptions(device, raw)

        assert len(subscriptions) == 1
        assert subscriptions[0].subscription_id == UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    def test_extract_tags(self, mapper, raw_device_full):
        """Test extracting tags from device data."""
        device = mapper.map_to_entity(raw_device_full)
        tags = mapper.extract_tags(device, raw_device_full)

        assert len(tags) == 2
        assert any(t.tag_key == "environment" and t.tag_value == "production" for t in tags)
        assert any(t.tag_key == "team" and t.tag_value == "networking" for t in tags)

    def test_extract_tags_empty(self, mapper, raw_device_minimal):
        """Test extracting tags when none exist."""
        device = mapper.map_to_entity(raw_device_minimal)
        tags = mapper.extract_tags(device, raw_device_minimal)

        assert tags == []

    def test_parse_timestamp_with_z_suffix(self, mapper):
        """Test parsing ISO timestamp with Z suffix."""
        result = mapper._parse_timestamp("2024-01-15T10:30:00Z")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_timestamp_with_offset(self, mapper):
        """Test parsing ISO timestamp with timezone offset."""
        result = mapper._parse_timestamp("2024-01-15T10:30:00+00:00")

        assert result is not None
        assert result.tzinfo is not None

    def test_parse_timestamp_none(self, mapper):
        """Test parsing None returns None."""
        result = mapper._parse_timestamp(None)
        assert result is None

    def test_parse_timestamp_empty_string(self, mapper):
        """Test parsing empty string returns None."""
        result = mapper._parse_timestamp("")
        assert result is None


class TestSubscriptionFieldMapper:
    """Tests for SubscriptionFieldMapper."""

    @pytest.fixture
    def mapper(self):
        """Create a SubscriptionFieldMapper instance."""
        return SubscriptionFieldMapper()

    @pytest.fixture
    def raw_subscription_minimal(self):
        """Minimal raw subscription data from API."""
        return {
            "id": "12345678-1234-1234-1234-123456789012",
        }

    @pytest.fixture
    def raw_subscription_full(self):
        """Full raw subscription data from API with all fields."""
        return {
            "id": "12345678-1234-1234-1234-123456789012",
            "key": "SUB-001",
            "type": "subscriptions/subscription",
            "subscriptionType": "CENTRAL_SWITCH",
            "subscriptionStatus": "STARTED",
            "quantity": 100,
            "availableQuantity": 50,
            "sku": "SKU-123",
            "skuDescription": "Enterprise Switch License",
            "startTime": "2024-01-01T00:00:00Z",
            "endTime": "2025-01-01T00:00:00Z",
            "tier": "ADVANCED",
            "tierDescription": "Advanced Tier",
            "productType": "NETWORKING",
            "isEval": False,
            "contract": "CONTRACT-001",
            "quote": "QUOTE-001",
            "po": "PO-001",
            "resellerPo": "RPO-001",
            "createdAt": "2024-01-01T10:30:00Z",
            "updatedAt": "2024-01-15T11:00:00Z",
            "tags": {
                "environment": "production",
                "team": "networking",
            },
        }

    def test_map_to_entity_minimal(self, mapper, raw_subscription_minimal):
        """Test mapping minimal subscription data to entity."""
        sub = mapper.map_to_entity(raw_subscription_minimal)

        assert isinstance(sub, Subscription)
        assert sub.id == UUID("12345678-1234-1234-1234-123456789012")
        assert sub.key is None
        assert sub.subscription_status is None
        assert sub.is_eval is False

    def test_map_to_entity_full(self, mapper, raw_subscription_full):
        """Test mapping full subscription data to entity."""
        sub = mapper.map_to_entity(raw_subscription_full)

        # Basic fields
        assert sub.id == UUID("12345678-1234-1234-1234-123456789012")
        assert sub.key == "SUB-001"
        assert sub.subscription_type == "CENTRAL_SWITCH"
        assert sub.subscription_status == "STARTED"
        assert sub.quantity == 100
        assert sub.available_quantity == 50
        assert sub.sku == "SKU-123"
        assert sub.tier == "ADVANCED"

        # resource_type (API uses "type")
        assert sub.resource_type == "subscriptions/subscription"

        # Raw data preserved
        assert sub.raw_data == raw_subscription_full

    def test_map_to_entity_parses_timestamps(self, mapper, raw_subscription_full):
        """Test timestamp parsing."""
        sub = mapper.map_to_entity(raw_subscription_full)

        assert sub.start_time is not None
        assert isinstance(sub.start_time, datetime)
        assert sub.start_time.year == 2024
        assert sub.start_time.month == 1
        assert sub.start_time.day == 1

        assert sub.end_time is not None
        assert sub.end_time.year == 2025

    def test_map_to_entity_parses_quantity(self, mapper):
        """Test quantity parsing with different values."""
        raw_with_qty = {
            "id": "12345678-1234-1234-1234-123456789012",
            "quantity": 50,
            "availableQuantity": 25,
        }
        raw_without_qty = {
            "id": "12345678-1234-1234-1234-123456789012",
        }

        sub_with = mapper.map_to_entity(raw_with_qty)
        sub_without = mapper.map_to_entity(raw_without_qty)

        assert sub_with.quantity == 50
        assert sub_with.available_quantity == 25
        assert sub_without.quantity is None
        assert sub_without.available_quantity is None

    def test_map_to_record(self, mapper, raw_subscription_full):
        """Test mapping entity to database record tuple."""
        sub = mapper.map_to_entity(raw_subscription_full)
        record = mapper.map_to_record(sub)

        # Should be a tuple with 22 elements
        assert isinstance(record, tuple)
        assert len(record) == 22

        # Check some key fields
        assert record[0] == "12345678-1234-1234-1234-123456789012"  # id
        assert record[1] == "SUB-001"  # key
        assert record[3] == "CENTRAL_SWITCH"  # subscription_type

    def test_extract_tags(self, mapper, raw_subscription_full):
        """Test extracting tags from subscription data."""
        sub = mapper.map_to_entity(raw_subscription_full)
        tags = mapper.extract_tags(sub, raw_subscription_full)

        assert len(tags) == 2
        assert any(t.tag_key == "environment" and t.tag_value == "production" for t in tags)
        assert any(t.tag_key == "team" and t.tag_value == "networking" for t in tags)

    def test_extract_tags_empty(self, mapper, raw_subscription_minimal):
        """Test extracting tags when none exist."""
        sub = mapper.map_to_entity(raw_subscription_minimal)
        tags = mapper.extract_tags(sub, raw_subscription_minimal)

        assert tags == []

    def test_extract_tags_handles_none_values(self, mapper):
        """Test extracting tags handles None values gracefully."""
        raw = {
            "id": "12345678-1234-1234-1234-123456789012",
            "tags": {
                "key1": "value1",
                "key2": None,
            },
        }
        sub = mapper.map_to_entity(raw)
        tags = mapper.extract_tags(sub, raw)

        assert len(tags) == 2
        assert any(t.tag_key == "key1" and t.tag_value == "value1" for t in tags)
        assert any(t.tag_key == "key2" and t.tag_value == "" for t in tags)
