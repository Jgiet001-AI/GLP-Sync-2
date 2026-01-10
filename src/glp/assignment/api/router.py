"""FastAPI router for device assignment endpoints."""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..domain.entities import DeviceAssignment
from ..domain.ports import (
    IDeviceManagerPort,
    IDeviceRepository,
    IExcelParser,
    IReportGenerator,
    ISubscriptionRepository,
    ISyncService,
)
from ..use_cases import (
    ApplyAssignmentsUseCase,
    GetOptionsUseCase,
    ProcessExcelUseCase,
    SyncAndReportUseCase,
)
from .dependencies import (
    get_device_manager,
    get_device_repo,
    get_excel_parser,
    get_report_generator,
    get_subscription_repo,
    get_sync_service,
)
from .schemas import (
    AddDeviceResultDTO,
    AddDevicesRequest,
    AddDevicesResponse,
    ApplyRequest,
    ApplyResponse,
    DeviceAssignmentDTO,
    OperationResultDTO,
    OptionsResponse,
    ProcessResponse,
    RegionDTO,
    ReportBreakdownDTO,
    ReportResponse,
    ReportSummaryDTO,
    SubscriptionDTO,
    SyncRequest,
    SyncResultDTO,
    TagDTO,
    ValidationErrorDTO,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assignment", tags=["Device Assignment"])


@router.post("/upload", response_model=ProcessResponse)
async def upload_excel(
    file: UploadFile = File(...),
    excel_parser: IExcelParser = Depends(get_excel_parser),
    device_repo: IDeviceRepository = Depends(get_device_repo),
):
    """Upload an Excel file with device serial numbers and MAC addresses.

    The Excel file should have columns:
    - Serial Number (required)
    - MAC Address (optional)

    Returns parsed devices with their current assignment status.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not file.filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(
            status_code=400,
            detail="File must be an Excel (.xlsx, .xls) or CSV (.csv) file",
        )

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Process the Excel file
    use_case = ProcessExcelUseCase(
        excel_parser=excel_parser,
        device_repo=device_repo,
    )

    result = await use_case.execute(content, filename=file.filename)

    # Convert to response DTOs
    devices = [
        DeviceAssignmentDTO(
            serial_number=d.serial_number,
            mac_address=d.mac_address,
            row_number=d.row_number,
            device_id=d.device_id,
            device_type=d.device_type,
            model=d.model,
            region=d.region,
            status=d.status.value,
            current_subscription_id=d.current_subscription_id,
            current_subscription_key=d.current_subscription_key,
            current_application_id=d.current_application_id,
            current_tags=d.current_tags or {},
            needs_creation=d.needs_creation,
            needs_subscription_patch=d.needs_subscription_patch,
            needs_application_patch=d.needs_application_patch,
            needs_tag_patch=d.needs_tag_patch,
        )
        for d in result.assignments
    ]

    errors = [
        ValidationErrorDTO(
            row_number=e.row_number,
            field=e.field,
            message=e.message,
        )
        for e in result.errors
    ]

    return ProcessResponse(
        success=result.success,
        devices=devices,
        errors=errors,
        warnings=result.warnings,
        total_rows=result.total_rows,
        devices_found=result.devices_found,
        devices_not_found=result.devices_not_found,
        fully_assigned=result.fully_assigned,
        partially_assigned=result.partially_assigned,
        unassigned=result.unassigned,
    )


@router.get("/options", response_model=OptionsResponse)
async def get_options(
    device_type: Annotated[
        Optional[str],
        Query(description="Filter subscriptions by device type (NETWORK, COMPUTE, STORAGE)"),
    ] = None,
    subscription_repo: ISubscriptionRepository = Depends(get_subscription_repo),
    device_repo: IDeviceRepository = Depends(get_device_repo),
):
    """Get available options for device assignment.

    Returns:
    - Subscriptions: Available subscription licenses (filtered by device type if specified)
    - Regions: Available regions (mapped to application IDs)
    - Existing Tags: Tags already used in the system (for autocomplete)
    """
    use_case = GetOptionsUseCase(
        subscription_repo=subscription_repo,
        device_repo=device_repo,
    )

    result = await use_case.execute(device_type=device_type)

    # Convert to response DTOs
    subscriptions = [
        SubscriptionDTO(
            id=s.id,
            key=s.key,
            subscription_type=s.subscription_type,
            tier=s.tier,
            tier_description=s.tier_description,
            quantity=s.quantity,
            available_quantity=s.available_quantity,
            start_time=s.start_time,
            end_time=s.end_time,
            days_remaining=s.days_remaining,
            compatible_device_types=s.compatible_device_types,
        )
        for s in result.subscriptions
    ]

    regions = [
        RegionDTO(
            application_id=r.application_id,
            region=r.region,
            display_name=r.display_name,
        )
        for r in result.regions
    ]

    existing_tags = [TagDTO(key=k, value=v) for k, v in result.existing_tags]

    return OptionsResponse(
        subscriptions=subscriptions,
        regions=regions,
        existing_tags=existing_tags,
    )


@router.post("/apply", response_model=ApplyResponse)
async def apply_assignments(
    request: ApplyRequest,
    device_manager: IDeviceManagerPort = Depends(get_device_manager),
):
    """Apply selected assignments to devices.

    This endpoint:
    1. Creates new devices (POST) if they don't exist in GreenLake
    2. Assigns subscriptions (PATCH) to devices missing them
    3. Assigns applications/regions (PATCH) to devices missing them
    4. Updates tags (PATCH) on devices

    Only patches what's actually needed - devices with existing
    assignments are skipped for that operation type.
    """
    # Log what we received for debugging
    sample_devices = request.devices[:3] if request.devices else []
    logger.info(f"=== APPLY REQUEST: {len(request.devices)} devices ===")
    for d in sample_devices:
        logger.info(
            f"Device {d.serial_number}: "
            f"device_id={d.device_id}, "
            f"current_app={d.current_application_id}, "
            f"selected_app={d.selected_application_id}, "
            f"current_sub={d.current_subscription_id}, "
            f"selected_sub={d.selected_subscription_id}, "
            f"current_tags={d.current_tags}, "
            f"selected_tags={d.selected_tags}"
        )

    use_case = ApplyAssignmentsUseCase(device_manager=device_manager)

    # Convert request DTOs to domain entities
    assignments = [
        DeviceAssignment(
            serial_number=d.serial_number,
            mac_address=d.mac_address,
            device_id=d.device_id,
            device_type=d.device_type,
            # Current assignments from database (for gap detection)
            current_subscription_id=d.current_subscription_id,
            current_application_id=d.current_application_id,
            current_tags=d.current_tags or {},
            # User selections
            selected_subscription_id=d.selected_subscription_id,
            selected_application_id=d.selected_application_id,
            selected_region=d.selected_region,  # Region code needed for application assignment
            selected_tags=d.selected_tags,
            # Keep flags
            keep_current_subscription=d.keep_current_subscription,
            keep_current_application=d.keep_current_application,
            keep_current_tags=d.keep_current_tags,
        )
        for d in request.devices
    ]

    result = await use_case.execute(
        assignments=assignments,
        wait_for_completion=request.wait_for_completion,
    )

    # Convert to response DTOs
    operations = [
        OperationResultDTO(
            success=op.success,
            operation_type=op.operation_type,
            device_ids=op.device_ids,
            device_serials=op.device_serials,
            error=op.error,
            operation_url=op.operation_url,
        )
        for op in result.operations
    ]

    return ApplyResponse(
        success=result.success,
        operations=operations,
        devices_created=result.devices_created,
        subscriptions_assigned=result.subscriptions_assigned,
        applications_assigned=result.applications_assigned,
        tags_updated=result.tags_updated,
        errors=result.errors,
    )


@router.post("/sync", response_model=ReportResponse)
async def sync_and_report(
    request: SyncRequest,
    sync_service: ISyncService = Depends(get_sync_service),
    report_generator: IReportGenerator = Depends(get_report_generator),
):
    """Trigger a resync with GreenLake and generate a report.

    This endpoint:
    1. Syncs devices from GreenLake to the local database
    2. Syncs subscriptions from GreenLake to the local database
    3. Generates a summary report

    Use this after applying assignments to verify the changes
    are reflected in the system.
    """
    use_case = SyncAndReportUseCase(
        sync_service=sync_service,
        report_generator=report_generator,
    )

    # We don't have operations to report on from this endpoint
    # This is just for triggering a sync
    result = await use_case.execute(operations=[], sync_after=True)

    return ReportResponse(
        generated_at=result.generated_at,
        summary=ReportSummaryDTO(
            total_operations=result.total_operations,
            successful_operations=result.successful_operations,
            failed_operations=result.failed_operations,
        ),
        breakdown=ReportBreakdownDTO(
            devices_created=result.devices_created,
            subscriptions_assigned=result.subscriptions_assigned,
            applications_assigned=result.applications_assigned,
            tags_updated=result.tags_updated,
        ),
        sync=SyncResultDTO(
            success=result.sync_success,
            devices_synced=result.devices_synced,
            subscriptions_synced=result.subscriptions_synced,
        ),
        operations=[],
        errors=result.errors,
    )


@router.get("/report/download")
async def download_report(
    report_generator: IReportGenerator = Depends(get_report_generator),
):
    """Download the latest report as an Excel file.

    Returns an Excel file with:
    - Summary sheet with statistics
    - Operations sheet with all operations
    - Errors sheet (if any errors occurred)
    """
    # Generate an empty report for download template
    # In a real implementation, we'd store and retrieve the last report
    excel_bytes = report_generator.generate_excel(operations=[])

    return StreamingResponse(
        iter([excel_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=assignment_report.xlsx"
        },
    )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "device-assignment"}


@router.post("/devices/add", response_model=AddDevicesResponse)
async def add_devices_to_greenlake(
    request: AddDevicesRequest,
    device_manager: IDeviceManagerPort = Depends(get_device_manager),
):
    """Add new devices to GreenLake.

    Use this endpoint to register devices that exist in your Excel upload
    but are not yet in the GreenLake platform. Once added, you can then
    assign subscriptions and applications to them.

    Requirements:
    - NETWORK devices require mac_address
    - COMPUTE/STORAGE devices require part_number
    """
    results: list[AddDeviceResultDTO] = []
    devices_added = 0
    devices_failed = 0
    errors: list[str] = []

    for device in request.devices:
        try:
            # Call the device manager to add the device
            result = await device_manager.add_device(
                serial=device.serial_number,
                device_type=device.device_type,
                mac_address=device.mac_address,
                part_number=device.part_number,
                tags=device.tags if device.tags else None,
            )

            if result.success:
                devices_added += 1
                results.append(
                    AddDeviceResultDTO(
                        serial_number=device.serial_number,
                        success=True,
                        operation_url=result.operation_url,
                    )
                )
                logger.info(f"Added device {device.serial_number} to GreenLake")
            else:
                devices_failed += 1
                error_msg = result.error or "Unknown error"
                errors.append(f"{device.serial_number}: {error_msg}")
                results.append(
                    AddDeviceResultDTO(
                        serial_number=device.serial_number,
                        success=False,
                        error=error_msg,
                    )
                )
                logger.error(f"Failed to add device {device.serial_number}: {error_msg}")

        except Exception as e:
            devices_failed += 1
            error_msg = str(e)
            errors.append(f"{device.serial_number}: {error_msg}")
            results.append(
                AddDeviceResultDTO(
                    serial_number=device.serial_number,
                    success=False,
                    error=error_msg,
                )
            )
            logger.exception(f"Exception adding device {device.serial_number}")

    return AddDevicesResponse(
        success=devices_failed == 0,
        devices_added=devices_added,
        devices_failed=devices_failed,
        results=results,
        errors=errors,
    )
