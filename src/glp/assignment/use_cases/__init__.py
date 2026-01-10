"""Use cases for device assignment.

Each use case represents a single user action and orchestrates
domain logic without knowing about infrastructure details.
"""

from .apply_assignments import ApplyAssignmentsUseCase, ApplyResult, PhaseResult
from .device_actions import ActionResult, DeviceActionsUseCase
from .get_options import GetOptionsUseCase
from .process_excel import ProcessExcelUseCase
from .sync_and_report import SyncAndReportUseCase

__all__ = [
    "ProcessExcelUseCase",
    "GetOptionsUseCase",
    "ApplyAssignmentsUseCase",
    "ApplyResult",
    "PhaseResult",
    "DeviceActionsUseCase",
    "ActionResult",
    "SyncAndReportUseCase",
]
