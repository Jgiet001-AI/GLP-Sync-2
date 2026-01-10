"""GreenLake Platform DeviceManager adapter.

This adapter wraps the existing DeviceManager class to implement
the IDeviceManagerPort interface.
"""

import logging
from typing import Optional
from uuid import UUID

from ...api.device_manager import DeviceManager, DeviceType
from ..domain.entities import OperationResult
from ..domain.ports import IDeviceManagerPort

logger = logging.getLogger(__name__)


class GLPDeviceManagerAdapter(IDeviceManagerPort):
    """Adapter wrapping the existing DeviceManager.

    This adapter:
    - Converts between domain types and API types
    - Handles async operation waiting
    - Translates API responses to OperationResult
    """

    def __init__(self, device_manager: DeviceManager):
        """Initialize with an existing DeviceManager.

        Args:
            device_manager: Configured DeviceManager instance
        """
        self.manager = device_manager

    async def add_device(
        self,
        serial: str,
        device_type: str,
        mac_address: Optional[str] = None,
        part_number: Optional[str] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> OperationResult:
        """Add a new device via POST."""
        try:
            # Convert string to DeviceType enum
            dt = DeviceType(device_type.upper())

            # Call the underlying DeviceManager
            async_result = await self.manager.add_device(
                serial_number=serial,
                device_type=dt,
                mac_address=mac_address,
                part_number=part_number,
                tags=tags,
            )

            return OperationResult(
                success=True,
                operation_type="create",
                device_serials=[serial],
                operation_url=async_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to add device {serial}: {e}")
            return OperationResult(
                success=False,
                operation_type="create",
                device_serials=[serial],
                error=str(e),
            )

    async def assign_subscription(
        self,
        device_ids: list[UUID],
        subscription_id: UUID,
    ) -> OperationResult:
        """Assign a subscription to devices."""
        try:
            # Convert UUIDs to strings for the API
            device_id_strs = [str(d) for d in device_ids]

            async_result = await self.manager.assign_subscription(
                device_ids=device_id_strs,
                subscription_id=str(subscription_id),
            )

            return OperationResult(
                success=True,
                operation_type="subscription",
                device_ids=device_ids,
                operation_url=async_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to assign subscription: {e}")
            return OperationResult(
                success=False,
                operation_type="subscription",
                device_ids=device_ids,
                error=str(e),
            )

    async def assign_application(
        self,
        device_ids: list[UUID],
        application_id: UUID,
        region: Optional[str] = None,
    ) -> OperationResult:
        """Assign an application to devices."""
        try:
            # Convert UUIDs to strings for the API
            device_id_strs = [str(d) for d in device_ids]

            async_result = await self.manager.assign_application(
                device_ids=device_id_strs,
                application_id=str(application_id),
                region=region,
            )

            return OperationResult(
                success=True,
                operation_type="application",
                device_ids=device_ids,
                operation_url=async_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to assign application: {e}")
            return OperationResult(
                success=False,
                operation_type="application",
                device_ids=device_ids,
                error=str(e),
            )

    async def update_tags(
        self,
        device_ids: list[UUID],
        tags: dict[str, Optional[str]],
    ) -> OperationResult:
        """Update tags on devices."""
        try:
            # Convert UUIDs to strings for the API
            device_id_strs = [str(d) for d in device_ids]

            async_result = await self.manager.update_tags(
                device_ids=device_id_strs,
                tags=tags,
            )

            return OperationResult(
                success=True,
                operation_type="tags",
                device_ids=device_ids,
                operation_url=async_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to update tags: {e}")
            return OperationResult(
                success=False,
                operation_type="tags",
                device_ids=device_ids,
                error=str(e),
            )

    async def archive_devices(
        self,
        device_ids: list[UUID],
    ) -> OperationResult:
        """Archive devices."""
        try:
            device_id_strs = [str(d) for d in device_ids]

            async_result = await self.manager.archive_devices(
                device_ids=device_id_strs,
            )

            return OperationResult(
                success=True,
                operation_type="archive",
                device_ids=device_ids,
                operation_url=async_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to archive devices: {e}")
            return OperationResult(
                success=False,
                operation_type="archive",
                device_ids=device_ids,
                error=str(e),
            )

    async def unarchive_devices(
        self,
        device_ids: list[UUID],
    ) -> OperationResult:
        """Unarchive devices."""
        try:
            device_id_strs = [str(d) for d in device_ids]

            async_result = await self.manager.unarchive_devices(
                device_ids=device_id_strs,
            )

            return OperationResult(
                success=True,
                operation_type="unarchive",
                device_ids=device_ids,
                operation_url=async_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to unarchive devices: {e}")
            return OperationResult(
                success=False,
                operation_type="unarchive",
                device_ids=device_ids,
                error=str(e),
            )

    async def remove_devices(
        self,
        device_ids: list[UUID],
    ) -> OperationResult:
        """Remove devices from GreenLake."""
        try:
            device_id_strs = [str(d) for d in device_ids]

            async_result = await self.manager.remove_devices(
                device_ids=device_id_strs,
            )

            return OperationResult(
                success=True,
                operation_type="remove",
                device_ids=device_ids,
                operation_url=async_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to remove devices: {e}")
            return OperationResult(
                success=False,
                operation_type="remove",
                device_ids=device_ids,
                error=str(e),
            )

    async def wait_for_completion(
        self,
        operation_url: str,
        timeout: float = 300,
    ) -> OperationResult:
        """Wait for an async operation to complete."""
        try:
            status = await self.manager.wait_for_completion(
                operation_url=operation_url,
                timeout=timeout,
            )

            return OperationResult(
                success=status.is_success,
                operation_type="async",
                error=status.error,
                operation_url=operation_url,
            )

        except Exception as e:
            logger.error(f"Failed waiting for operation: {e}")
            return OperationResult(
                success=False,
                operation_type="async",
                error=str(e),
                operation_url=operation_url,
            )
