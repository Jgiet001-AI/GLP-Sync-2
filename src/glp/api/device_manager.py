#!/usr/bin/env python3
"""Device Management Operations for HPE GreenLake Platform.

This module provides the DeviceManager class for write operations on devices
using the GreenLake Devices API v2beta1.

Architecture:
    DeviceManager handles all WRITE operations (POST/PATCH):
    - Add devices (COMPUTE, NETWORK, STORAGE)
    - Update device tags
    - Assign/unassign applications
    - Archive/unarchive devices
    - Assign/unassign subscriptions

    Read operations remain in DeviceSyncer (/devices/v1/devices).

API Details:
    - Endpoint: /devices/v2beta1/devices
    - Rate Limits: PATCH=20/min, POST=25/min per workspace
    - Max Devices: 25 per PATCH request
    - Async: Returns 202 Accepted with Location header

Example:
    async with GLPClient(token_manager) as client:
        manager = DeviceManager(client)

        # Add a network device
        result = await manager.add_device(
            serial_number="SN12345",
            device_type=DeviceType.NETWORK,
            mac_address="00:1B:44:11:3A:B7",
        )

        # Update tags on multiple devices
        result = await manager.update_tags(
            device_ids=["uuid1", "uuid2"],
            tags={"location": "San Jose", "old_tag": None},  # None removes tag
        )

        # Wait for completion
        status = await manager.wait_for_completion(result.operation_url)

Author: HPE GreenLake Team
"""
import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional
from urllib.parse import urlparse

from .client import AsyncOperationResult, GLPClient
from .exceptions import (
    AsyncOperationError,
    DeviceLimitError,
    ValidationError,
)

logger = logging.getLogger(__name__)


# ============================================
# Data Types
# ============================================

class DeviceType(str, Enum):
    """Device types supported by the GreenLake API."""
    COMPUTE = "COMPUTE"
    NETWORK = "NETWORK"
    STORAGE = "STORAGE"


@dataclass
class OperationStatus:
    """Status of an async operation.

    Attributes:
        status: Current status of the operation
        progress: Progress percentage (0-100) if available
        result: Result data if completed successfully
        error: Error message if failed
        raw_response: Full API response
    """
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"]
    progress: Optional[int] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    raw_response: Optional[dict] = None

    @property
    def is_complete(self) -> bool:
        """Check if operation has finished (success or failure)."""
        return self.status in ("COMPLETED", "FAILED")

    @property
    def is_success(self) -> bool:
        """Check if operation completed successfully."""
        return self.status == "COMPLETED"


# ============================================
# DeviceManager
# ============================================

class DeviceManager:
    """Manage device operations in GreenLake Platform (v2beta1 API).

    Handles all write operations:
    - Add devices (POST)
    - Update devices (PATCH): tags, application, archive
    - Manage subscriptions on devices (PATCH)

    Note: Read operations remain in DeviceSyncer.

    Attributes:
        client: GLPClient instance for API communication
    """

    ENDPOINT = "/devices/v2beta1/devices"
    MAX_DEVICES_PER_REQUEST = 25

    def __init__(self, client: GLPClient):
        """Initialize DeviceManager.

        Args:
            client: Configured GLPClient instance
        """
        self.client = client

    # ----------------------------------------
    # Validation Helpers
    # ----------------------------------------

    def _validate_device_ids(self, device_ids: list[str]) -> None:
        """Validate device IDs list.

        Args:
            device_ids: List of device UUIDs

        Raises:
            ValidationError: If list is empty
            DeviceLimitError: If list exceeds MAX_DEVICES_PER_REQUEST
        """
        if not device_ids:
            raise ValidationError(
                "At least one device ID is required",
                field="device_ids",
            )

        if len(device_ids) > self.MAX_DEVICES_PER_REQUEST:
            raise DeviceLimitError(
                device_count=len(device_ids),
                max_devices=self.MAX_DEVICES_PER_REQUEST,
            )

    # ----------------------------------------
    # Add Devices (POST)
    # ----------------------------------------

    async def add_device(
        self,
        serial_number: str,
        device_type: DeviceType,
        *,
        part_number: Optional[str] = None,
        mac_address: Optional[str] = None,
        tags: Optional[dict[str, str]] = None,
        location_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Add a device to the workspace.

        Args:
            serial_number: Serial number of the device
            device_type: Type of device (COMPUTE, NETWORK, STORAGE)
            part_number: Part number (required for COMPUTE/STORAGE)
            mac_address: MAC address (required for NETWORK)
            tags: Optional tags to apply to the device
            location_id: Optional location ID
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking

        Raises:
            ValidationError: If required fields are missing for device type
        """
        # Validate required fields based on device type
        if device_type == DeviceType.NETWORK:
            if not mac_address:
                raise ValidationError(
                    "mac_address is required for NETWORK devices",
                    field="mac_address",
                )
        else:  # COMPUTE or STORAGE
            if not part_number:
                raise ValidationError(
                    f"part_number is required for {device_type.value} devices",
                    field="part_number",
                )

        # Build request payload
        payload: dict = {
            "serialNumber": serial_number,
            "deviceType": device_type.value,
        }

        if part_number:
            payload["partNumber"] = part_number
        if mac_address:
            payload["macAddress"] = mac_address
        if tags:
            payload["tags"] = tags
        if location_id:
            payload["location"] = {"id": location_id}

        # Build query params
        params = {}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(f"Adding {device_type.value} device: {serial_number}")

        return await self.client.post_async(
            self.ENDPOINT,
            json_body=payload,
            params=params if params else None,
        )

    # ----------------------------------------
    # Update Tags (PATCH)
    # ----------------------------------------

    async def update_tags(
        self,
        device_ids: list[str],
        tags: dict[str, Optional[str]],
        *,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Add, update, or remove tags on devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            tags: Tag key-value pairs. Set value to None to remove a tag.
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking

        Raises:
            ValidationError: If device_ids is empty
            DeviceLimitError: If more than 25 devices

        Example:
            await manager.update_tags(
                device_ids=["uuid1", "uuid2"],
                tags={
                    "location": "San Jose",    # Add or update
                    "old_tag": None,           # Remove
                },
            )
        """
        self._validate_device_ids(device_ids)

        payload = {"tags": tags}
        params = {"id": device_ids}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(f"Updating tags on {len(device_ids)} device(s)")

        return await self.client.patch_merge(
            self.ENDPOINT,
            json_body=payload,
            params=params,
        )

    # ----------------------------------------
    # Application Assignment (PATCH)
    # ----------------------------------------

    async def assign_application(
        self,
        device_ids: list[str],
        application_id: str,
        *,
        region: Optional[str] = None,
        tenant_workspace_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Assign an application to devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            application_id: UUID of the application to assign
            region: Optional region for the application
            tenant_workspace_id: Optional tenant workspace ID
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking
        """
        self._validate_device_ids(device_ids)

        payload: dict = {
            "application": {"id": application_id}
        }
        if region:
            payload["region"] = region
        if tenant_workspace_id:
            payload["tenantWorkspaceId"] = tenant_workspace_id

        params = {"id": device_ids}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(
            f"Assigning application {application_id} to {len(device_ids)} device(s)"
        )

        return await self.client.patch_merge(
            self.ENDPOINT,
            json_body=payload,
            params=params,
        )

    async def unassign_application(
        self,
        device_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Remove application assignment from devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking
        """
        self._validate_device_ids(device_ids)

        payload = {"application": {"id": None}}

        params = {"id": device_ids}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(f"Unassigning application from {len(device_ids)} device(s)")

        return await self.client.patch_merge(
            self.ENDPOINT,
            json_body=payload,
            params=params,
        )

    # ----------------------------------------
    # Archive/Unarchive (PATCH)
    # ----------------------------------------

    async def archive_devices(
        self,
        device_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Archive devices.

        Note: Archive is an exclusive operation and cannot be combined
        with other device operations in the same API call.

        Args:
            device_ids: List of device UUIDs (max 25)
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking
        """
        self._validate_device_ids(device_ids)

        payload = {"archived": True}

        params = {"id": device_ids}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(f"Archiving {len(device_ids)} device(s)")

        return await self.client.patch_merge(
            self.ENDPOINT,
            json_body=payload,
            params=params,
        )

    async def unarchive_devices(
        self,
        device_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Unarchive devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking
        """
        self._validate_device_ids(device_ids)

        payload = {"archived": False}

        params = {"id": device_ids}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(f"Unarchiving {len(device_ids)} device(s)")

        return await self.client.patch_merge(
            self.ENDPOINT,
            json_body=payload,
            params=params,
        )

    # ----------------------------------------
    # Subscription Operations (PATCH)
    # ----------------------------------------

    async def assign_subscription(
        self,
        device_ids: list[str],
        subscription_id: str,
        *,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Assign a subscription to devices.

        Note: Subscription operations must be separate from device
        operations (tags, application, archive) in the API call.

        Args:
            device_ids: List of device UUIDs (max 25)
            subscription_id: UUID of the subscription to assign
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking
        """
        self._validate_device_ids(device_ids)

        payload = {
            "subscription": [{"id": subscription_id}]
        }

        params = {"id": device_ids}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(
            f"Assigning subscription {subscription_id} to {len(device_ids)} device(s)"
        )

        return await self.client.patch_merge(
            self.ENDPOINT,
            json_body=payload,
            params=params,
        )

    async def unassign_subscription(
        self,
        device_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> AsyncOperationResult:
        """Remove subscription from devices.

        Args:
            device_ids: List of device UUIDs (max 25)
            dry_run: If True, validate without executing

        Returns:
            AsyncOperationResult with operation_url for status tracking
        """
        self._validate_device_ids(device_ids)

        payload = {"subscription": []}

        params = {"id": device_ids}
        if dry_run:
            params["dry-run"] = "true"

        logger.info(f"Unassigning subscription from {len(device_ids)} device(s)")

        return await self.client.patch_merge(
            self.ENDPOINT,
            json_body=payload,
            params=params,
        )

    # ----------------------------------------
    # Async Operation Status
    # ----------------------------------------

    async def get_operation_status(
        self,
        operation_url: str,
    ) -> OperationStatus:
        """Get the status of an async operation.

        Args:
            operation_url: URL from AsyncOperationResult.operation_url

        Returns:
            OperationStatus with current status and any results/errors
        """
        # The operation_url is typically a full URL, but we need just the path
        # for our client
        if operation_url.startswith("http"):
            # Extract path from full URL
            parsed = urlparse(operation_url)
            endpoint = parsed.path
        else:
            endpoint = operation_url

        response = await self.client.get(endpoint)

        # Parse response into OperationStatus
        status = response.get("status", "PENDING")
        progress = response.get("progress")
        result = response.get("result")
        error = response.get("error") or response.get("errorMessage")

        return OperationStatus(
            status=status,
            progress=progress,
            result=result,
            error=error,
            raw_response=response,
        )

    async def wait_for_completion(
        self,
        operation_url: str,
        *,
        timeout: float = 300,
        poll_interval: float = 2.0,
    ) -> OperationStatus:
        """Wait for an async operation to complete.

        Polls the operation status until it completes or times out.

        Args:
            operation_url: URL from AsyncOperationResult.operation_url
            timeout: Maximum time to wait in seconds (default: 300)
            poll_interval: Time between status checks (default: 2.0)

        Returns:
            Final OperationStatus

        Raises:
            AsyncOperationError: If operation fails
            TimeoutError: If operation doesn't complete within timeout
        """
        if not operation_url:
            raise ValidationError(
                "operation_url is required",
                field="operation_url",
            )

        elapsed = 0.0
        last_status: Optional[OperationStatus] = None

        logger.info(f"Waiting for operation to complete: {operation_url}")

        while elapsed < timeout:
            status = await self.get_operation_status(operation_url)
            last_status = status

            if status.is_complete:
                if status.is_success:
                    logger.info("Operation completed successfully")
                    return status
                else:
                    logger.error(f"Operation failed: {status.error}")
                    raise AsyncOperationError(
                        f"Operation failed: {status.error}",
                        operation_url=operation_url,
                        operation_status=status.status,
                    )

            # Log progress if available
            if status.progress is not None:
                logger.debug(f"Operation progress: {status.progress}%")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout reached
        raise asyncio.TimeoutError(
            f"Operation did not complete within {timeout} seconds. "
            f"Last status: {last_status.status if last_status else 'unknown'}"
        )


# ============================================
# Standalone Test
# ============================================

if __name__ == "__main__":
    async def demo():
        """Demo DeviceManager usage."""
        from .auth import TokenManager
        from .client import GLPClient

        token_manager = TokenManager()

        async with GLPClient(token_manager) as client:
            manager = DeviceManager(client)

            # Example: Add a network device (dry run)
            result = await manager.add_device(
                serial_number="DEMO123",
                device_type=DeviceType.NETWORK,
                mac_address="00:11:22:33:44:55",
                tags={"environment": "demo"},
                dry_run=True,
            )
            print(f"Add device result: {result}")

    asyncio.run(demo())
