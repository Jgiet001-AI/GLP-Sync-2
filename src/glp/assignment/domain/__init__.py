"""Domain layer for device assignment.

Contains:
- Entities: Core business objects
- Ports: Interface definitions for infrastructure adapters
"""

from .entities import (
    AssignmentGap,
    DeviceAssignment,
    ExcelRow,
    OperationResult,
    ProcessResult,
    RegionMapping,
    SubscriptionOption,
    ValidationResult,
)
from .entities import (
    ValidationError as DomainValidationError,
)
from .ports import (
    IDeviceManagerPort,
    IDeviceRepository,
    IExcelParser,
    IReportGenerator,
    ISubscriptionRepository,
    ISyncService,
)

__all__ = [
    # Entities
    "DeviceAssignment",
    "AssignmentGap",
    "RegionMapping",
    "SubscriptionOption",
    "ExcelRow",
    "ValidationResult",
    "DomainValidationError",
    "ProcessResult",
    "OperationResult",
    # Ports
    "IDeviceRepository",
    "ISubscriptionRepository",
    "IDeviceManagerPort",
    "IExcelParser",
    "ISyncService",
    "IReportGenerator",
]
