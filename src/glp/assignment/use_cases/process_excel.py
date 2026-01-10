"""Process Excel use case.

This use case handles uploading and processing an Excel file
containing device serial numbers and MAC addresses.
"""

import logging
from typing import Optional

from ..domain.entities import (
    AssignmentStatus,
    DeviceAssignment,
    ProcessResult,
    ValidationError,
)
from ..domain.ports import IDeviceRepository, IExcelParser

logger = logging.getLogger(__name__)


class ProcessExcelUseCase:
    """Process an Excel file and look up devices in the database.

    This use case:
    1. Parses the Excel file to extract serial numbers and MAC addresses
    2. Validates the parsed data
    3. Looks up each device in the database
    4. Returns a list of DeviceAssignment with current state and gaps
    """

    def __init__(
        self,
        excel_parser: IExcelParser,
        device_repo: IDeviceRepository,
    ):
        """Initialize the use case.

        Args:
            excel_parser: Parser for Excel files
            device_repo: Repository for device lookups
        """
        self.parser = excel_parser
        self.devices = device_repo

    async def execute(
        self,
        file_content: bytes,
        filename: Optional[str] = None,
    ) -> ProcessResult:
        """Execute the use case.

        Args:
            file_content: Raw bytes of the Excel file
            filename: Optional filename for error messages

        Returns:
            ProcessResult with assignments and any errors
        """
        logger.info(f"Processing Excel file: {filename or 'unknown'}")

        # 1. Parse Excel file
        try:
            rows = self.parser.parse(file_content)
        except ValueError as e:
            logger.error(f"Failed to parse Excel: {e}")
            return ProcessResult(
                success=False,
                errors=[
                    ValidationError(
                        row_number=0,
                        field="file",
                        message=str(e),
                    )
                ],
            )

        if not rows:
            return ProcessResult(
                success=False,
                errors=[
                    ValidationError(
                        row_number=0,
                        field="file",
                        message="No data rows found in Excel file",
                    )
                ],
            )

        # 2. Validate rows
        validation = self.parser.validate(rows)
        if not validation.is_valid:
            logger.warning(f"Validation failed: {len(validation.errors)} errors")
            return ProcessResult(
                success=False,
                errors=validation.errors,
                warnings=validation.warnings,
                total_rows=len(rows),
            )

        # 3. Batch lookup devices by serial number
        serials = [r.serial_number for r in rows]
        logger.info(f"Looking up {len(serials)} devices by serial number")

        found_devices = await self.devices.find_by_serials(serials)
        device_map = {d.serial_number.upper(): d for d in found_devices}

        logger.info(f"Found {len(found_devices)} of {len(serials)} devices in database")

        # 4. Build DeviceAssignment list
        assignments: list[DeviceAssignment] = []

        for row in rows:
            serial = row.serial_number.upper()
            existing = device_map.get(serial)

            if existing:
                # Device found in DB - copy data
                assignment = DeviceAssignment(
                    serial_number=existing.serial_number,
                    mac_address=row.mac_address or existing.mac_address,
                    row_number=row.row_number,
                    device_id=existing.device_id,
                    device_type=existing.device_type,
                    model=existing.model,
                    region=existing.region,
                    current_subscription_id=existing.current_subscription_id,
                    current_subscription_key=existing.current_subscription_key,
                    current_application_id=existing.current_application_id,
                    current_tags=existing.current_tags.copy() if existing.current_tags else None,
                )
            else:
                # Device not in DB - will need creation
                assignment = DeviceAssignment(
                    serial_number=row.serial_number,
                    mac_address=row.mac_address,
                    row_number=row.row_number,
                    # All other fields remain None
                )

            assignments.append(assignment)

        # 5. Calculate statistics
        devices_found = sum(1 for a in assignments if a.device_id is not None)
        devices_not_found = len(assignments) - devices_found

        status_counts = {s: 0 for s in AssignmentStatus}
        for a in assignments:
            status_counts[a.status] += 1

        result = ProcessResult(
            success=True,
            assignments=assignments,
            warnings=validation.warnings,
            total_rows=len(rows),
            devices_found=devices_found,
            devices_not_found=devices_not_found,
            fully_assigned=status_counts[AssignmentStatus.FULLY_ASSIGNED],
            partially_assigned=status_counts[AssignmentStatus.PARTIAL],
            unassigned=status_counts[AssignmentStatus.UNASSIGNED],
        )

        logger.info(
            f"Processed {result.total_rows} rows: "
            f"{result.devices_found} found, "
            f"{result.devices_not_found} not found, "
            f"{result.fully_assigned} fully assigned"
        )

        return result
