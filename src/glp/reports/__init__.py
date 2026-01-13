"""Reports module for comprehensive CSV/Excel report generation.

This module provides a unified report generation framework for:
- Dashboard executive reports
- Device inventory exports
- Subscription reports
- Client network reports
- Assignment workflow reports

Features:
- Beautiful multi-sheet Excel workbooks with HPE branding
- CSV exports for large datasets
- Excel formula injection protection
- Thread-safe async generation
"""

from .generator import BaseReportGenerator
from .styles import ExcelStyles

__all__ = ["BaseReportGenerator", "ExcelStyles"]
