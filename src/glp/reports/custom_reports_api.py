"""Custom report builder API endpoints.

This module provides REST endpoints for creating, managing, and executing
custom reports with a drag-and-drop report builder interface.

Security:
- All endpoints require API key authentication
- Field names validated against whitelist to prevent SQL injection
- Parameterized queries for all user inputs
"""

import logging

from fastapi import APIRouter, Depends

from ..assignment.api.dependencies import verify_api_key
from .query_builder import get_available_tables
from .schemas import FieldsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["custom-reports"])


@router.get("/fields", response_model=FieldsResponse)
async def get_fields(
    _auth: bool = Depends(verify_api_key),
):
    """Get available fields for report building.

    Returns metadata for all available tables and their fields, including:
    - Field names and display names
    - Data types
    - Available filter operators
    - Whether fields are filterable, groupable, sortable

    This endpoint is used by the report builder UI to populate the field
    selector and filter builder.

    Returns:
        FieldsResponse: Tables with their field metadata
    """
    try:
        tables = get_available_tables()
        return FieldsResponse(tables=tables)
    except Exception as e:
        logger.error(f"Error getting available fields: {e}", exc_info=True)
        raise
