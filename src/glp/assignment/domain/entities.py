"""Domain entities for device assignment.

These are pure domain objects with no infrastructure dependencies.
They represent the core business concepts of the assignment workflow.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class DeviceType(str, Enum):
    """Device types supported by the GreenLake API."""

    COMPUTE = "COMPUTE"
    NETWORK = "NETWORK"
    STORAGE = "STORAGE"


class AssignmentStatus(str, Enum):
    """Status of a device assignment."""

    NOT_IN_DB = "not_in_db"  # Device not found in database
    FULLY_ASSIGNED = "fully_assigned"  # Has subscription, application, and tags
    PARTIAL = "partial"  # Has some but not all assignments
    UNASSIGNED = "unassigned"  # In DB but no assignments


class WorkflowAction(str, Enum):
    """Available workflow actions for devices."""

    ASSIGN = "assign"  # Default: assign subscription, application, tags
    ARCHIVE = "archive"  # Archive devices
    UNARCHIVE = "unarchive"  # Unarchive devices
    REMOVE = "remove"  # Remove devices from GreenLake


@dataclass
class ExcelRow:
    """A single row from the uploaded Excel file."""

    row_number: int
    serial_number: str
    mac_address: Optional[str] = None

    def __post_init__(self):
        # Normalize serial number
        self.serial_number = self.serial_number.strip().upper()
        # Normalize MAC address if present
        if self.mac_address:
            self.mac_address = self.mac_address.strip().upper()


@dataclass
class ValidationError:
    """A validation error for an Excel row."""

    row_number: int
    field: str
    message: str


@dataclass
class ValidationResult:
    """Result of validating Excel rows."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DeviceAssignment:
    """Represents a device from Excel with its current and selected state.

    This is the main entity used throughout the assignment workflow.
    It tracks both what's currently assigned in the DB and what the
    user has selected for assignment.
    """

    # From Excel
    serial_number: str
    mac_address: Optional[str] = None
    row_number: int = 0

    # Looked up from DB
    device_id: Optional[UUID] = None
    device_type: Optional[str] = None  # NETWORK, COMPUTE, STORAGE
    model: Optional[str] = None
    region: Optional[str] = None

    # Current assignments (from DB)
    current_subscription_id: Optional[UUID] = None
    current_subscription_key: Optional[str] = None
    current_application_id: Optional[UUID] = None
    current_tags: dict[str, str] = field(default_factory=dict)

    # User-selected assignments
    selected_subscription_id: Optional[UUID] = None
    selected_application_id: Optional[UUID] = None
    selected_region: Optional[str] = None  # Region code (e.g., "us-west") - required with application_id
    selected_tags: dict[str, str] = field(default_factory=dict)

    # User choices for keeping existing values
    # If True, keep the current value instead of changing/assigning
    keep_current_subscription: bool = False
    keep_current_application: bool = False
    keep_current_tags: bool = False

    @property
    def status(self) -> AssignmentStatus:
        """Determine the assignment status of this device."""
        if self.device_id is None:
            return AssignmentStatus.NOT_IN_DB

        has_subscription = self.current_subscription_id is not None
        has_application = self.current_application_id is not None
        has_tags = bool(self.current_tags)  # Must have at least one tag

        if has_subscription and has_application and has_tags:
            return AssignmentStatus.FULLY_ASSIGNED
        elif has_subscription or has_application or has_tags:
            return AssignmentStatus.PARTIAL
        else:
            return AssignmentStatus.UNASSIGNED

    @property
    def needs_creation(self) -> bool:
        """Check if device needs to be created via POST."""
        return self.device_id is None

    @property
    def needs_subscription_patch(self) -> bool:
        """Check if subscription needs to be patched.

        Returns False if:
        - Device doesn't exist
        - User chose to keep current subscription
        - Device already has a subscription
        - No new subscription was selected
        """
        if self.device_id is None:
            return False
        if self.keep_current_subscription:
            return False
        if self.current_subscription_id is not None:
            return False
        if self.selected_subscription_id is None:
            return False
        return True

    @property
    def needs_application_patch(self) -> bool:
        """Check if application needs to be patched.

        Returns False if:
        - Device doesn't exist
        - User chose to keep current application
        - Device already has an application
        - No new application was selected
        """
        if self.device_id is None:
            return False
        if self.keep_current_application:
            return False
        if self.current_application_id is not None:
            return False
        if self.selected_application_id is None:
            return False
        return True

    @property
    def needs_tag_patch(self) -> bool:
        """Check if tags need to be patched.

        Returns False if:
        - Device doesn't exist
        - User chose to keep current tags
        - No new tags were selected
        - Selected tags are same as current
        """
        if self.device_id is None:
            return False
        if self.keep_current_tags:
            return False
        if not self.selected_tags:
            return False
        return self.selected_tags != self.current_tags

    @property
    def model_series(self) -> Optional[str]:
        """Extract the model series from the device model.

        Examples:
            "6200F-24G-4SFP+" -> "6200"
            "6300M-48G-CL6-4SFP56" -> "6300"
            "AP-565-US" -> "565"
            "AP-635-US" -> "635"
        """
        if not self.model:
            return None
        return extract_model_series(self.model)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "serial_number": self.serial_number,
            "mac_address": self.mac_address,
            "row_number": self.row_number,
            "device_id": str(self.device_id) if self.device_id else None,
            "device_type": self.device_type,
            "model": self.model,
            "model_series": self.model_series,
            "region": self.region,
            "status": self.status.value,
            "current_subscription_id": str(self.current_subscription_id)
            if self.current_subscription_id
            else None,
            "current_subscription_key": self.current_subscription_key,
            "current_application_id": str(self.current_application_id)
            if self.current_application_id
            else None,
            "current_tags": self.current_tags,
            "selected_subscription_id": str(self.selected_subscription_id)
            if self.selected_subscription_id
            else None,
            "selected_application_id": str(self.selected_application_id)
            if self.selected_application_id
            else None,
            "selected_tags": self.selected_tags,
            "keep_current_subscription": self.keep_current_subscription,
            "keep_current_application": self.keep_current_application,
            "keep_current_tags": self.keep_current_tags,
            "needs_creation": self.needs_creation,
            "needs_subscription_patch": self.needs_subscription_patch,
            "needs_application_patch": self.needs_application_patch,
            "needs_tag_patch": self.needs_tag_patch,
        }


def extract_model_series(model: str) -> Optional[str]:
    """Extract the model series from a device model string.

    This extracts the numeric series identifier that determines
    subscription compatibility.

    Examples:
        "6200F-24G-4SFP+" -> "6200"
        "6300M-48G-CL6-4SFP56" -> "6300"
        "6400-48G-4SFP+" -> "6400"
        "AP-565-US" -> "565"
        "AP-635-RW" -> "635"
        "Aruba 6200F" -> "6200"

    Args:
        model: Device model string

    Returns:
        Model series string or None if not found
    """
    if not model:
        return None

    # Normalize: uppercase and replace common separators
    model = model.upper().strip()

    # Pattern 1: Switch models like "6200F-24G-4SFP+", "6300M-48G"
    # Look for 4-digit number at the start
    switch_match = re.match(r"^(\d{4})[A-Z]?[-\s]", model)
    if switch_match:
        return switch_match.group(1)

    # Pattern 2: AP models like "AP-565-US", "AP-635-RW"
    ap_match = re.search(r"AP[-\s]?(\d{3,4})", model)
    if ap_match:
        return ap_match.group(1)

    # Pattern 3: Models with series in the name "Aruba 6200F"
    aruba_match = re.search(r"ARUBA\s+(\d{4})", model)
    if aruba_match:
        return aruba_match.group(1)

    # Pattern 4: Just extract the first significant number (3-4 digits)
    number_match = re.search(r"\b(\d{3,4})\b", model)
    if number_match:
        return number_match.group(1)

    return None


@dataclass
class AssignmentGap:
    """What needs to be assigned for a device.

    Used to plan the operations that need to be performed.
    """

    device_id: Optional[UUID]
    serial_number: str
    mac_address: Optional[str] = None
    device_type: Optional[str] = None

    needs_creation: bool = False
    needs_subscription: bool = False
    needs_application: bool = False
    needs_tags: bool = False

    # What to assign
    subscription_id: Optional[UUID] = None
    application_id: Optional[UUID] = None
    tags_to_add: dict[str, str] = field(default_factory=dict)
    tags_to_remove: list[str] = field(default_factory=list)


@dataclass
class RegionMapping:
    """Maps application UUID to region name.

    In GreenLake, region is tied to application. The user sees
    the region name (e.g., "US West") but we store the application UUID.
    """

    application_id: UUID
    region: str  # e.g., "us-west", "eu-central"
    display_name: str  # e.g., "US West", "EU Central"


@dataclass
class SubscriptionOption:
    """A subscription available for assignment."""

    id: UUID
    key: str
    subscription_type: str  # CENTRAL_AP, CENTRAL_SWITCH, etc.
    tier: str
    tier_description: Optional[str] = None
    quantity: int = 0
    available_quantity: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def compatible_device_types(self) -> list[str]:
        """Determine which device types can use this subscription."""
        type_map = {
            "CENTRAL_AP": ["NETWORK"],
            "CENTRAL_SWITCH": ["NETWORK"],
            "CENTRAL_GW": ["NETWORK"],
            "CENTRAL_BRIDGE": ["NETWORK"],
            "CENTRAL_COMPUTE": ["COMPUTE"],
            "CENTRAL_STORAGE": ["STORAGE"],
        }
        return type_map.get(self.subscription_type, ["NETWORK", "COMPUTE", "STORAGE"])

    @property
    def model_series(self) -> Optional[str]:
        """Extract the model series this subscription is for.

        The tier often contains the model series, e.g.:
        - FOUNDATION_SWITCH_6200 -> "6200"
        - FOUNDATION_AP -> None (compatible with all APs)
        - ADVANCED_SWITCH_6300 -> "6300"
        """
        if not self.tier:
            return None
        return extract_tier_model_series(self.tier)

    def is_compatible_with(self, device_type: str) -> bool:
        """Check if this subscription is compatible with a device type."""
        return device_type in self.compatible_device_types

    def is_compatible_with_model(self, model: str) -> bool:
        """Check if this subscription is compatible with a device model.

        Args:
            model: Device model string (e.g., "6200F-24G-4SFP+")

        Returns:
            True if compatible, False otherwise
        """
        sub_series = self.model_series
        device_series = extract_model_series(model)

        # If subscription doesn't specify a series, it's compatible with all
        if sub_series is None:
            return True

        # If device doesn't have a series, can't match
        if device_series is None:
            return True  # Be permissive when we can't determine

        # Compare series
        return sub_series == device_series

    @property
    def days_remaining(self) -> Optional[int]:
        """Calculate days remaining until expiration."""
        if self.end_time is None:
            return None
        delta = self.end_time - datetime.now(self.end_time.tzinfo)
        return max(0, delta.days)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "key": self.key,
            "subscription_type": self.subscription_type,
            "tier": self.tier,
            "tier_description": self.tier_description,
            "model_series": self.model_series,
            "quantity": self.quantity,
            "available_quantity": self.available_quantity,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "days_remaining": self.days_remaining,
            "compatible_device_types": self.compatible_device_types,
        }


def extract_tier_model_series(tier: str) -> Optional[str]:
    """Extract the model series from a subscription tier.

    Examples:
        "FOUNDATION_SWITCH_6200" -> "6200"
        "ADVANCED_SWITCH_6300" -> "6300"
        "FOUNDATION_AP" -> None (no specific model)
        "FOUNDATION_AP_565" -> "565"

    Args:
        tier: Subscription tier string

    Returns:
        Model series string or None if not specified
    """
    if not tier:
        return None

    tier = tier.upper()

    # Look for a 3-4 digit number at the end
    match = re.search(r"_(\d{3,4})$", tier)
    if match:
        return match.group(1)

    # Look for a 3-4 digit number anywhere
    match = re.search(r"(\d{3,4})", tier)
    if match:
        return match.group(1)

    return None


@dataclass
class ProcessResult:
    """Result of processing an Excel file."""

    success: bool
    assignments: list[DeviceAssignment] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Statistics
    total_rows: int = 0
    devices_found: int = 0
    devices_not_found: int = 0
    fully_assigned: int = 0
    partially_assigned: int = 0
    unassigned: int = 0


@dataclass
class OperationResult:
    """Result of an assignment operation."""

    success: bool
    operation_type: str  # "create", "subscription", "application", "tags", "archive", "unarchive", "remove"
    device_ids: list[UUID] = field(default_factory=list)
    device_serials: list[str] = field(default_factory=list)
    error: Optional[str] = None
    operation_url: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "success": self.success,
            "operation_type": self.operation_type,
            "device_ids": [str(d) for d in self.device_ids],
            "device_serials": self.device_serials,
            "error": self.error,
            "operation_url": self.operation_url,
        }
