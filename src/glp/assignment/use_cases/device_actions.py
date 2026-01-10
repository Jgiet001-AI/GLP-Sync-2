"""Device Actions use case.

This use case handles device management actions that are separate from
the main assignment workflow:

- ARCHIVE: Archive selected devices
- UNARCHIVE: Unarchive selected devices
- REMOVE: Remove devices from GreenLake (must be archived first)

These are simpler workflows compared to the full assignment process,
operating directly on a list of device IDs.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, TypeVar
from uuid import UUID

from ..domain.entities import DeviceAssignment, OperationResult, WorkflowAction
from ..domain.ports import IDeviceManagerPort, ISyncService

logger = logging.getLogger(__name__)

T = TypeVar("T")


def chunk(items: list[T], size: int) -> Iterator[list[T]]:
    """Split a list into chunks of specified size."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


@dataclass
class ActionResult:
    """Result of a device action workflow."""

    success: bool
    action: WorkflowAction
    operations: list[OperationResult] = field(default_factory=list)

    # Statistics
    devices_processed: int = 0
    devices_succeeded: int = 0
    devices_failed: int = 0

    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float = 0.0

    # Failed devices (for reporting)
    failed_device_ids: list[UUID] = field(default_factory=list)
    failed_device_serials: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "success": self.success,
            "action": self.action.value,
            "devices_processed": self.devices_processed,
            "devices_succeeded": self.devices_succeeded,
            "devices_failed": self.devices_failed,
            "total_duration_seconds": self.total_duration_seconds,
            "failed_device_ids": [str(d) for d in self.failed_device_ids],
            "failed_device_serials": self.failed_device_serials,
            "operations": [op.to_dict() for op in self.operations],
        }


class DeviceActionsUseCase:
    """Execute device management actions.

    This use case handles:
    - Archive: Set devices as archived
    - Unarchive: Restore archived devices
    - Remove: Permanently remove devices from GreenLake

    Key constraints:
    - Max 25 devices per API call
    - Remove requires devices to be archived first
    - Actions are applied in parallel with rate limiting
    """

    MAX_BATCH_SIZE = 25

    def __init__(
        self,
        device_manager: IDeviceManagerPort,
        sync_service: ISyncService | None = None,
    ):
        """Initialize the use case.

        Args:
            device_manager: Manager for device operations
            sync_service: Optional service for syncing after actions
        """
        self.manager = device_manager
        self.sync_service = sync_service

    async def execute(
        self,
        action: WorkflowAction,
        devices: list[DeviceAssignment],
        wait_for_completion: bool = True,
        sync_after: bool = True,
    ) -> ActionResult:
        """Execute a device action on selected devices.

        Args:
            action: The action to perform (ARCHIVE, UNARCHIVE, REMOVE)
            devices: List of DeviceAssignment with device IDs
            wait_for_completion: Whether to wait for async operations
            sync_after: Whether to sync database after action

        Returns:
            ActionResult with operation outcomes

        Raises:
            ValueError: If action is ASSIGN (use ApplyAssignmentsUseCase instead)
        """
        if action == WorkflowAction.ASSIGN:
            raise ValueError(
                "ASSIGN action should use ApplyAssignmentsUseCase, not DeviceActionsUseCase"
            )

        started_at = datetime.now()
        logger.info(f"Starting {action.value} action for {len(devices)} devices")

        result = ActionResult(
            success=True,
            action=action,
            started_at=started_at,
            devices_processed=len(devices),
        )

        # Filter to only devices that have IDs (exist in DB)
        valid_devices = [d for d in devices if d.device_id is not None]
        if len(valid_devices) < len(devices):
            missing_count = len(devices) - len(valid_devices)
            logger.warning(f"Skipping {missing_count} devices without IDs")

        if not valid_devices:
            logger.warning("No valid devices to process")
            result.completed_at = datetime.now()
            result.total_duration_seconds = (
                result.completed_at - started_at
            ).total_seconds()
            return result

        # Execute the action
        if action == WorkflowAction.ARCHIVE:
            operations = await self._execute_action_batched(
                valid_devices,
                self.manager.archive_devices,
                wait_for_completion,
            )
        elif action == WorkflowAction.UNARCHIVE:
            operations = await self._execute_action_batched(
                valid_devices,
                self.manager.unarchive_devices,
                wait_for_completion,
            )
        elif action == WorkflowAction.REMOVE:
            operations = await self._execute_action_batched(
                valid_devices,
                self.manager.remove_devices,
                wait_for_completion,
            )
        else:
            raise ValueError(f"Unknown action: {action}")

        # Collect results
        result.operations = operations
        for op in operations:
            if op.success:
                result.devices_succeeded += len(op.device_ids or [])
            else:
                result.devices_failed += len(op.device_ids or [])
                result.failed_device_ids.extend(op.device_ids or [])
                result.failed_device_serials.extend(op.device_serials or [])

        result.success = result.devices_failed == 0

        # Sync database after action if requested
        if sync_after and self.sync_service:
            try:
                await self.sync_service.sync_devices()
                logger.info("Database synced after action")
            except Exception as e:
                logger.error(f"Failed to sync database: {e}")
                # Don't fail the overall result for sync failures

        result.completed_at = datetime.now()
        result.total_duration_seconds = (
            result.completed_at - started_at
        ).total_seconds()

        logger.info(
            f"{action.value} complete in {result.total_duration_seconds:.1f}s: "
            f"{result.devices_succeeded} succeeded, {result.devices_failed} failed"
        )

        return result

    async def _execute_action_batched(
        self,
        devices: list[DeviceAssignment],
        action_func,
        wait_for_completion: bool,
    ) -> list[OperationResult]:
        """Execute an action on devices in batches.

        Args:
            devices: List of devices to process
            action_func: Async function to call (archive/unarchive/remove)
            wait_for_completion: Whether to wait for async operations

        Returns:
            List of OperationResult from all batches
        """
        results: list[OperationResult] = []

        # Process in batches of MAX_BATCH_SIZE
        device_id_batches = list(
            chunk([d.device_id for d in devices if d.device_id], self.MAX_BATCH_SIZE)
        )
        serial_batches = list(
            chunk([d.serial_number for d in devices], self.MAX_BATCH_SIZE)
        )

        for i, (id_batch, serial_batch) in enumerate(
            zip(device_id_batches, serial_batches)
        ):
            logger.debug(f"Processing batch {i + 1}/{len(device_id_batches)}")

            try:
                op_result = await action_func(device_ids=id_batch)

                # Add serials for reporting
                op_result.device_serials = serial_batch

                if not op_result.success:
                    results.append(op_result)
                    continue

                # Wait for async completion if requested
                if wait_for_completion and op_result.operation_url:
                    completion_result = await self.manager.wait_for_completion(
                        op_result.operation_url
                    )
                    if not completion_result.success:
                        results.append(
                            OperationResult(
                                success=False,
                                operation_type=op_result.operation_type,
                                device_ids=id_batch,
                                device_serials=serial_batch,
                                error=completion_result.error,
                                operation_url=op_result.operation_url,
                            )
                        )
                        continue

                results.append(op_result)

            except Exception as e:
                logger.error(f"Batch {i + 1} failed: {e}")
                results.append(
                    OperationResult(
                        success=False,
                        operation_type="unknown",
                        device_ids=id_batch,
                        device_serials=serial_batch,
                        error=str(e),
                    )
                )

        return results

    async def archive(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool = True,
        sync_after: bool = True,
    ) -> ActionResult:
        """Convenience method to archive devices.

        Args:
            devices: List of DeviceAssignment with device IDs
            wait_for_completion: Whether to wait for async operations
            sync_after: Whether to sync database after action

        Returns:
            ActionResult with operation outcomes
        """
        return await self.execute(
            WorkflowAction.ARCHIVE,
            devices,
            wait_for_completion,
            sync_after,
        )

    async def unarchive(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool = True,
        sync_after: bool = True,
    ) -> ActionResult:
        """Convenience method to unarchive devices.

        Args:
            devices: List of DeviceAssignment with device IDs
            wait_for_completion: Whether to wait for async operations
            sync_after: Whether to sync database after action

        Returns:
            ActionResult with operation outcomes
        """
        return await self.execute(
            WorkflowAction.UNARCHIVE,
            devices,
            wait_for_completion,
            sync_after,
        )

    async def remove(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool = True,
        sync_after: bool = True,
    ) -> ActionResult:
        """Convenience method to remove devices.

        Note: Devices should be archived before removal.

        Args:
            devices: List of DeviceAssignment with device IDs
            wait_for_completion: Whether to wait for async operations
            sync_after: Whether to sync database after action

        Returns:
            ActionResult with operation outcomes
        """
        return await self.execute(
            WorkflowAction.REMOVE,
            devices,
            wait_for_completion,
            sync_after,
        )
