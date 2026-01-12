"""Sync and Report use case.

This use case triggers a resync with GreenLake and generates
a comprehensive report of all operations performed.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..domain.entities import OperationResult
from ..domain.ports import IReportGenerator, ISyncService
from .apply_assignments import ApplyResult, PhaseResult

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of syncing with GreenLake."""

    success: bool
    devices_synced: int = 0
    subscriptions_synced: int = 0
    error: Optional[str] = None


@dataclass
class Report:
    """Final report of assignment operations."""

    generated_at: datetime = field(default_factory=datetime.now)

    # Operation summary
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0

    # Breakdown by type
    devices_created: int = 0
    applications_assigned: int = 0
    subscriptions_assigned: int = 0
    tags_updated: int = 0

    # Sync results
    sync_success: bool = False
    devices_synced: int = 0
    subscriptions_synced: int = 0

    # Phase information
    phase_results: list[PhaseResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    # New devices tracking
    new_devices_added: list[str] = field(default_factory=list)
    new_devices_failed: list[str] = field(default_factory=list)

    # Details
    operations: list[OperationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "summary": {
                "total_operations": self.total_operations,
                "successful_operations": self.successful_operations,
                "failed_operations": self.failed_operations,
            },
            "breakdown": {
                "devices_created": self.devices_created,
                "applications_assigned": self.applications_assigned,
                "subscriptions_assigned": self.subscriptions_assigned,
                "tags_updated": self.tags_updated,
            },
            "sync": {
                "success": self.sync_success,
                "devices_synced": self.devices_synced,
                "subscriptions_synced": self.subscriptions_synced,
            },
            "workflow": {
                "total_duration_seconds": self.total_duration_seconds,
                "new_devices_added": self.new_devices_added,
                "new_devices_failed": self.new_devices_failed,
            },
            "phases": [
                {
                    "phase_name": p.phase_name,
                    "success": p.success,
                    "devices_processed": p.devices_processed,
                    "errors": p.errors,
                    "duration_seconds": p.duration_seconds,
                }
                for p in self.phase_results
            ],
            "operations": [op.to_dict() for op in self.operations],
            "errors": self.errors,
        }


class SyncAndReportUseCase:
    """Sync with GreenLake and generate a comprehensive report.

    This use case:
    1. Triggers a full sync of devices and subscriptions from GreenLake
    2. Generates a report of all operations performed
    3. Optionally generates an Excel report with multiple sheets
    """

    def __init__(
        self,
        sync_service: ISyncService,
        report_generator: IReportGenerator,
    ):
        """Initialize the use case.

        Args:
            sync_service: Service for syncing with GreenLake
            report_generator: Generator for reports
        """
        self.sync = sync_service
        self.reporter = report_generator

    async def execute(
        self,
        operations: list[OperationResult],
        sync_after: bool = True,
        apply_result: Optional[ApplyResult] = None,
        sync_devices: bool = True,
        sync_subscriptions: bool = True,
    ) -> Report:
        """Execute the use case.

        Args:
            operations: List of operation results from apply step
            sync_after: Whether to sync with GreenLake after operations
            apply_result: Optional ApplyResult with phase information
            sync_devices: Whether to sync devices (default True)
            sync_subscriptions: Whether to sync subscriptions (default True)

        Returns:
            Report with all details
        """
        logger.info(f"Generating report for {len(operations)} operations")

        # 1. Calculate operation statistics
        report = Report(
            total_operations=len(operations),
            successful_operations=sum(1 for op in operations if op.success),
            failed_operations=sum(1 for op in operations if not op.success),
            operations=operations,
        )

        # Count by type
        for op in operations:
            if op.success:
                device_count = len(op.device_serials or []) or len(op.device_ids or [])
                if op.operation_type == "create":
                    report.devices_created += device_count
                elif op.operation_type == "application":
                    report.applications_assigned += device_count
                elif op.operation_type == "subscription":
                    report.subscriptions_assigned += device_count
                elif op.operation_type == "tags":
                    report.tags_updated += device_count

            if op.error:
                report.errors.append(op.error)

        # 2. Include phase information from ApplyResult
        if apply_result:
            report.phase_results = apply_result.phase_results
            report.total_duration_seconds = apply_result.total_duration_seconds
            report.new_devices_added = apply_result.new_devices_added
            report.new_devices_failed = apply_result.new_devices_failed

        # 3. Optionally sync with GreenLake
        if sync_after:
            logger.info(
                f"Syncing with GreenLake (devices={sync_devices}, subscriptions={sync_subscriptions})..."
            )
            sync_result = await self._sync(
                sync_devices=sync_devices,
                sync_subscriptions=sync_subscriptions,
            )
            report.sync_success = sync_result.success
            report.devices_synced = sync_result.devices_synced
            report.subscriptions_synced = sync_result.subscriptions_synced

            if sync_result.error:
                report.errors.append(f"Sync error: {sync_result.error}")

        logger.info(
            f"Report generated: "
            f"{report.successful_operations}/{report.total_operations} successful, "
            f"{report.failed_operations} failed"
        )

        return report

    async def _sync(
        self,
        sync_devices: bool = True,
        sync_subscriptions: bool = True,
    ) -> SyncResult:
        """Perform sync with GreenLake.

        Args:
            sync_devices: Whether to sync devices
            sync_subscriptions: Whether to sync subscriptions
        """
        try:
            devices_synced = 0
            subs_synced = 0

            # Sync devices (if enabled)
            if sync_devices:
                device_result = await self.sync.sync_devices()
                devices_synced = device_result.get("records_fetched", device_result.get("total", 0))

            # Sync subscriptions (if enabled)
            if sync_subscriptions:
                sub_result = await self.sync.sync_subscriptions()
                subs_synced = sub_result.get("records_fetched", sub_result.get("total", 0))

            return SyncResult(
                success=True,
                devices_synced=devices_synced,
                subscriptions_synced=subs_synced,
            )
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return SyncResult(
                success=False,
                error=str(e),
            )

    async def generate_excel_report(
        self,
        operations: list[OperationResult],
        sync_result: Optional[SyncResult] = None,
        apply_result: Optional[ApplyResult] = None,
    ) -> bytes:
        """Generate an Excel report.

        Args:
            operations: List of operation results
            sync_result: Optional sync results
            apply_result: Optional apply result with phase info

        Returns:
            Excel file bytes
        """
        # Build workflow stats
        workflow_stats = None
        phase_results = None

        if apply_result:
            workflow_stats = {
                "devices_created": apply_result.devices_created,
                "applications_assigned": apply_result.applications_assigned,
                "subscriptions_assigned": apply_result.subscriptions_assigned,
                "tags_updated": apply_result.tags_updated,
                "total_duration_seconds": apply_result.total_duration_seconds,
                "new_devices_added": apply_result.new_devices_added,
                "new_devices_failed": apply_result.new_devices_failed,
            }
            phase_results = apply_result.phase_results

        return self.reporter.generate_excel(
            operations=operations,
            sync_result=sync_result.__dict__ if sync_result else None,
            phase_results=phase_results,
            workflow_stats=workflow_stats,
        )
