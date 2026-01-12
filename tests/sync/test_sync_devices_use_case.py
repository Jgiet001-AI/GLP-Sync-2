"""Tests for the SyncDevicesUseCase.

These tests use mock ports to test the use case in isolation,
demonstrating the testability benefits of Clean Architecture.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from src.glp.sync.domain.entities import (
    Device,
    DeviceSubscription,
    DeviceTag,
    SyncResult,
)
from src.glp.sync.domain.ports import IDeviceAPI, IDeviceRepository, IFieldMapper
from src.glp.sync.use_cases.sync_devices import SyncDevicesUseCase


class MockDeviceAPI(IDeviceAPI):
    """Mock implementation of IDeviceAPI for testing."""

    def __init__(self, devices: list[dict[str, Any]] | None = None, raise_error: Exception | None = None):
        self.devices = devices or []
        self.raise_error = raise_error
        self.fetch_all_called = False

    async def fetch_all(self) -> list[dict[str, Any]]:
        self.fetch_all_called = True
        if self.raise_error:
            raise self.raise_error
        return self.devices

    async def fetch_paginated(self):
        yield self.devices


class MockDeviceRepository(IDeviceRepository):
    """Mock implementation of IDeviceRepository for testing."""

    def __init__(self, raise_error: Exception | None = None):
        self.upserted_devices: list[Device] = []
        self.synced_subscriptions: list[DeviceSubscription] = []
        self.synced_tags: list[DeviceTag] = []
        self.raise_error = raise_error

    async def upsert_devices(self, devices: list[Device]) -> int:
        if self.raise_error:
            raise self.raise_error
        self.upserted_devices.extend(devices)
        return len(devices)

    async def sync_subscriptions(
        self,
        device_ids: list[UUID],
        subscriptions: list[DeviceSubscription],
    ) -> None:
        self.synced_subscriptions.extend(subscriptions)

    async def sync_tags(
        self,
        device_ids: list[UUID],
        tags: list[DeviceTag],
    ) -> None:
        self.synced_tags.extend(tags)

    async def sync_all_related_data(
        self,
        device_ids: list[UUID],
        subscriptions: list[DeviceSubscription],
        tags: list[DeviceTag],
    ) -> None:
        if self.raise_error:
            raise self.raise_error
        self.synced_subscriptions.extend(subscriptions)
        self.synced_tags.extend(tags)


class MockFieldMapper(IFieldMapper):
    """Mock implementation of IFieldMapper for testing."""

    def __init__(self, raise_mapping_error: bool = False):
        self.raise_mapping_error = raise_mapping_error
        self.mapped_count = 0

    def map_to_entity(self, raw: dict[str, Any]) -> Device:
        if self.raise_mapping_error:
            raise ValueError("Mapping error")

        self.mapped_count += 1
        return Device(
            id=UUID(raw["id"]),
            serial_number=raw.get("serialNumber"),
            mac_address=raw.get("macAddress"),
            device_type=raw.get("deviceType"),
            raw_data=raw,
        )

    def map_to_record(self, device: Device) -> tuple[Any, ...]:
        return (str(device.id), device.serial_number)

    def extract_subscriptions(
        self,
        device: Device,
        raw: dict[str, Any],
    ) -> list[DeviceSubscription]:
        subs = []
        for sub in raw.get("subscription", []):
            if sub.get("id"):
                subs.append(
                    DeviceSubscription(
                        device_id=device.id,
                        subscription_id=UUID(sub["id"]),
                        resource_uri=sub.get("resourceUri"),
                    )
                )
        return subs

    def extract_tags(
        self,
        device: Device,
        raw: dict[str, Any],
    ) -> list[DeviceTag]:
        tags = []
        for key, value in (raw.get("tags") or {}).items():
            tags.append(
                DeviceTag(
                    device_id=device.id,
                    tag_key=key,
                    tag_value=str(value),
                )
            )
        return tags


class TestSyncDevicesUseCase:
    """Tests for SyncDevicesUseCase."""

    @pytest.fixture
    def sample_devices(self):
        """Sample device data from API."""
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "serialNumber": "SN001",
                "macAddress": "AA:BB:CC:DD:EE:01",
                "deviceType": "AP",
                "subscription": [
                    {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "resourceUri": "/subs/sub-001"},
                ],
                "tags": {"env": "prod"},
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "serialNumber": "SN002",
                "macAddress": "AA:BB:CC:DD:EE:02",
                "deviceType": "SWITCH",
                "subscription": [],
                "tags": {"env": "dev", "team": "network"},
            },
        ]

    async def test_sync_success(self, sample_devices):
        """Test successful device sync."""
        api = MockDeviceAPI(devices=sample_devices)
        repo = MockDeviceRepository()
        mapper = MockFieldMapper()

        use_case = SyncDevicesUseCase(api, repo, mapper)
        result = await use_case.execute()

        # Verify result
        assert result.success is True
        assert result.total == 2
        assert result.upserted == 2
        assert result.errors == 0

        # Verify API was called
        assert api.fetch_all_called is True

        # Verify devices were upserted
        assert len(repo.upserted_devices) == 2

        # Verify subscriptions were synced
        assert len(repo.synced_subscriptions) == 1

        # Verify tags were synced
        assert len(repo.synced_tags) == 3  # 1 + 2 tags

    async def test_sync_empty_devices(self):
        """Test sync with no devices."""
        api = MockDeviceAPI(devices=[])
        repo = MockDeviceRepository()
        mapper = MockFieldMapper()

        use_case = SyncDevicesUseCase(api, repo, mapper)
        result = await use_case.execute()

        assert result.success is True
        assert result.total == 0
        assert result.upserted == 0
        assert result.errors == 0

    async def test_sync_api_error(self):
        """Test sync handles API errors."""
        api = MockDeviceAPI(raise_error=Exception("API connection failed"))
        repo = MockDeviceRepository()
        mapper = MockFieldMapper()

        use_case = SyncDevicesUseCase(api, repo, mapper)
        result = await use_case.execute()

        assert result.success is False
        assert result.errors == 1
        assert "API fetch failed" in result.error_details[0]

    async def test_sync_mapping_error(self, sample_devices):
        """Test sync handles mapping errors gracefully."""
        api = MockDeviceAPI(devices=sample_devices)
        repo = MockDeviceRepository()
        mapper = MockFieldMapper(raise_mapping_error=True)

        use_case = SyncDevicesUseCase(api, repo, mapper)
        result = await use_case.execute()

        # Should still succeed with errors logged
        assert result.total == 2
        assert result.errors == 2  # Both mappings failed
        assert len(result.error_details) == 2

    async def test_sync_database_error(self, sample_devices):
        """Test sync handles database errors."""
        api = MockDeviceAPI(devices=sample_devices)
        repo = MockDeviceRepository(raise_error=Exception("Database connection lost"))
        mapper = MockFieldMapper()

        use_case = SyncDevicesUseCase(api, repo, mapper)
        result = await use_case.execute()

        # Should complete with errors
        assert result.success is False
        assert result.errors >= 1
        assert any("Database" in e for e in result.error_details)

    async def test_sync_result_to_dict(self, sample_devices):
        """Test sync result can be converted to dict for backward compat."""
        api = MockDeviceAPI(devices=sample_devices)
        repo = MockDeviceRepository()
        mapper = MockFieldMapper()

        use_case = SyncDevicesUseCase(api, repo, mapper)
        result = await use_case.execute()

        d = result.to_dict()

        assert "total" in d
        assert "upserted" in d
        assert "errors" in d
        assert "synced_at" in d
        assert d["total"] == 2
        assert d["upserted"] == 2

    async def test_sync_extracts_subscriptions_correctly(self, sample_devices):
        """Test that subscriptions are correctly extracted and synced."""
        api = MockDeviceAPI(devices=sample_devices)
        repo = MockDeviceRepository()
        mapper = MockFieldMapper()

        use_case = SyncDevicesUseCase(api, repo, mapper)
        await use_case.execute()

        # First device has 1 subscription, second has 0
        assert len(repo.synced_subscriptions) == 1
        assert repo.synced_subscriptions[0].subscription_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def test_sync_extracts_tags_correctly(self, sample_devices):
        """Test that tags are correctly extracted and synced."""
        api = MockDeviceAPI(devices=sample_devices)
        repo = MockDeviceRepository()
        mapper = MockFieldMapper()

        use_case = SyncDevicesUseCase(api, repo, mapper)
        await use_case.execute()

        # First device has 1 tag, second has 2 tags
        assert len(repo.synced_tags) == 3

        tag_keys = {t.tag_key for t in repo.synced_tags}
        assert "env" in tag_keys
        assert "team" in tag_keys
