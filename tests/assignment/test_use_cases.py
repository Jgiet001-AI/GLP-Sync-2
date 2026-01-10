"""Tests for assignment use cases."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.glp.assignment.domain.entities import (
    DeviceAssignment,
    ExcelRow,
    OperationResult,
    ValidationResult,
)
from src.glp.assignment.use_cases import (
    ApplyAssignmentsUseCase,
    GetOptionsUseCase,
    ProcessExcelUseCase,
)


@pytest.fixture
def mock_excel_parser():
    parser = MagicMock()
    parser.parse.return_value = [
        ExcelRow(row_number=2, serial_number="SN001", mac_address="AA:BB:CC:DD:EE:FF"),
        ExcelRow(row_number=3, serial_number="SN002"),
    ]
    parser.validate.return_value = ValidationResult(is_valid=True)
    return parser


@pytest.fixture
def mock_device_repo():
    repo = AsyncMock()
    device_id = uuid4()
    repo.find_by_serials.return_value = [
        DeviceAssignment(
            serial_number="SN001",
            device_id=device_id,
            device_type="NETWORK",
            current_subscription_id=uuid4(),
        )
    ]
    repo.get_all_tags.return_value = [("location", "NYC"), ("env", "prod")]
    return repo


@pytest.fixture
def mock_subscription_repo():
    repo = AsyncMock()
    repo.get_available_subscriptions.return_value = []
    repo.get_region_mappings.return_value = []
    return repo


@pytest.fixture
def mock_device_manager():
    manager = AsyncMock()
    manager.add_device.return_value = OperationResult(
        success=True, operation_type="create", device_serials=["SN002"]
    )
    manager.assign_subscription.return_value = OperationResult(
        success=True, operation_type="subscription", device_ids=[uuid4()]
    )
    manager.assign_application.return_value = OperationResult(
        success=True, operation_type="application", device_ids=[uuid4()]
    )
    manager.update_tags.return_value = OperationResult(
        success=True, operation_type="tags", device_ids=[uuid4()]
    )
    manager.wait_for_completion.return_value = OperationResult(
        success=True, operation_type="async"
    )
    return manager


class TestProcessExcelUseCase:
    """Tests for ProcessExcelUseCase."""

    @pytest.mark.asyncio
    async def test_process_valid_excel(self, mock_excel_parser, mock_device_repo):
        use_case = ProcessExcelUseCase(
            excel_parser=mock_excel_parser,
            device_repo=mock_device_repo,
        )

        result = await use_case.execute(b"fake excel content")

        assert result.success is True
        assert result.total_rows == 2
        assert result.devices_found == 1  # SN001 found
        assert result.devices_not_found == 1  # SN002 not found

    @pytest.mark.asyncio
    async def test_process_validation_failure(self, mock_excel_parser, mock_device_repo):
        mock_excel_parser.validate.return_value = ValidationResult(
            is_valid=False,
            errors=[MagicMock(row_number=1, field="serial", message="Error")],
        )

        use_case = ProcessExcelUseCase(
            excel_parser=mock_excel_parser,
            device_repo=mock_device_repo,
        )

        result = await use_case.execute(b"fake excel content")

        assert result.success is False
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_process_parse_error(self, mock_excel_parser, mock_device_repo):
        mock_excel_parser.parse.side_effect = ValueError("Invalid file")

        use_case = ProcessExcelUseCase(
            excel_parser=mock_excel_parser,
            device_repo=mock_device_repo,
        )

        result = await use_case.execute(b"invalid content")

        assert result.success is False
        assert len(result.errors) == 1
        assert "Invalid file" in result.errors[0].message

    @pytest.mark.asyncio
    async def test_process_empty_file(self, mock_excel_parser, mock_device_repo):
        mock_excel_parser.parse.return_value = []

        use_case = ProcessExcelUseCase(
            excel_parser=mock_excel_parser,
            device_repo=mock_device_repo,
        )

        result = await use_case.execute(b"empty file")

        assert result.success is False
        assert "No data rows" in result.errors[0].message


class TestGetOptionsUseCase:
    """Tests for GetOptionsUseCase."""

    @pytest.mark.asyncio
    async def test_get_all_options(self, mock_subscription_repo, mock_device_repo):
        use_case = GetOptionsUseCase(
            subscription_repo=mock_subscription_repo,
            device_repo=mock_device_repo,
        )

        result = await use_case.execute()

        mock_subscription_repo.get_available_subscriptions.assert_called_once()
        mock_subscription_repo.get_region_mappings.assert_called_once()
        mock_device_repo.get_all_tags.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_options_with_device_type(self, mock_subscription_repo, mock_device_repo):
        use_case = GetOptionsUseCase(
            subscription_repo=mock_subscription_repo,
            device_repo=mock_device_repo,
        )

        await use_case.execute(device_type="NETWORK")

        mock_subscription_repo.get_available_subscriptions.assert_called_once_with(
            device_type="NETWORK"
        )


class TestApplyAssignmentsUseCase:
    """Tests for ApplyAssignmentsUseCase."""

    @pytest.mark.asyncio
    async def test_create_new_devices(self, mock_device_manager):
        use_case = ApplyAssignmentsUseCase(device_manager=mock_device_manager)

        assignments = [
            DeviceAssignment(
                serial_number="SN001",
                mac_address="AA:BB:CC:DD:EE:FF",
                device_type="NETWORK",
            )
        ]

        result = await use_case.execute(assignments)

        assert result.success is True
        assert result.devices_created == 1
        mock_device_manager.add_device.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_subscriptions(self, mock_device_manager):
        use_case = ApplyAssignmentsUseCase(device_manager=mock_device_manager)

        device_id = uuid4()
        sub_id = uuid4()

        assignments = [
            DeviceAssignment(
                serial_number="SN001",
                device_id=device_id,
                selected_subscription_id=sub_id,
            )
        ]

        result = await use_case.execute(assignments)

        assert result.success is True
        mock_device_manager.assign_subscription.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_applications(self, mock_device_manager):
        use_case = ApplyAssignmentsUseCase(device_manager=mock_device_manager)

        device_id = uuid4()
        app_id = uuid4()

        assignments = [
            DeviceAssignment(
                serial_number="SN001",
                device_id=device_id,
                selected_application_id=app_id,
                selected_region="us-west",  # Required with application_id
            )
        ]

        result = await use_case.execute(assignments)

        assert result.success is True
        mock_device_manager.assign_application.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tags(self, mock_device_manager):
        use_case = ApplyAssignmentsUseCase(device_manager=mock_device_manager)

        device_id = uuid4()

        assignments = [
            DeviceAssignment(
                serial_number="SN001",
                device_id=device_id,
                selected_tags={"location": "NYC"},
            )
        ]

        result = await use_case.execute(assignments)

        assert result.success is True
        mock_device_manager.update_tags.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_operations(self, mock_device_manager):
        """Test that devices are batched correctly (max 25 per API call)."""
        use_case = ApplyAssignmentsUseCase(device_manager=mock_device_manager)

        sub_id = uuid4()
        # Create 30 devices needing subscription assignment
        assignments = [
            DeviceAssignment(
                serial_number=f"SN{i:03d}",
                device_id=uuid4(),
                selected_subscription_id=sub_id,
            )
            for i in range(30)
        ]

        await use_case.execute(assignments)

        # Should be called twice: once for 25 devices, once for 5
        assert mock_device_manager.assign_subscription.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_errors(self, mock_device_manager):
        mock_device_manager.add_device.return_value = OperationResult(
            success=False,
            operation_type="create",
            device_serials=["SN001"],
            error="API error",
        )

        use_case = ApplyAssignmentsUseCase(device_manager=mock_device_manager)

        assignments = [
            DeviceAssignment(
                serial_number="SN001",
                device_type="NETWORK",
            )
        ]

        result = await use_case.execute(assignments)

        assert result.success is False
        assert result.errors == 1

    @pytest.mark.asyncio
    async def test_no_operations_when_nothing_needed(self, mock_device_manager):
        """Test that no API calls are made when devices don't need changes."""
        use_case = ApplyAssignmentsUseCase(device_manager=mock_device_manager)

        # Device already has everything assigned
        assignments = [
            DeviceAssignment(
                serial_number="SN001",
                device_id=uuid4(),
                current_subscription_id=uuid4(),
                current_application_id=uuid4(),
                current_tags={"location": "NYC"},
            )
        ]

        result = await use_case.execute(assignments)

        assert result.success is True
        mock_device_manager.add_device.assert_not_called()
        mock_device_manager.assign_subscription.assert_not_called()
        mock_device_manager.assign_application.assert_not_called()
        mock_device_manager.update_tags.assert_not_called()
