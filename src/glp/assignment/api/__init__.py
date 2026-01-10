"""API layer for device assignment.

Contains:
- FastAPI router with endpoints
- Pydantic schemas for request/response validation
"""

from .router import router
from .schemas import (
    ApplyRequest,
    ApplyResponse,
    DeviceAssignmentDTO,
    OptionsResponse,
    ProcessResponse,
    RegionDTO,
    ReportResponse,
    SubscriptionDTO,
    SyncRequest,
)

__all__ = [
    "router",
    "DeviceAssignmentDTO",
    "SubscriptionDTO",
    "RegionDTO",
    "ProcessResponse",
    "OptionsResponse",
    "ApplyRequest",
    "ApplyResponse",
    "SyncRequest",
    "ReportResponse",
]
