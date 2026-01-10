"""Infrastructure adapters for device assignment.

These adapters implement the port interfaces defined in the domain layer,
connecting the application to external systems like PostgreSQL, Excel files,
and the GreenLake API.
"""

from .excel_parser import OpenpyxlExcelParser
from .glp_device_manager import GLPDeviceManagerAdapter
from .postgres_device_repo import PostgresDeviceRepository
from .postgres_subscription_repo import PostgresSubscriptionRepository
from .report_generator import SimpleReportGenerator
from .sync_service import DeviceSyncerAdapter

__all__ = [
    "PostgresDeviceRepository",
    "PostgresSubscriptionRepository",
    "GLPDeviceManagerAdapter",
    "OpenpyxlExcelParser",
    "DeviceSyncerAdapter",
    "SimpleReportGenerator",
]
