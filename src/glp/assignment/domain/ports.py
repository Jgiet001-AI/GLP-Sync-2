"""Port interfaces for device assignment.

These are abstract interfaces (ports) that define how the domain
interacts with external systems. Concrete implementations (adapters)
are provided in the adapters module.

This follows the Hexagonal Architecture pattern.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from uuid import UUID

from .entities import (
    DeviceAssignment,
    ExcelRow,
    OperationResult,
    RegionMapping,
    SubscriptionOption,
    ValidationResult,
)


class IDeviceRepository(ABC):
    """Port for device data access.

    Implementations might use PostgreSQL, in-memory storage, etc.
    """

    @abstractmethod
    async def find_by_serial(self, serial: str) -> Optional[DeviceAssignment]:
        """Find a device by serial number.

        Args:
            serial: Device serial number

        Returns:
            DeviceAssignment if found, None otherwise
        """
        ...

    @abstractmethod
    async def find_by_mac(self, mac: str) -> Optional[DeviceAssignment]:
        """Find a device by MAC address.

        Args:
            mac: Device MAC address

        Returns:
            DeviceAssignment if found, None otherwise
        """
        ...

    @abstractmethod
    async def find_by_serials(self, serials: list[str]) -> list[DeviceAssignment]:
        """Find multiple devices by serial numbers.

        Args:
            serials: List of serial numbers

        Returns:
            List of DeviceAssignment for found devices
        """
        ...

    @abstractmethod
    async def get_all_tags(self) -> list[tuple[str, str]]:
        """Get all unique tag key-value pairs in the database.

        Returns:
            List of (key, value) tuples
        """
        ...


class ISubscriptionRepository(ABC):
    """Port for subscription data access."""

    @abstractmethod
    async def get_available_subscriptions(
        self,
        device_type: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[SubscriptionOption]:
        """Get subscriptions available for assignment.

        Args:
            device_type: Optional filter by device type (NETWORK, COMPUTE, STORAGE)
            model: Optional filter by device model (checks model series compatibility)

        Returns:
            List of available SubscriptionOption
        """
        ...

    @abstractmethod
    async def get_region_mappings(self) -> list[RegionMapping]:
        """Get all available region mappings.

        Returns:
            List of RegionMapping (application_id -> region name)
        """
        ...

    @abstractmethod
    async def get_subscription_by_id(self, subscription_id: UUID) -> Optional[SubscriptionOption]:
        """Get a specific subscription by ID.

        Args:
            subscription_id: Subscription UUID

        Returns:
            SubscriptionOption if found, None otherwise
        """
        ...


class IDeviceManagerPort(ABC):
    """Port for device management operations.

    Wraps the GreenLake API device management operations.
    """

    @abstractmethod
    async def add_device(
        self,
        serial: str,
        device_type: str,
        mac_address: Optional[str] = None,
        part_number: Optional[str] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> OperationResult:
        """Add a new device via POST.

        Args:
            serial: Device serial number
            device_type: Type of device (NETWORK, COMPUTE, STORAGE)
            mac_address: MAC address (required for NETWORK)
            part_number: Part number (required for COMPUTE/STORAGE)
            tags: Optional initial tags

        Returns:
            OperationResult with success status
        """
        ...

    @abstractmethod
    async def assign_subscription(
        self,
        device_ids: list[UUID],
        subscription_id: UUID,
    ) -> OperationResult:
        """Assign a subscription to devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            subscription_id: Subscription UUID to assign

        Returns:
            OperationResult with success status
        """
        ...

    @abstractmethod
    async def assign_application(
        self,
        device_ids: list[UUID],
        application_id: UUID,
        region: Optional[str] = None,
    ) -> OperationResult:
        """Assign an application to devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            application_id: Application UUID to assign
            region: Optional region

        Returns:
            OperationResult with success status
        """
        ...

    @abstractmethod
    async def update_tags(
        self,
        device_ids: list[UUID],
        tags: dict[str, Optional[str]],
    ) -> OperationResult:
        """Update tags on devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            tags: Tag key-value pairs. None value removes the tag.

        Returns:
            OperationResult with success status
        """
        ...

    @abstractmethod
    async def archive_devices(
        self,
        device_ids: list[UUID],
    ) -> OperationResult:
        """Archive devices.

        Args:
            device_ids: List of device UUIDs (max 25)

        Returns:
            OperationResult with success status
        """
        ...

    @abstractmethod
    async def unarchive_devices(
        self,
        device_ids: list[UUID],
    ) -> OperationResult:
        """Unarchive devices.

        Args:
            device_ids: List of device UUIDs (max 25)

        Returns:
            OperationResult with success status
        """
        ...

    @abstractmethod
    async def remove_devices(
        self,
        device_ids: list[UUID],
    ) -> OperationResult:
        """Remove devices from GreenLake.

        Args:
            device_ids: List of device UUIDs (max 25)

        Returns:
            OperationResult with success status
        """
        ...

    @abstractmethod
    async def wait_for_completion(
        self,
        operation_url: str,
        timeout: float = 300,
    ) -> OperationResult:
        """Wait for an async operation to complete.

        Args:
            operation_url: URL from async operation response
            timeout: Maximum wait time in seconds

        Returns:
            OperationResult with final status
        """
        ...


class IExcelParser(ABC):
    """Port for Excel file parsing."""

    @abstractmethod
    def parse(self, file_content: bytes) -> list[ExcelRow]:
        """Parse an Excel file.

        Args:
            file_content: Raw bytes of the Excel file

        Returns:
            List of ExcelRow objects

        Raises:
            ValueError: If file format is invalid
        """
        ...

    @abstractmethod
    def validate(self, rows: list[ExcelRow]) -> ValidationResult:
        """Validate parsed Excel rows.

        Args:
            rows: List of ExcelRow to validate

        Returns:
            ValidationResult with any errors
        """
        ...


class ISyncService(ABC):
    """Port for synchronization with GreenLake."""

    @abstractmethod
    async def sync_devices(self) -> dict:
        """Sync all devices from GreenLake to database.

        Returns:
            Sync statistics (records fetched, inserted, updated)
        """
        ...

    @abstractmethod
    async def sync_subscriptions(self) -> dict:
        """Sync all subscriptions from GreenLake to database.

        Returns:
            Sync statistics
        """
        ...


class IReportGenerator(ABC):
    """Port for generating reports."""

    @abstractmethod
    def generate(
        self,
        operations: list[OperationResult],
        sync_result: Optional[dict] = None,
        phase_results: Optional[list[dict]] = None,
        workflow_stats: Optional[dict] = None,
    ) -> dict:
        """Generate a report of assignment operations.

        Args:
            operations: List of operation results
            sync_result: Optional sync statistics
            phase_results: Optional phase-by-phase results
            workflow_stats: Optional workflow-level statistics

        Returns:
            Report data structure
        """
        ...

    @abstractmethod
    def generate_excel(
        self,
        operations: list[OperationResult],
        sync_result: Optional[dict] = None,
        phase_results: Optional[list[Any]] = None,
        workflow_stats: Optional[dict] = None,
    ) -> bytes:
        """Generate an Excel report.

        Args:
            operations: List of operation results
            sync_result: Optional sync statistics
            phase_results: Optional phase-by-phase results
            workflow_stats: Optional workflow-level statistics

        Returns:
            Excel file bytes
        """
        ...
