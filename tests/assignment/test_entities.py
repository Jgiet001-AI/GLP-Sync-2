"""Tests for domain entities."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.glp.assignment.domain.entities import (
    AssignmentStatus,
    DeviceAssignment,
    ExcelRow,
    SubscriptionOption,
    ValidationResult,
    ValidationError,
)


class TestExcelRow:
    """Tests for ExcelRow entity."""

    def test_normalizes_serial_number(self):
        row = ExcelRow(row_number=1, serial_number="  sn12345  ")
        assert row.serial_number == "SN12345"

    def test_normalizes_mac_address(self):
        row = ExcelRow(row_number=1, serial_number="SN123", mac_address="aa:bb:cc:dd:ee:ff")
        assert row.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_handles_none_mac_address(self):
        row = ExcelRow(row_number=1, serial_number="SN123")
        assert row.mac_address is None


class TestDeviceAssignment:
    """Tests for DeviceAssignment entity."""

    def test_status_not_in_db(self):
        assignment = DeviceAssignment(serial_number="SN123")
        assert assignment.status == AssignmentStatus.NOT_IN_DB
        assert assignment.needs_creation is True

    def test_status_fully_assigned(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            current_subscription_id=uuid4(),
            current_application_id=uuid4(),
        )
        assert assignment.status == AssignmentStatus.FULLY_ASSIGNED
        assert assignment.needs_creation is False

    def test_status_partial_with_subscription_only(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            current_subscription_id=uuid4(),
        )
        assert assignment.status == AssignmentStatus.PARTIAL

    def test_status_partial_with_application_only(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            current_application_id=uuid4(),
        )
        assert assignment.status == AssignmentStatus.PARTIAL

    def test_status_unassigned(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
        )
        assert assignment.status == AssignmentStatus.UNASSIGNED

    def test_needs_subscription_patch(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            selected_subscription_id=uuid4(),
        )
        assert assignment.needs_subscription_patch is True

    def test_no_subscription_patch_when_already_has_one(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            current_subscription_id=uuid4(),
            selected_subscription_id=uuid4(),
        )
        assert assignment.needs_subscription_patch is False

    def test_needs_application_patch(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            selected_application_id=uuid4(),
        )
        assert assignment.needs_application_patch is True

    def test_needs_tag_patch(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            selected_tags={"location": "NYC"},
        )
        assert assignment.needs_tag_patch is True

    def test_no_tag_patch_when_same_tags(self):
        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=uuid4(),
            current_tags={"location": "NYC"},
            selected_tags={"location": "NYC"},
        )
        assert assignment.needs_tag_patch is False

    def test_to_dict(self):
        device_id = uuid4()
        sub_id = uuid4()

        assignment = DeviceAssignment(
            serial_number="SN123",
            device_id=device_id,
            current_subscription_id=sub_id,
        )

        result = assignment.to_dict()

        assert result["serial_number"] == "SN123"
        assert result["device_id"] == str(device_id)
        assert result["current_subscription_id"] == str(sub_id)
        assert result["status"] == "partial"


class TestSubscriptionOption:
    """Tests for SubscriptionOption entity."""

    def test_compatible_device_types_for_ap(self):
        sub = SubscriptionOption(
            id=uuid4(),
            key="SUB123",
            subscription_type="CENTRAL_AP",
            tier="FOUNDATION",
        )
        assert sub.compatible_device_types == ["NETWORK"]
        assert sub.is_compatible_with("NETWORK") is True
        assert sub.is_compatible_with("COMPUTE") is False

    def test_compatible_device_types_for_switch(self):
        sub = SubscriptionOption(
            id=uuid4(),
            key="SUB123",
            subscription_type="CENTRAL_SWITCH",
            tier="FOUNDATION",
        )
        assert sub.is_compatible_with("NETWORK") is True

    def test_days_remaining(self):
        future = datetime.now(timezone.utc).replace(
            year=datetime.now().year + 1
        )
        sub = SubscriptionOption(
            id=uuid4(),
            key="SUB123",
            subscription_type="CENTRAL_AP",
            tier="FOUNDATION",
            end_time=future,
        )
        assert sub.days_remaining is not None
        assert sub.days_remaining > 0

    def test_days_remaining_none_when_no_end_time(self):
        sub = SubscriptionOption(
            id=uuid4(),
            key="SUB123",
            subscription_type="CENTRAL_AP",
            tier="FOUNDATION",
        )
        assert sub.days_remaining is None


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_is_valid_with_no_errors(self):
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_is_invalid_with_errors(self):
        result = ValidationResult(
            is_valid=False,
            errors=[
                ValidationError(row_number=1, field="serial", message="Required")
            ],
        )
        assert result.is_valid is False
        assert len(result.errors) == 1
