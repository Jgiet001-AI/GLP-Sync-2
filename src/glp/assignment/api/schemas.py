"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WorkflowActionDTO(str, Enum):
    """Available workflow actions for devices."""

    ASSIGN = "assign"
    ARCHIVE = "archive"
    UNARCHIVE = "unarchive"
    REMOVE = "remove"


class DeviceAssignmentDTO(BaseModel):
    """Device assignment data transfer object."""

    serial_number: str
    mac_address: Optional[str] = None
    row_number: int = 0

    # From database lookup
    device_id: Optional[UUID] = None
    device_type: Optional[str] = None
    model: Optional[str] = None
    model_series: Optional[str] = None  # Extracted series (e.g., "6200" from "6200F-24G")
    region: Optional[str] = None
    status: str = "not_in_db"

    # Current assignments
    current_subscription_id: Optional[UUID] = None
    current_subscription_key: Optional[str] = None
    current_application_id: Optional[UUID] = None
    current_tags: dict[str, str] = Field(default_factory=dict)

    # User selections
    selected_subscription_id: Optional[UUID] = None
    selected_application_id: Optional[UUID] = None
    selected_tags: dict[str, str] = Field(default_factory=dict)

    # User choices for keeping existing values
    keep_current_subscription: bool = False
    keep_current_application: bool = False
    keep_current_tags: bool = False

    # Computed flags
    needs_creation: bool = False
    needs_subscription_patch: bool = False
    needs_application_patch: bool = False
    needs_tag_patch: bool = False

    class Config:
        from_attributes = True


class ValidationErrorDTO(BaseModel):
    """Validation error for an Excel row."""

    row_number: int
    field: str
    message: str


class ProcessResponse(BaseModel):
    """Response from processing an Excel file."""

    success: bool
    devices: list[DeviceAssignmentDTO] = Field(default_factory=list)
    errors: list[ValidationErrorDTO] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Statistics
    total_rows: int = 0
    devices_found: int = 0
    devices_not_found: int = 0
    fully_assigned: int = 0
    partially_assigned: int = 0
    unassigned: int = 0


class SubscriptionDTO(BaseModel):
    """Subscription available for assignment."""

    id: UUID
    key: str
    subscription_type: str
    tier: str
    tier_description: Optional[str] = None
    model_series: Optional[str] = None  # Model series this subscription is for
    quantity: int = 0
    available_quantity: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    days_remaining: Optional[int] = None
    compatible_device_types: list[str] = Field(default_factory=list)


class RegionDTO(BaseModel):
    """Region available for assignment.

    Note: Internally, region maps to application_id.
    User sees the region name, but we store the application UUID.
    """

    application_id: UUID = Field(..., description="Application UUID (use this for API calls)")
    region: str = Field(..., description="Region code (e.g., 'us-west')")
    display_name: str = Field(..., description="Display name (e.g., 'US West')")


class TagDTO(BaseModel):
    """Tag key-value pair."""

    key: str
    value: str


class OptionsResponse(BaseModel):
    """Response with available options for assignment."""

    subscriptions: list[SubscriptionDTO]
    regions: list[RegionDTO]
    existing_tags: list[TagDTO] = Field(default_factory=list)


class DeviceSelectionDTO(BaseModel):
    """User's selection for a device."""

    serial_number: str
    device_id: Optional[UUID] = None
    device_type: Optional[str] = None
    mac_address: Optional[str] = None

    # Current assignments (from database) - needed to determine what needs patching
    current_subscription_id: Optional[UUID] = None
    current_application_id: Optional[UUID] = None
    current_tags: dict[str, str] = Field(default_factory=dict)

    # User selections
    selected_subscription_id: Optional[UUID] = None
    selected_application_id: Optional[UUID] = None
    selected_region: Optional[str] = None  # Region code (e.g., "us-west") - required with application_id
    selected_tags: dict[str, str] = Field(default_factory=dict)

    # User choices for keeping existing values
    keep_current_subscription: bool = False
    keep_current_application: bool = False
    keep_current_tags: bool = False


class ApplyRequest(BaseModel):
    """Request to apply assignments."""

    devices: list[DeviceSelectionDTO]
    wait_for_completion: bool = True


class OperationResultDTO(BaseModel):
    """Result of a single operation."""

    success: bool
    operation_type: str
    device_ids: list[UUID] = Field(default_factory=list)
    device_serials: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    operation_url: Optional[str] = None


class ApplyResponse(BaseModel):
    """Response from applying assignments."""

    success: bool
    operations: list[OperationResultDTO] = Field(default_factory=list)

    # Statistics
    devices_created: int = 0
    subscriptions_assigned: int = 0
    applications_assigned: int = 0
    tags_updated: int = 0
    errors: int = 0


class SyncRequest(BaseModel):
    """Request to sync with GreenLake."""

    sync_devices: bool = True
    sync_subscriptions: bool = True


class ReportSummaryDTO(BaseModel):
    """Report summary statistics."""

    total_operations: int
    successful_operations: int
    failed_operations: int


class ReportBreakdownDTO(BaseModel):
    """Report breakdown by operation type."""

    devices_created: int
    subscriptions_assigned: int
    applications_assigned: int
    tags_updated: int


class SyncResultDTO(BaseModel):
    """Sync result statistics."""

    success: bool
    devices_synced: int
    subscriptions_synced: int


class ReportResponse(BaseModel):
    """Response with the final report."""

    generated_at: datetime
    summary: ReportSummaryDTO
    breakdown: ReportBreakdownDTO
    sync: Optional[SyncResultDTO] = None
    operations: list[OperationResultDTO] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ============================================
# Device Action Schemas
# ============================================


class DeviceActionRequest(BaseModel):
    """Request to perform an action on devices."""

    action: WorkflowActionDTO = Field(
        ...,
        description="The action to perform (archive, unarchive, remove)",
    )
    device_ids: list[UUID] = Field(
        ...,
        description="List of device UUIDs to perform action on",
    )
    wait_for_completion: bool = Field(
        default=True,
        description="Whether to wait for async operations to complete",
    )
    sync_after: bool = Field(
        default=True,
        description="Whether to sync database after action",
    )


class DeviceActionResponse(BaseModel):
    """Response from performing an action on devices."""

    success: bool
    action: WorkflowActionDTO
    devices_processed: int = 0
    devices_succeeded: int = 0
    devices_failed: int = 0
    total_duration_seconds: float = 0.0
    failed_device_ids: list[UUID] = Field(default_factory=list)
    failed_device_serials: list[str] = Field(default_factory=list)
    operations: list[OperationResultDTO] = Field(default_factory=list)


class PhaseResultDTO(BaseModel):
    """Result of a workflow phase."""

    phase_name: str
    success: bool
    devices_processed: int = 0
    errors: int = 0
    duration_seconds: float = 0.0


class ApplyResultDTO(BaseModel):
    """Extended response from applying assignments with phase information."""

    success: bool
    operations: list[OperationResultDTO] = Field(default_factory=list)
    phases: list[PhaseResultDTO] = Field(default_factory=list)

    # Statistics
    devices_created: int = 0
    applications_assigned: int = 0
    subscriptions_assigned: int = 0
    tags_updated: int = 0
    errors: int = 0

    # Timing
    total_duration_seconds: float = 0.0

    # New devices tracking
    new_devices_added: list[str] = Field(default_factory=list)
    new_devices_failed: list[str] = Field(default_factory=list)


# ============================================
# Add Devices to GreenLake Schemas
# ============================================


class AddDeviceDTO(BaseModel):
    """Device to add to GreenLake."""

    serial_number: str = Field(..., description="Device serial number")
    mac_address: str = Field(..., description="MAC address (required for NETWORK devices)")
    device_type: str = Field(
        default="NETWORK",
        description="Device type (NETWORK, COMPUTE, STORAGE)",
    )
    part_number: Optional[str] = Field(
        None,
        description="Part number (required for COMPUTE/STORAGE devices)",
    )
    tags: dict[str, str] = Field(default_factory=dict)


class AddDevicesRequest(BaseModel):
    """Request to add devices to GreenLake."""

    devices: list[AddDeviceDTO] = Field(
        ...,
        description="List of devices to add to GreenLake",
    )
    wait_for_completion: bool = Field(
        default=True,
        description="Whether to wait for async operations to complete",
    )


class AddDeviceResultDTO(BaseModel):
    """Result of adding a single device."""

    serial_number: str
    success: bool
    device_id: Optional[str] = None
    error: Optional[str] = None
    operation_url: Optional[str] = None


class AddDevicesResponse(BaseModel):
    """Response from adding devices to GreenLake."""

    success: bool
    devices_added: int = 0
    devices_failed: int = 0
    results: list[AddDeviceResultDTO] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
