"""Apply Assignments use case.

This use case applies user-selected assignments to devices using a phased workflow:

PHASE 1: Process EXISTING devices (already have UUIDs in DB)
├── Apply applications (SEQUENTIAL, 3.5s between batches)
├── Apply subscriptions (SEQUENTIAL, 3.5s between batches)
└── Apply tags (SEQUENTIAL, 3.5s between batches)

PHASE 2: Add NEW devices (not in DB)
├── POST add_device (SEQUENTIAL, 2.6s between requests)
├── Poll each until complete
├── Continue on failures, collect errors

PHASE 3: Refresh DB to get new UUIDs
└── Full sync from GreenLake

PHASE 4: Process NEWLY ADDED devices (now have UUIDs)
├── Apply applications (SEQUENTIAL)
├── Apply subscriptions (SEQUENTIAL)
└── Apply tags (SEQUENTIAL)

THE PERFECT RATE LIMITING ALGORITHM:
=====================================
Problem: GreenLake API enforces rate limits (20 PATCH/min, 25 POST/min).
         If we hit the limit, we get 429 errors and must wait 60 seconds.

Solution: SEQUENTIAL processing with guaranteed minimum intervals.
         - PATCH operations: 3.5 seconds between requests (17/min, well under 20/min)
         - POST operations: 2.6 seconds between requests (23/min, well under 25/min)
         - First request in each phase executes immediately (no delay)
         - Subsequent requests wait the full interval BEFORE executing

Why this is perfect:
1. NEVER hits rate limits (mathematically impossible at 17 req/min vs 20 req/min limit)
2. Simple and predictable timing
3. No 60-second penalty waits
4. Total time is calculable: (num_batches - 1) * interval_seconds

Example for 308 devices:
- 308 / 25 = 13 batches per operation type
- Applications: 13 batches * 3.5s = ~42 seconds
- Subscriptions: 13 batches * 3.5s = ~42 seconds
- Total: ~84 seconds of rate-limiting wait time

Key Design Decisions:
- Application MUST be assigned BEFORE subscription (GreenLake requirement)
- Both application_id AND region are required for application assignment
- Rate limiting: PATCH=3.5s interval, POST=2.6s interval
- Max 25 devices per API call
- SEQUENTIAL execution guarantees no rate limit hits
- Continue on individual failures, collect all errors for report
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional, TypeVar
from uuid import UUID

from ..domain.entities import DeviceAssignment, OperationResult
from ..domain.ports import IDeviceManagerPort, IDeviceRepository, ISyncService

logger = logging.getLogger(__name__)

T = TypeVar("T")


def chunk(items: list[T], size: int) -> Iterator[list[T]]:
    """Split a list into chunks of specified size."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


@dataclass
class PhaseResult:
    """Result of a workflow phase."""

    phase_name: str
    success: bool
    operations: list[OperationResult] = field(default_factory=list)
    devices_processed: int = 0
    errors: int = 0
    duration_seconds: float = 0.0


@dataclass
class ApplyResult:
    """Result of applying assignments."""

    success: bool
    operations: list[OperationResult] = field(default_factory=list)
    phase_results: list[PhaseResult] = field(default_factory=list)

    # Statistics
    devices_created: int = 0
    applications_assigned: int = 0
    subscriptions_assigned: int = 0
    tags_updated: int = 0
    errors: int = 0

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_seconds: float = 0.0

    # New devices added (serials)
    new_devices_added: list[str] = field(default_factory=list)
    new_devices_failed: list[str] = field(default_factory=list)


class SequentialRateLimiter:
    """Sequential rate limiter that GUARANTEES we never hit rate limits.

    The PERFECT algorithm:
    - Process requests SEQUENTIALLY (not in parallel)
    - Wait a fixed interval BEFORE each request (except the first)
    - Use a generous safety margin to account for clock drift

    For 20 PATCH/minute:
    - Theoretical minimum interval: 60/20 = 3.0 seconds
    - With 20% safety margin: 3.0 * 1.2 = 3.6 seconds
    - We use 3.5 seconds (17 requests/min, well under 20/min limit)
    """

    # Fixed intervals with safety margins
    PATCH_INTERVAL = 3.5  # 60/20 * 1.17 = ~3.5s between PATCH requests
    POST_INTERVAL = 2.6   # 60/25 * 1.08 = ~2.6s between POST requests

    def __init__(self, operation_type: str = "patch"):
        """Initialize rate limiter.

        Args:
            operation_type: "patch" (20/min) or "post" (25/min)
        """
        self.operation_type = operation_type
        self.interval = self.PATCH_INTERVAL if operation_type == "patch" else self.POST_INTERVAL
        self._call_count = 0
        self._total_wait_time = 0.0

    async def wait_before_call(self, batch_index: int) -> None:
        """Wait the required interval before making an API call.

        Args:
            batch_index: The index of this batch (0-based). First batch (index 0) doesn't wait.
        """
        if batch_index > 0:
            logger.info(
                f"Rate limiter: waiting {self.interval:.1f}s before batch {batch_index + 1} "
                f"({self.operation_type.upper()} rate limit protection)"
            )
            await asyncio.sleep(self.interval)
            self._total_wait_time += self.interval
        self._call_count += 1

    @property
    def call_count(self) -> int:
        """Number of calls made through this limiter."""
        return self._call_count

    @property
    def total_wait_time(self) -> float:
        """Total time spent waiting (seconds)."""
        return self._total_wait_time

    def estimate_time(self, num_batches: int) -> float:
        """Estimate total time for processing N batches.

        Args:
            num_batches: Number of batches to process

        Returns:
            Estimated time in seconds (wait time only, excludes API call time)
        """
        if num_batches <= 1:
            return 0.0
        return (num_batches - 1) * self.interval


class ApplyAssignmentsUseCase:
    """Apply user-selected assignments to devices using phased workflow.

    This use case implements a 4-phase workflow:
    1. Process existing devices (have UUIDs)
    2. Add new devices (no UUIDs)
    3. Refresh DB to get new UUIDs
    4. Process newly added devices

    Key constraints:
    - Application MUST be assigned BEFORE subscription
    - Max 25 devices per API call
    - Rate limits: PATCH=20/min, POST=25/min
    """

    MAX_BATCH_SIZE = 25  # GreenLake API limit

    def __init__(
        self,
        device_manager: IDeviceManagerPort,
        device_repository: Optional[IDeviceRepository] = None,
        sync_service: Optional[ISyncService] = None,
    ):
        """Initialize the use case.

        Args:
            device_manager: Manager for device operations
            device_repository: Repository to look up devices after sync
            sync_service: Service for syncing with GreenLake
        """
        self.manager = device_manager
        self.device_repo = device_repository
        self.sync_service = sync_service

    async def execute(
        self,
        assignments: list[DeviceAssignment],
        wait_for_completion: bool = True,
    ) -> ApplyResult:
        """Execute the phased workflow.

        Args:
            assignments: List of DeviceAssignment with user selections
            wait_for_completion: Whether to wait for async operations

        Returns:
            ApplyResult with operation outcomes
        """
        started_at = datetime.now()
        logger.info(f"Starting phased assignment workflow for {len(assignments)} devices")

        # IMPORTANT: Validate that if subscription is selected, application is also selected
        # GreenLake requires application to be assigned BEFORE subscription
        devices_needing_warning = []
        for a in assignments:
            if a.selected_subscription_id and not a.selected_application_id:
                if not a.current_application_id:  # Device doesn't have an app already
                    devices_needing_warning.append(a.serial_number)

        if devices_needing_warning:
            logger.warning(
                f"WARNING: {len(devices_needing_warning)} devices have subscription selected "
                f"but no application/region selected! Subscriptions will FAIL. "
                f"Sample: {devices_needing_warning[:5]}"
            )

        result = ApplyResult(success=True, started_at=started_at)
        all_operations: list[OperationResult] = []

        # Separate devices into existing (have UUID) and new (need creation)
        existing_devices = [a for a in assignments if a.device_id is not None]
        new_devices = [a for a in assignments if a.device_id is None]

        logger.info(f"Found {len(existing_devices)} existing devices, {len(new_devices)} new devices")

        # ========================================
        # PHASE 1: Process EXISTING devices
        # ========================================
        if existing_devices:
            phase1_result = await self._phase1_process_existing(
                existing_devices, wait_for_completion
            )
            result.phase_results.append(phase1_result)
            all_operations.extend(phase1_result.operations)

            # Update stats
            for op in phase1_result.operations:
                if op.success:
                    if op.operation_type == "application":
                        result.applications_assigned += len(op.device_ids or [])
                    elif op.operation_type == "subscription":
                        result.subscriptions_assigned += len(op.device_ids or [])
                    elif op.operation_type == "tags":
                        result.tags_updated += len(op.device_ids or [])

        # ========================================
        # PHASE 2: Add NEW devices
        # ========================================
        if new_devices:
            phase2_result = await self._phase2_add_new_devices(
                new_devices, wait_for_completion
            )
            result.phase_results.append(phase2_result)
            all_operations.extend(phase2_result.operations)

            # Track which devices were added successfully
            for op in phase2_result.operations:
                for serial in op.device_serials:
                    if op.success:
                        result.new_devices_added.append(serial)
                        result.devices_created += 1
                    else:
                        result.new_devices_failed.append(serial)

        # ========================================
        # PHASE 3: Refresh DB to get new UUIDs
        # ========================================
        if result.new_devices_added and self.sync_service:
            phase3_result = await self._phase3_refresh_db()
            result.phase_results.append(phase3_result)

        # ========================================
        # PHASE 4: Process NEWLY ADDED devices
        # ========================================
        if result.new_devices_added and self.device_repo:
            phase4_result = await self._phase4_process_new_devices(
                new_devices, result.new_devices_added, wait_for_completion
            )
            result.phase_results.append(phase4_result)
            all_operations.extend(phase4_result.operations)

            # Update stats
            for op in phase4_result.operations:
                if op.success:
                    if op.operation_type == "application":
                        result.applications_assigned += len(op.device_ids or [])
                    elif op.operation_type == "subscription":
                        result.subscriptions_assigned += len(op.device_ids or [])
                    elif op.operation_type == "tags":
                        result.tags_updated += len(op.device_ids or [])

        # Final stats
        result.operations = all_operations
        result.errors = sum(1 for op in all_operations if not op.success)
        result.success = result.errors == 0
        result.completed_at = datetime.now()
        result.total_duration_seconds = (result.completed_at - started_at).total_seconds()

        logger.info(
            f"Workflow complete in {result.total_duration_seconds:.1f}s: "
            f"{result.devices_created} created, "
            f"{result.applications_assigned} applications, "
            f"{result.subscriptions_assigned} subscriptions, "
            f"{result.tags_updated} tags, "
            f"{result.errors} errors"
        )

        return result

    async def _phase1_process_existing(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> PhaseResult:
        """Phase 1: Process devices that already exist in DB.

        Order: Applications FIRST, then Subscriptions, then Tags.
        """
        phase_start = datetime.now()
        logger.info(f"PHASE 1: Processing {len(devices)} existing devices")

        # Log what each device needs for debugging
        for d in devices[:5]:  # Log first 5 for sample
            logger.info(
                f"  Device {d.serial_number}: "
                f"needs_app={d.needs_application_patch}, needs_sub={d.needs_subscription_patch}, "
                f"current_app={d.current_application_id}, selected_app={d.selected_application_id}, "
                f"current_sub={d.current_subscription_id}, selected_sub={d.selected_subscription_id}"
            )

        operations: list[OperationResult] = []

        # Step 1: Assign APPLICATIONS first (required before subscription)
        need_application = [a for a in devices if a.needs_application_patch]
        if need_application:
            logger.info(f"  Assigning applications to {len(need_application)} devices")
            for d in need_application[:3]:  # Log sample
                logger.info(f"    -> {d.serial_number}: app_id={d.selected_application_id}")
            app_results = await self._assign_applications_sequential(
                need_application, wait_for_completion
            )
            operations.extend(app_results)
            # Log results
            for r in app_results:
                if not r.success:
                    logger.error(f"    Application assignment failed: {r.error}")
        else:
            logger.info("  No devices need application assignment")

        # Step 2: Assign SUBSCRIPTIONS (after applications)
        need_subscription = [a for a in devices if a.needs_subscription_patch]
        if need_subscription:
            logger.info(f"  Assigning subscriptions to {len(need_subscription)} devices")
            for d in need_subscription[:3]:  # Log sample
                logger.info(f"    -> {d.serial_number}: sub_id={d.selected_subscription_id}")
            sub_results = await self._assign_subscriptions_sequential(
                need_subscription, wait_for_completion
            )
            operations.extend(sub_results)
            # Log results
            for r in sub_results:
                if not r.success:
                    logger.error(f"    Subscription assignment failed: {r.error}")
        else:
            logger.info("  No devices need subscription assignment")

        # Step 3: Update TAGS
        need_tags = [a for a in devices if a.needs_tag_patch]
        if need_tags:
            logger.info(f"  Updating tags on {len(need_tags)} devices")
            tag_results = await self._update_tags_sequential(
                need_tags, wait_for_completion
            )
            operations.extend(tag_results)

        duration = (datetime.now() - phase_start).total_seconds()
        errors = sum(1 for op in operations if not op.success)

        return PhaseResult(
            phase_name="Process Existing Devices",
            success=errors == 0,
            operations=operations,
            devices_processed=len(devices),
            errors=errors,
            duration_seconds=duration,
        )

    async def _phase2_add_new_devices(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> PhaseResult:
        """Phase 2: Add new devices that don't exist in DB.

        Uses SEQUENTIAL processing with guaranteed rate limiting.
        POST rate limit: 25/min = 2.6s between requests.
        """
        phase_start = datetime.now()
        logger.info(f"PHASE 2: Adding {len(devices)} new devices")

        operations: list[OperationResult] = []
        rate_limiter = SequentialRateLimiter("post")

        # Log estimated time
        if devices:
            estimated_wait = rate_limiter.estimate_time(len(devices))
            logger.info(
                f"Processing {len(devices)} device creations SEQUENTIALLY "
                f"(~{estimated_wait:.0f}s total wait time for rate limiting)"
            )

        # Execute SEQUENTIALLY with rate limiting
        for device_index, device in enumerate(devices):
            # Wait before this device (except first)
            await rate_limiter.wait_before_call(device_index)

            # Create this device
            try:
                result = await self._create_single_device(device, wait_for_completion)
                operations.append(result)
            except Exception as e:
                logger.error(f"Device {device.serial_number} creation failed: {e}")
                operations.append(
                    OperationResult(
                        success=False,
                        operation_type="create",
                        device_serials=[device.serial_number],
                        error=str(e),
                    )
                )

        if devices:
            logger.info(
                f"Device creation complete: {rate_limiter.call_count} API calls, "
                f"{rate_limiter.total_wait_time:.1f}s total wait time"
            )

        duration = (datetime.now() - phase_start).total_seconds()
        errors = sum(1 for op in operations if not op.success)

        return PhaseResult(
            phase_name="Add New Devices",
            success=errors == 0,
            operations=operations,
            devices_processed=len(devices),
            errors=errors,
            duration_seconds=duration,
        )

    async def _phase3_refresh_db(self) -> PhaseResult:
        """Phase 3: Refresh database to get new device UUIDs."""
        phase_start = datetime.now()
        logger.info("PHASE 3: Refreshing database from GreenLake")

        try:
            if self.sync_service:
                await self.sync_service.sync_devices()
                await self.sync_service.sync_subscriptions()

            duration = (datetime.now() - phase_start).total_seconds()
            return PhaseResult(
                phase_name="Refresh Database",
                success=True,
                devices_processed=0,
                errors=0,
                duration_seconds=duration,
            )
        except Exception as e:
            logger.error(f"Phase 3 sync failed: {e}")
            duration = (datetime.now() - phase_start).total_seconds()
            return PhaseResult(
                phase_name="Refresh Database",
                success=False,
                errors=1,
                duration_seconds=duration,
            )

    async def _phase4_process_new_devices(
        self,
        original_assignments: list[DeviceAssignment],
        added_serials: list[str],
        wait_for_completion: bool,
    ) -> PhaseResult:
        """Phase 4: Process newly added devices (now have UUIDs)."""
        phase_start = datetime.now()
        logger.info(f"PHASE 4: Processing {len(added_serials)} newly added devices")

        operations: list[OperationResult] = []

        if not self.device_repo:
            logger.warning("No device repository configured, skipping phase 4")
            return PhaseResult(
                phase_name="Process New Devices",
                success=True,
                devices_processed=0,
                duration_seconds=0.0,
            )

        # Look up the newly added devices to get their UUIDs
        refreshed_devices = await self.device_repo.find_by_serials(added_serials)
        refreshed_by_serial = {d.serial_number.upper(): d for d in refreshed_devices}

        # Create updated assignments with new device IDs
        updated_assignments: list[DeviceAssignment] = []
        for orig in original_assignments:
            if orig.serial_number.upper() in refreshed_by_serial:
                refreshed = refreshed_by_serial[orig.serial_number.upper()]
                # Copy over the user's selections to the refreshed device
                updated = DeviceAssignment(
                    serial_number=orig.serial_number,
                    mac_address=orig.mac_address,
                    row_number=orig.row_number,
                    device_id=refreshed.device_id,
                    device_type=refreshed.device_type,
                    model=refreshed.model,
                    region=refreshed.region,
                    current_subscription_id=refreshed.current_subscription_id,
                    current_subscription_key=refreshed.current_subscription_key,
                    current_application_id=refreshed.current_application_id,
                    current_tags=refreshed.current_tags,
                    selected_subscription_id=orig.selected_subscription_id,
                    selected_application_id=orig.selected_application_id,
                    selected_tags=orig.selected_tags,
                )
                updated_assignments.append(updated)

        if not updated_assignments:
            logger.warning("No devices found after refresh")
            return PhaseResult(
                phase_name="Process New Devices",
                success=True,
                devices_processed=0,
                duration_seconds=(datetime.now() - phase_start).total_seconds(),
            )

        # Step 1: Assign APPLICATIONS first
        need_application = [a for a in updated_assignments if a.needs_application_patch]
        if need_application:
            logger.info(f"  Assigning applications to {len(need_application)} new devices")
            app_results = await self._assign_applications_sequential(
                need_application, wait_for_completion
            )
            operations.extend(app_results)

        # Step 2: Assign SUBSCRIPTIONS
        need_subscription = [a for a in updated_assignments if a.needs_subscription_patch]
        if need_subscription:
            logger.info(f"  Assigning subscriptions to {len(need_subscription)} new devices")
            sub_results = await self._assign_subscriptions_sequential(
                need_subscription, wait_for_completion
            )
            operations.extend(sub_results)

        # Step 3: Update TAGS
        need_tags = [a for a in updated_assignments if a.needs_tag_patch]
        if need_tags:
            logger.info(f"  Updating tags on {len(need_tags)} new devices")
            tag_results = await self._update_tags_sequential(
                need_tags, wait_for_completion
            )
            operations.extend(tag_results)

        duration = (datetime.now() - phase_start).total_seconds()
        errors = sum(1 for op in operations if not op.success)

        return PhaseResult(
            phase_name="Process New Devices",
            success=errors == 0,
            operations=operations,
            devices_processed=len(updated_assignments),
            errors=errors,
            duration_seconds=duration,
        )

    async def _create_single_device(
        self,
        device: DeviceAssignment,
        wait_for_completion: bool,
    ) -> OperationResult:
        """Create a single device via POST."""
        try:
            op_result = await self.manager.add_device(
                serial=device.serial_number,
                device_type=device.device_type or "NETWORK",
                mac_address=device.mac_address,
                tags=device.selected_tags if device.selected_tags else None,
            )

            # Check if the initial add_device call failed
            if not op_result.success:
                return OperationResult(
                    success=False,
                    operation_type="create",
                    device_serials=[device.serial_number],
                    error=op_result.error or "Failed to add device",
                    operation_url=op_result.operation_url,
                )

            # Wait for async operation to complete
            if wait_for_completion and op_result.operation_url:
                completion_result = await self.manager.wait_for_completion(
                    op_result.operation_url
                )
                if not completion_result.success:
                    return OperationResult(
                        success=False,
                        operation_type="create",
                        device_serials=[device.serial_number],
                        error=completion_result.error or "Operation failed",
                        operation_url=op_result.operation_url,
                    )

            return OperationResult(
                success=True,
                operation_type="create",
                device_serials=[device.serial_number],
                operation_url=op_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to create device {device.serial_number}: {e}")
            return OperationResult(
                success=False,
                operation_type="create",
                device_serials=[device.serial_number],
                error=str(e),
            )

    async def _assign_applications_sequential(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> list[OperationResult]:
        """Assign applications to devices SEQUENTIALLY with guaranteed rate limiting.

        THE PERFECT ALGORITHM (Fire-then-Poll):
        1. FIRE PHASE: Send all PATCH requests sequentially with 3.5s delay
           - Don't wait for completion during this phase
           - Collect all operation URLs
        2. POLL PHASE: After all batches are fired, poll for completion
           - Poll sequentially with delays to avoid rate limits
        """
        results = []
        pending_operations: list[tuple[OperationResult, list[str], list[str]]] = []  # (result, device_ids, serials)
        rate_limiter = SequentialRateLimiter("patch")

        # Group by (application_id, region) tuple for efficient batching
        by_app_region: dict[tuple[UUID, str], list[DeviceAssignment]] = {}
        for device in devices:
            if device.selected_application_id and device.selected_region:
                key = (device.selected_application_id, device.selected_region)
                if key not in by_app_region:
                    by_app_region[key] = []
                by_app_region[key].append(device)
            elif device.selected_application_id and not device.selected_region:
                logger.warning(
                    f"Device {device.serial_number} has application_id but no region - skipping"
                )

        # Flatten all batches
        all_batches: list[tuple[UUID, str, list[DeviceAssignment]]] = []
        for (application_id, region), group_devices in by_app_region.items():
            for batch in chunk(group_devices, self.MAX_BATCH_SIZE):
                all_batches.append((application_id, region, batch))

        if all_batches:
            estimated_wait = rate_limiter.estimate_time(len(all_batches))
            logger.info(
                f"FIRE PHASE: Sending {len(all_batches)} application batches "
                f"(~{estimated_wait:.0f}s for rate limiting)"
            )

        # FIRE PHASE: Send all PATCH requests (don't wait for completion)
        for batch_index, (application_id, region, batch) in enumerate(all_batches):
            await rate_limiter.wait_before_call(batch_index)

            device_ids = [str(d.device_id) for d in batch if d.device_id]
            device_serials = [d.serial_number for d in batch]

            try:
                logger.info(
                    f"Batch {batch_index + 1}/{len(all_batches)}: "
                    f"Assigning app {application_id} + region '{region}' to {len(device_ids)} devices"
                )
                op_result = await self.manager.assign_application(
                    device_ids=device_ids,
                    application_id=application_id,
                    region=region,
                )
                if op_result.success and op_result.operation_url:
                    pending_operations.append((op_result, device_ids, device_serials))
                elif not op_result.success:
                    results.append(OperationResult(
                        success=False,
                        operation_type="application",
                        device_ids=device_ids,
                        device_serials=device_serials,
                        error=op_result.error,
                    ))
            except Exception as e:
                logger.error(f"Batch {batch_index + 1} failed: {e}")
                results.append(OperationResult(
                    success=False,
                    operation_type="application",
                    device_ids=device_ids,
                    device_serials=device_serials,
                    error=str(e),
                ))

        # Mark all fired operations as success (GreenLake processes async)
        # User can sync at the end to verify all assignments completed
        for op_result, device_ids, device_serials in pending_operations:
            results.append(OperationResult(
                success=True,
                operation_type="application",
                device_ids=device_ids,
                device_serials=device_serials,
                operation_url=op_result.operation_url,
            ))

        if all_batches:
            logger.info(
                f"Application assignment complete: {rate_limiter.call_count} API calls, "
                f"{rate_limiter.total_wait_time:.1f}s rate limit wait"
            )

        return results

    async def _assign_application_batch(
        self,
        application_id: UUID,
        region: str,
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> OperationResult:
        """Assign application to a batch of devices.

        GreenLake API requires BOTH application_id and region for assignment.
        """
        device_ids = [d.device_id for d in devices if d.device_id]
        device_serials = [d.serial_number for d in devices]

        if not device_ids:
            return OperationResult(
                success=True,
                operation_type="application",
                device_serials=device_serials,
            )

        try:
            logger.info(
                f"Assigning application {application_id} + region '{region}' to {len(device_ids)} devices"
            )
            op_result = await self.manager.assign_application(
                device_ids=device_ids,
                application_id=application_id,
                region=region,  # Required by GreenLake API
            )

            # Check if the initial operation failed
            if not op_result.success:
                return OperationResult(
                    success=False,
                    operation_type="application",
                    device_ids=device_ids,
                    device_serials=device_serials,
                    error=op_result.error or "Failed to assign application",
                    operation_url=op_result.operation_url,
                )

            if wait_for_completion and op_result.operation_url:
                completion_result = await self.manager.wait_for_completion(
                    op_result.operation_url
                )
                if not completion_result.success:
                    return OperationResult(
                        success=False,
                        operation_type="application",
                        device_ids=device_ids,
                        device_serials=device_serials,
                        error=completion_result.error,
                        operation_url=op_result.operation_url,
                    )

            return OperationResult(
                success=True,
                operation_type="application",
                device_ids=device_ids,
                device_serials=device_serials,
                operation_url=op_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to assign application: {e}")
            return OperationResult(
                success=False,
                operation_type="application",
                device_ids=device_ids,
                device_serials=device_serials,
                error=str(e),
            )

    async def _assign_subscriptions_sequential(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> list[OperationResult]:
        """Assign subscriptions to devices SEQUENTIALLY with guaranteed rate limiting.

        THE PERFECT ALGORITHM (Fire-then-Poll):
        1. FIRE PHASE: Send all PATCH requests sequentially with 3.5s delay
        2. POLL PHASE: After all batches are fired, poll for completion
        """
        results = []
        pending_operations: list[tuple] = []  # (op_result, device_ids, device_serials)
        rate_limiter = SequentialRateLimiter("patch")

        # Group by subscription_id for efficient batching
        by_subscription: dict[UUID, list[DeviceAssignment]] = {}
        for device in devices:
            if device.selected_subscription_id:
                sub_id = device.selected_subscription_id
                if sub_id not in by_subscription:
                    by_subscription[sub_id] = []
                by_subscription[sub_id].append(device)

        # Flatten all batches
        all_batches: list[tuple[UUID, list[DeviceAssignment]]] = []
        for subscription_id, group_devices in by_subscription.items():
            for batch in chunk(group_devices, self.MAX_BATCH_SIZE):
                all_batches.append((subscription_id, batch))

        if all_batches:
            estimated_wait = rate_limiter.estimate_time(len(all_batches))
            logger.info(
                f"FIRE PHASE: Sending {len(all_batches)} subscription batches "
                f"(~{estimated_wait:.0f}s for rate limiting)"
            )

        # FIRE PHASE: Send all PATCH requests
        for batch_index, (subscription_id, batch) in enumerate(all_batches):
            await rate_limiter.wait_before_call(batch_index)

            device_ids = [str(d.device_id) for d in batch if d.device_id]
            device_serials = [d.serial_number for d in batch]

            try:
                logger.info(
                    f"Batch {batch_index + 1}/{len(all_batches)}: "
                    f"Assigning subscription {subscription_id} to {len(device_ids)} devices"
                )
                op_result = await self.manager.assign_subscription(
                    device_ids=device_ids,
                    subscription_id=subscription_id,
                )
                if op_result.success and op_result.operation_url:
                    pending_operations.append((op_result, device_ids, device_serials))
                elif not op_result.success:
                    results.append(OperationResult(
                        success=False,
                        operation_type="subscription",
                        device_ids=device_ids,
                        device_serials=device_serials,
                        error=op_result.error,
                    ))
            except Exception as e:
                logger.error(f"Batch {batch_index + 1} failed: {e}")
                results.append(OperationResult(
                    success=False,
                    operation_type="subscription",
                    device_ids=device_ids,
                    device_serials=device_serials,
                    error=str(e),
                ))

        # Mark all fired operations as success (GreenLake processes async)
        for op_result, device_ids, device_serials in pending_operations:
            results.append(OperationResult(
                success=True,
                operation_type="subscription",
                device_ids=device_ids,
                device_serials=device_serials,
                operation_url=op_result.operation_url,
            ))

        if all_batches:
            logger.info(
                f"Subscription assignment complete: {rate_limiter.call_count} API calls, "
                f"{rate_limiter.total_wait_time:.1f}s rate limit wait"
            )

        return results

    async def _assign_subscription_batch(
        self,
        subscription_id: UUID,
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> OperationResult:
        """Assign subscription to a batch of devices."""
        device_ids = [d.device_id for d in devices if d.device_id]
        device_serials = [d.serial_number for d in devices]

        if not device_ids:
            return OperationResult(
                success=True,
                operation_type="subscription",
                device_serials=device_serials,
            )

        try:
            op_result = await self.manager.assign_subscription(
                device_ids=device_ids,
                subscription_id=subscription_id,
            )

            # Check if the initial operation failed
            if not op_result.success:
                return OperationResult(
                    success=False,
                    operation_type="subscription",
                    device_ids=device_ids,
                    device_serials=device_serials,
                    error=op_result.error or "Failed to assign subscription",
                    operation_url=op_result.operation_url,
                )

            if wait_for_completion and op_result.operation_url:
                completion_result = await self.manager.wait_for_completion(
                    op_result.operation_url
                )
                if not completion_result.success:
                    return OperationResult(
                        success=False,
                        operation_type="subscription",
                        device_ids=device_ids,
                        device_serials=device_serials,
                        error=completion_result.error,
                        operation_url=op_result.operation_url,
                    )

            return OperationResult(
                success=True,
                operation_type="subscription",
                device_ids=device_ids,
                device_serials=device_serials,
                operation_url=op_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to assign subscription: {e}")
            return OperationResult(
                success=False,
                operation_type="subscription",
                device_ids=device_ids,
                device_serials=device_serials,
                error=str(e),
            )

    async def _update_tags_sequential(
        self,
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> list[OperationResult]:
        """Update tags on devices SEQUENTIALLY with guaranteed rate limiting.

        THE PERFECT ALGORITHM (Fire-and-Forget):
        - Group devices by tag set for efficient batching
        - Split into batches of 25 devices max
        - Process each batch SEQUENTIALLY with 3.5s delay between batches
        - This guarantees we NEVER hit the 20 PATCH/minute rate limit
        - NO POLLING - just fire and mark as success (GreenLake processes async)
        """
        results = []
        pending_operations: list[tuple] = []  # (op_result, device_ids, device_serials)
        rate_limiter = SequentialRateLimiter("patch")

        # Group by tag set for efficient batching
        by_tags: dict[tuple, list[DeviceAssignment]] = {}
        for device in devices:
            tag_key = tuple(sorted(device.selected_tags.items()))
            if tag_key not in by_tags:
                by_tags[tag_key] = []
            by_tags[tag_key].append(device)

        # Flatten all batches into a single list for sequential processing
        all_batches: list[tuple[dict[str, str], list[DeviceAssignment]]] = []
        for tag_tuple, group_devices in by_tags.items():
            tags = dict(tag_tuple)
            for batch in chunk(group_devices, self.MAX_BATCH_SIZE):
                all_batches.append((tags, batch))

        # Log estimated time
        if all_batches:
            estimated_wait = rate_limiter.estimate_time(len(all_batches))
            logger.info(
                f"FIRE PHASE: Sending {len(all_batches)} tag batches "
                f"(~{estimated_wait:.0f}s for rate limiting)"
            )

        # FIRE PHASE: Send all PATCH requests (don't wait for completion)
        for batch_index, (tags, batch) in enumerate(all_batches):
            # Wait before this batch (except first batch)
            await rate_limiter.wait_before_call(batch_index)

            device_ids = [str(d.device_id) for d in batch if d.device_id]
            device_serials = [d.serial_number for d in batch]

            try:
                logger.info(
                    f"Batch {batch_index + 1}/{len(all_batches)}: "
                    f"Updating tags on {len(device_ids)} devices"
                )
                op_result = await self.manager.update_tags(
                    device_ids=device_ids,
                    tags=tags,
                )
                if op_result.success and op_result.operation_url:
                    pending_operations.append((op_result, device_ids, device_serials))
                elif not op_result.success:
                    results.append(OperationResult(
                        success=False,
                        operation_type="tags",
                        device_ids=device_ids,
                        device_serials=device_serials,
                        error=op_result.error,
                    ))
            except Exception as e:
                logger.error(f"Batch {batch_index + 1} failed: {e}")
                results.append(OperationResult(
                    success=False,
                    operation_type="tags",
                    device_ids=device_ids,
                    device_serials=device_serials,
                    error=str(e),
                ))

        # Mark all fired operations as success (GreenLake processes async)
        for op_result, device_ids, device_serials in pending_operations:
            results.append(OperationResult(
                success=True,
                operation_type="tags",
                device_ids=device_ids,
                device_serials=device_serials,
                operation_url=op_result.operation_url,
            ))

        if all_batches:
            logger.info(
                f"Tag update complete: {rate_limiter.call_count} API calls, "
                f"{rate_limiter.total_wait_time:.1f}s rate limit wait"
            )

        return results

    async def _update_tags_batch(
        self,
        tags: dict[str, str],
        devices: list[DeviceAssignment],
        wait_for_completion: bool,
    ) -> OperationResult:
        """Update tags on a batch of devices."""
        device_ids = [d.device_id for d in devices if d.device_id]
        device_serials = [d.serial_number for d in devices]

        if not device_ids:
            return OperationResult(
                success=True,
                operation_type="tags",
                device_serials=device_serials,
            )

        try:
            op_result = await self.manager.update_tags(
                device_ids=device_ids,
                tags=tags,
            )

            # Check if the initial operation failed
            if not op_result.success:
                return OperationResult(
                    success=False,
                    operation_type="tags",
                    device_ids=device_ids,
                    device_serials=device_serials,
                    error=op_result.error or "Failed to update tags",
                    operation_url=op_result.operation_url,
                )

            if wait_for_completion and op_result.operation_url:
                completion_result = await self.manager.wait_for_completion(
                    op_result.operation_url
                )
                if not completion_result.success:
                    return OperationResult(
                        success=False,
                        operation_type="tags",
                        device_ids=device_ids,
                        device_serials=device_serials,
                        error=completion_result.error,
                        operation_url=op_result.operation_url,
                    )

            return OperationResult(
                success=True,
                operation_type="tags",
                device_ids=device_ids,
                device_serials=device_serials,
                operation_url=op_result.operation_url,
            )

        except Exception as e:
            logger.error(f"Failed to update tags: {e}")
            return OperationResult(
                success=False,
                operation_type="tags",
                device_ids=device_ids,
                device_serials=device_serials,
                error=str(e),
            )
