"""
Tests for device array limit enforcement in WriteExecutor.

Ensures the MAX_DEVICES_PER_OPERATION limit is properly enforced.
"""

import os
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from src.glp.agent.domain.entities import ToolCall, ToolDefinition, ToolResult, UserContext
from src.glp.agent.tools.write_executor import (
    DeviceLimitExceededError,
    WriteExecutor,
    WriteOperationType,
)


class MockDeviceManager:
    """Mock device manager for testing."""

    async def update_tags(self, device_ids, tags, *, dry_run=False):
        return {"updated": len(device_ids)}

    async def assign_application(self, device_ids, application_id, *, region=None, tenant_workspace_id=None, dry_run=False):
        return {"assigned": len(device_ids)}

    async def archive_devices(self, device_ids, *, dry_run=False):
        return {"archived": len(device_ids)}


class TestableWriteExecutor(WriteExecutor):
    """Concrete implementation of WriteExecutor for testing."""

    async def execute(
        self,
        tool_call: ToolCall,
        context: UserContext,
        idempotency_key: Optional[str] = None,
    ) -> ToolResult:
        """Execute a tool call (mock implementation)."""
        return ToolResult(success=True, data={"mocked": True})

    def is_read_tool(self, tool_name: str) -> bool:
        """Check if a tool is read-only."""
        return False

    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation."""
        return True

    async def get_all_tools(self) -> list[ToolDefinition]:
        """Get all available tools."""
        return []


@pytest.fixture
def executor():
    """Create a WriteExecutor with mock device manager."""
    return TestableWriteExecutor(MockDeviceManager())


class TestDeviceLimitValidation:
    """Tests for device ID array validation."""

    def test_validate_within_limit(self, executor):
        """Device count within limit passes validation."""
        device_ids = [f"device-{i}" for i in range(25)]
        result = executor._validate_device_ids(device_ids, "test_op")
        assert len(result) == 25

    def test_validate_exactly_at_limit(self, executor):
        """Exactly at the limit (25) is allowed."""
        device_ids = [f"device-{i}" for i in range(25)]
        result = executor._validate_device_ids(device_ids, "test_op")
        assert len(result) == 25

    def test_validate_exceeds_limit(self, executor):
        """Exceeding limit raises DeviceLimitExceededError."""
        device_ids = [f"device-{i}" for i in range(26)]
        with pytest.raises(DeviceLimitExceededError) as exc_info:
            executor._validate_device_ids(device_ids, "test_op")

        assert exc_info.value.count == 26
        assert exc_info.value.limit == 25
        assert "test_op" in exc_info.value.operation
        assert "split into smaller batches" in str(exc_info.value)

    def test_validate_large_array(self, executor):
        """Large arrays (100+ devices) are rejected."""
        device_ids = [f"device-{i}" for i in range(100)]
        with pytest.raises(DeviceLimitExceededError) as exc_info:
            executor._validate_device_ids(device_ids, "bulk_op")

        assert exc_info.value.count == 100
        assert exc_info.value.limit == 25

    def test_validate_empty_array(self, executor):
        """Empty array is allowed."""
        result = executor._validate_device_ids([], "test_op")
        assert result == []


class TestDeduplication:
    """Tests for device ID deduplication."""

    def test_duplicates_are_removed(self, executor):
        """Duplicate device IDs are removed."""
        device_ids = ["device-1", "device-2", "device-1", "device-3", "device-2"]
        result = executor._validate_device_ids(device_ids, "test_op")
        assert len(result) == 3
        assert result == ["device-1", "device-2", "device-3"]

    def test_order_preserved_after_dedup(self, executor):
        """Order is preserved after deduplication."""
        device_ids = ["z-device", "a-device", "m-device", "a-device"]
        result = executor._validate_device_ids(device_ids, "test_op")
        assert result == ["z-device", "a-device", "m-device"]

    def test_limit_checked_after_dedup(self, executor):
        """Limit is checked AFTER deduplication."""
        # 30 IDs but only 20 unique
        device_ids = [f"device-{i % 20}" for i in range(30)]
        result = executor._validate_device_ids(device_ids, "test_op")
        assert len(result) == 20  # Passes because only 20 unique


class TestPrepareOperationValidation:
    """Tests for validation in prepare_operation."""

    def test_prepare_validates_device_count(self, executor):
        """prepare_operation validates device count."""
        with pytest.raises(DeviceLimitExceededError):
            executor.prepare_operation(
                WriteOperationType.UPDATE_TAGS,
                {"device_ids": [f"d-{i}" for i in range(30)], "tags": {"key": "value"}},
            )

    def test_prepare_deduplicates_before_check(self, executor):
        """prepare_operation deduplicates before limit check."""
        # 40 total but only 20 unique
        device_ids = [f"device-{i % 20}" for i in range(40)]
        operation = executor.prepare_operation(
            WriteOperationType.UPDATE_TAGS,
            {"device_ids": device_ids, "tags": {"key": "value"}},
        )
        assert len(operation.arguments["device_ids"]) == 20

    def test_prepare_updates_arguments_with_deduped(self, executor):
        """prepare_operation updates arguments with deduplicated list."""
        device_ids = ["d1", "d2", "d1", "d3"]
        operation = executor.prepare_operation(
            WriteOperationType.ARCHIVE_DEVICES,
            {"device_ids": device_ids},
        )
        assert operation.arguments["device_ids"] == ["d1", "d2", "d3"]


class TestConfigurableLimit:
    """Tests for configurable MAX_DEVICES_PER_OPERATION."""

    def test_custom_limit_via_class_attribute(self, executor):
        """Limit can be configured via class attribute."""
        # Save original
        original_limit = executor.MAX_DEVICES_PER_OPERATION
        try:
            # Set custom limit
            executor.MAX_DEVICES_PER_OPERATION = 10

            # 10 devices should pass
            result = executor._validate_device_ids([f"d-{i}" for i in range(10)], "test")
            assert len(result) == 10

            # 11 devices should fail
            with pytest.raises(DeviceLimitExceededError) as exc_info:
                executor._validate_device_ids([f"d-{i}" for i in range(11)], "test")
            assert exc_info.value.limit == 10
        finally:
            executor.MAX_DEVICES_PER_OPERATION = original_limit

    def test_default_limit_is_25(self, executor):
        """Default limit is 25 if env var not set."""
        assert executor.MAX_DEVICES_PER_OPERATION == 25


class TestErrorMessageQuality:
    """Tests for error message quality."""

    def test_error_message_includes_counts(self, executor):
        """Error message includes actual and limit counts."""
        with pytest.raises(DeviceLimitExceededError) as exc_info:
            executor._validate_device_ids([f"d-{i}" for i in range(50)], "archive")

        error_str = str(exc_info.value)
        assert "50" in error_str  # Actual count
        assert "25" in error_str  # Limit

    def test_error_message_includes_operation(self, executor):
        """Error message includes operation name."""
        with pytest.raises(DeviceLimitExceededError) as exc_info:
            executor._validate_device_ids([f"d-{i}" for i in range(30)], "update_tags")

        assert "update_tags" in str(exc_info.value)

    def test_error_message_suggests_batching(self, executor):
        """Error message suggests batching as solution."""
        with pytest.raises(DeviceLimitExceededError) as exc_info:
            executor._validate_device_ids([f"d-{i}" for i in range(30)], "test")

        assert "batch" in str(exc_info.value).lower()
