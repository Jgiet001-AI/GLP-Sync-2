#!/usr/bin/env python3
"""Unit tests for DeviceManager.

Tests cover:
    - DeviceManager initialization
    - Add device operations (POST)
    - Update tags operations (PATCH)
    - Application assignment operations (PATCH)
    - Archive/unarchive operations (PATCH)
    - Subscription operations (PATCH)
    - Validation (device limits, required fields)
    - Async operation status polling

Note: These tests mock GLPClient rather than making real API calls.
"""
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests", 1)[0])
from src.glp.api.client import AsyncOperationResult, GLPClient
from src.glp.api.device_manager import (
    DeviceManager,
    DeviceType,
    OperationStatus,
)
from src.glp.api.exceptions import (
    AsyncOperationError,
    DeviceLimitError,
    ValidationError,
)

# ============================================
# DeviceManager Initialization Tests
# ============================================


class TestDeviceManagerInit:
    """Test DeviceManager initialization."""

    def test_manager_requires_client(self):
        """Should require a GLPClient instance."""
        mock_client = MagicMock(spec=GLPClient)
        manager = DeviceManager(client=mock_client)

        assert manager.client is mock_client

    def test_endpoint_constant(self):
        """Should have correct API endpoint constant."""
        assert DeviceManager.ENDPOINT == "/devices/v2beta1/devices"

    def test_max_devices_constant(self):
        """Should have correct max devices constant."""
        assert DeviceManager.MAX_DEVICES_PER_REQUEST == 25


# ============================================
# Validation Tests
# ============================================


class TestValidation:
    """Test validation helpers."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient."""
        return MagicMock(spec=GLPClient)

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    def test_validate_empty_device_ids(self, manager):
        """Should raise ValidationError for empty device IDs."""
        with pytest.raises(ValidationError) as exc_info:
            manager._validate_device_ids([])

        assert "At least one device ID" in str(exc_info.value)

    def test_validate_too_many_device_ids(self, manager):
        """Should raise DeviceLimitError for >25 devices."""
        device_ids = [f"device-{i}" for i in range(30)]

        with pytest.raises(DeviceLimitError) as exc_info:
            manager._validate_device_ids(device_ids)

        assert exc_info.value.device_count == 30
        assert exc_info.value.max_devices == 25

    def test_validate_valid_device_ids(self, manager):
        """Should not raise for valid device IDs."""
        device_ids = ["device-1", "device-2"]
        manager._validate_device_ids(device_ids)  # Should not raise


# ============================================
# Add Device Tests
# ============================================


class TestAddDevice:
    """Test add device operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient with post_async."""
        client = MagicMock(spec=GLPClient)
        client.post_async = AsyncMock(
            return_value=AsyncOperationResult(
                operation_url="https://api.example.com/status/123"
            )
        )
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    @pytest.mark.asyncio
    async def test_add_network_device(self, manager, mock_client):
        """Should add a network device with mac_address."""
        result = await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.NETWORK,
            mac_address="00:1B:44:11:3A:B7",
        )

        mock_client.post_async.assert_called_once()
        call_args = mock_client.post_async.call_args

        assert call_args[0][0] == "/devices/v2beta1/devices"
        payload = call_args[1]["json_body"]
        assert payload["serialNumber"] == "SN12345"
        assert payload["deviceType"] == "NETWORK"
        assert payload["macAddress"] == "00:1B:44:11:3A:B7"
        assert result.operation_url == "https://api.example.com/status/123"

    @pytest.mark.asyncio
    async def test_add_network_device_requires_mac(self, manager):
        """Should require mac_address for NETWORK devices."""
        with pytest.raises(ValidationError) as exc_info:
            await manager.add_device(
                serial_number="SN12345",
                device_type=DeviceType.NETWORK,
            )

        assert "mac_address" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_compute_device(self, manager, mock_client):
        """Should add a compute device with part_number."""
        await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.COMPUTE,
            part_number="PN12345",
        )

        mock_client.post_async.assert_called_once()
        payload = mock_client.post_async.call_args[1]["json_body"]
        assert payload["deviceType"] == "COMPUTE"
        assert payload["partNumber"] == "PN12345"

    @pytest.mark.asyncio
    async def test_add_compute_device_requires_part_number(self, manager):
        """Should require part_number for COMPUTE devices."""
        with pytest.raises(ValidationError) as exc_info:
            await manager.add_device(
                serial_number="SN12345",
                device_type=DeviceType.COMPUTE,
            )

        assert "part_number" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_storage_device(self, manager, mock_client):
        """Should add a storage device with part_number."""
        await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.STORAGE,
            part_number="PN12345",
        )

        payload = mock_client.post_async.call_args[1]["json_body"]
        assert payload["deviceType"] == "STORAGE"

    @pytest.mark.asyncio
    async def test_add_device_with_tags(self, manager, mock_client):
        """Should include tags in request payload."""
        await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.NETWORK,
            mac_address="00:11:22:33:44:55",
            tags={"environment": "production"},
        )

        payload = mock_client.post_async.call_args[1]["json_body"]
        assert payload["tags"] == {"environment": "production"}

    @pytest.mark.asyncio
    async def test_add_device_with_location(self, manager, mock_client):
        """Should include location in request payload."""
        await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.NETWORK,
            mac_address="00:11:22:33:44:55",
            location_id="loc-123",
        )

        payload = mock_client.post_async.call_args[1]["json_body"]
        assert payload["location"] == {"id": "loc-123"}

    @pytest.mark.asyncio
    async def test_add_device_dry_run(self, manager, mock_client):
        """Should pass dry-run parameter."""
        await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.NETWORK,
            mac_address="00:11:22:33:44:55",
            dry_run=True,
        )

        params = mock_client.post_async.call_args[1]["params"]
        assert params["dry-run"] == "true"


# ============================================
# Update Tags Tests
# ============================================


class TestUpdateTags:
    """Test update tags operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient with patch_merge."""
        client = MagicMock(spec=GLPClient)
        client.patch_merge = AsyncMock(
            return_value=AsyncOperationResult(
                operation_url="https://api.example.com/status/456"
            )
        )
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    @pytest.mark.asyncio
    async def test_update_tags(self, manager, mock_client):
        """Should send tags update request."""
        result = await manager.update_tags(
            device_ids=["device-1", "device-2"],
            tags={"location": "San Jose"},
        )

        mock_client.patch_merge.assert_called_once()
        call_args = mock_client.patch_merge.call_args

        assert call_args[0][0] == "/devices/v2beta1/devices"
        assert call_args[1]["json_body"]["tags"] == {"location": "San Jose"}
        assert call_args[1]["params"]["id"] == ["device-1", "device-2"]
        assert result.operation_url == "https://api.example.com/status/456"

    @pytest.mark.asyncio
    async def test_update_tags_remove(self, manager, mock_client):
        """Should send None value to remove tags."""
        await manager.update_tags(
            device_ids=["device-1"],
            tags={"old_tag": None},
        )

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["tags"] == {"old_tag": None}

    @pytest.mark.asyncio
    async def test_update_tags_validates_device_ids(self, manager):
        """Should validate device IDs."""
        with pytest.raises(ValidationError):
            await manager.update_tags(device_ids=[], tags={"key": "value"})


# ============================================
# Application Assignment Tests
# ============================================


class TestApplicationAssignment:
    """Test application assignment operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient."""
        client = MagicMock(spec=GLPClient)
        client.patch_merge = AsyncMock(
            return_value=AsyncOperationResult(operation_url="https://example.com/status")
        )
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    @pytest.mark.asyncio
    async def test_assign_application(self, manager, mock_client):
        """Should send application assignment request."""
        await manager.assign_application(
            device_ids=["device-1"],
            application_id="app-123",
        )

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["application"]["id"] == "app-123"

    @pytest.mark.asyncio
    async def test_assign_application_with_region(self, manager, mock_client):
        """Should include region in assignment."""
        await manager.assign_application(
            device_ids=["device-1"],
            application_id="app-123",
            region="us-west-2",
        )

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["region"] == "us-west-2"

    @pytest.mark.asyncio
    async def test_unassign_application(self, manager, mock_client):
        """Should send null to unassign application."""
        await manager.unassign_application(device_ids=["device-1"])

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["application"]["id"] is None


# ============================================
# Archive/Unarchive Tests
# ============================================


class TestArchiveUnarchive:
    """Test archive/unarchive operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient."""
        client = MagicMock(spec=GLPClient)
        client.patch_merge = AsyncMock(
            return_value=AsyncOperationResult(operation_url="https://example.com/status")
        )
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    @pytest.mark.asyncio
    async def test_archive_devices(self, manager, mock_client):
        """Should send archive request."""
        await manager.archive_devices(device_ids=["device-1"])

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["archived"] is True

    @pytest.mark.asyncio
    async def test_unarchive_devices(self, manager, mock_client):
        """Should send unarchive request."""
        await manager.unarchive_devices(device_ids=["device-1"])

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["archived"] is False


# ============================================
# Subscription Operation Tests
# ============================================


class TestSubscriptionOperations:
    """Test subscription assignment operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient."""
        client = MagicMock(spec=GLPClient)
        client.patch_merge = AsyncMock(
            return_value=AsyncOperationResult(operation_url="https://example.com/status")
        )
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    @pytest.mark.asyncio
    async def test_assign_subscription(self, manager, mock_client):
        """Should send subscription assignment request."""
        await manager.assign_subscription(
            device_ids=["device-1"],
            subscription_id="sub-123",
        )

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["subscription"] == [{"id": "sub-123"}]

    @pytest.mark.asyncio
    async def test_unassign_subscription(self, manager, mock_client):
        """Should send empty array to unassign subscription."""
        await manager.unassign_subscription(device_ids=["device-1"])

        payload = mock_client.patch_merge.call_args[1]["json_body"]
        assert payload["subscription"] == []


# ============================================
# Operation Status Tests
# ============================================


class TestOperationStatus:
    """Test async operation status polling."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient."""
        client = MagicMock(spec=GLPClient)
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    @pytest.mark.asyncio
    async def test_get_operation_status(self, manager, mock_client):
        """Should fetch operation status."""
        mock_client.get = AsyncMock(
            return_value={
                "status": "COMPLETED",
                "progress": 100,
                "result": {"updated": 2},
            }
        )

        status = await manager.get_operation_status("/status/123")

        assert status.status == "COMPLETED"
        assert status.progress == 100
        assert status.is_complete
        assert status.is_success

    @pytest.mark.asyncio
    async def test_get_operation_status_failed(self, manager, mock_client):
        """Should return failed status with error."""
        mock_client.get = AsyncMock(
            return_value={
                "status": "FAILED",
                "error": "Device not found",
            }
        )

        status = await manager.get_operation_status("/status/123")

        assert status.status == "FAILED"
        assert status.error == "Device not found"
        assert status.is_complete
        assert not status.is_success

    @pytest.mark.asyncio
    async def test_wait_for_completion_success(self, manager, mock_client):
        """Should poll until completion."""
        mock_client.get = AsyncMock(
            side_effect=[
                {"status": "IN_PROGRESS", "progress": 50},
                {"status": "COMPLETED", "progress": 100},
            ]
        )

        status = await manager.wait_for_completion(
            "/status/123",
            poll_interval=0.1,
        )

        assert status.is_success
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_wait_for_completion_failure(self, manager, mock_client):
        """Should raise AsyncOperationError on failure."""
        mock_client.get = AsyncMock(
            return_value={"status": "FAILED", "error": "Invalid device"}
        )

        with pytest.raises(AsyncOperationError) as exc_info:
            await manager.wait_for_completion("/status/123", poll_interval=0.1)

        assert "Invalid device" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_wait_for_completion_timeout(self, manager, mock_client):
        """Should raise TimeoutError on timeout."""
        mock_client.get = AsyncMock(
            return_value={"status": "IN_PROGRESS", "progress": 50}
        )

        with pytest.raises(asyncio.TimeoutError):
            await manager.wait_for_completion(
                "/status/123",
                timeout=0.2,
                poll_interval=0.1,
            )

    @pytest.mark.asyncio
    async def test_wait_for_completion_requires_url(self, manager):
        """Should raise ValidationError if no URL provided."""
        with pytest.raises(ValidationError):
            await manager.wait_for_completion("")


# ============================================
# OperationStatus Data Class Tests
# ============================================


class TestOperationStatusDataclass:
    """Test OperationStatus data class properties."""

    def test_is_complete_for_completed(self):
        """Should be complete for COMPLETED status."""
        status = OperationStatus(status="COMPLETED")
        assert status.is_complete is True
        assert status.is_success is True

    def test_is_complete_for_failed(self):
        """Should be complete for FAILED status."""
        status = OperationStatus(status="FAILED")
        assert status.is_complete is True
        assert status.is_success is False

    def test_is_not_complete_for_in_progress(self):
        """Should not be complete for IN_PROGRESS status."""
        status = OperationStatus(status="IN_PROGRESS")
        assert status.is_complete is False
        assert status.is_success is False

    def test_is_not_complete_for_pending(self):
        """Should not be complete for PENDING status."""
        status = OperationStatus(status="PENDING")
        assert status.is_complete is False


# ============================================
# DeviceType Enum Tests
# ============================================


class TestDeviceTypeEnum:
    """Test DeviceType enum."""

    def test_device_types(self):
        """Should have correct device type values."""
        assert DeviceType.COMPUTE.value == "COMPUTE"
        assert DeviceType.NETWORK.value == "NETWORK"
        assert DeviceType.STORAGE.value == "STORAGE"

    def test_device_type_is_string(self):
        """DeviceType should be usable as string."""
        assert DeviceType.COMPUTE == "COMPUTE"


# ============================================
# Non-202 Response Edge Case Tests
# ============================================


class TestNon202ResponseEdgeCase:
    """Test handling when API returns non-202 response unexpectedly."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GLPClient that returns dict instead of AsyncOperationResult."""
        client = MagicMock(spec=GLPClient)
        # Simulate non-202 response (returns dict directly)
        client.patch_merge = AsyncMock(
            return_value=AsyncOperationResult(
                operation_url="",  # Empty URL indicates non-202
                response_body={"status": "OK", "message": "Completed synchronously"},
            )
        )
        client.post_async = AsyncMock(
            return_value=AsyncOperationResult(
                operation_url="",
                response_body={"status": "OK"},
            )
        )
        return client

    @pytest.fixture
    def manager(self, mock_client):
        """Create a DeviceManager with mocked client."""
        return DeviceManager(client=mock_client)

    @pytest.mark.asyncio
    async def test_patch_merge_non_202_returns_empty_operation_url(self, manager):
        """Should return AsyncOperationResult with empty operation_url for non-202."""
        result = await manager.update_tags(
            device_ids=["device-1"],
            tags={"key": "value"},
        )

        assert result.operation_url == ""
        assert result.response_body is not None

    @pytest.mark.asyncio
    async def test_post_async_non_202_returns_empty_operation_url(self, manager):
        """Should return AsyncOperationResult with empty operation_url for non-202."""
        result = await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.NETWORK,
            mac_address="00:11:22:33:44:55",
        )

        assert result.operation_url == ""

    @pytest.mark.asyncio
    async def test_wait_for_completion_with_empty_url_raises(self, manager):
        """Should raise ValidationError when operation_url is empty."""
        with pytest.raises(ValidationError):
            await manager.wait_for_completion("")
