"""Custom report builder API endpoints.

This module provides REST endpoints for creating, managing, and executing
custom reports with a drag-and-drop report builder interface.

Security:
- All endpoints require API key authentication
- Field names validated against whitelist to prevent SQL injection
- Parameterized queries for all user inputs
"""

import json
import logging

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from ..assignment.api.dependencies import get_db_pool, verify_api_key
from .query_builder import get_available_tables
from .schemas import CreateReportRequest, FieldsResponse, ReportResponse

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


@router.post("/custom", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    request: CreateReportRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Create a new custom report template.

    This endpoint saves a report configuration that can be reused. The report
    can include:
    - Selected fields from devices and subscriptions tables
    - Filters with AND/OR logic
    - Grouping with aggregation functions
    - Sorting configuration

    Args:
        request: Report creation request with name, description, and config
        pool: Database connection pool
        _auth: API key authentication

    Returns:
        ReportResponse: Created report with generated ID and timestamps

    Raises:
        HTTPException: 400 if validation fails, 500 if database error occurs
    """
    try:
        # Use "api-user" as default creator since we don't have user auth yet
        created_by = "api-user"

        # Convert config to JSON for storage
        config_json = request.config.model_dump()

        async with pool.acquire() as conn:
            # Insert the new report and return the created record
            row = await conn.fetchrow(
                """
                INSERT INTO custom_reports (
                    name,
                    description,
                    created_by,
                    config,
                    is_shared,
                    shared_with
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING
                    id,
                    name,
                    description,
                    created_by,
                    config,
                    is_shared,
                    shared_with,
                    created_at,
                    updated_at,
                    last_executed_at,
                    execution_count
                """,
                request.name,
                request.description,
                created_by,
                json.dumps(config_json),
                request.is_shared,
                json.dumps(request.shared_with),
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create report",
            )

        # Convert database row to response model
        return ReportResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_by=row["created_by"],
            config=json.loads(row["config"]) if isinstance(row["config"], str) else row["config"],
            is_shared=row["is_shared"],
            shared_with=json.loads(row["shared_with"]) if isinstance(row["shared_with"], str) else row["shared_with"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_executed_at=row["last_executed_at"],
            execution_count=row["execution_count"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create report: {str(e)}",
        )
