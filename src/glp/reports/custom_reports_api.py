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
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from ..assignment.api.dependencies import get_db_pool, verify_api_key
from .query_builder import get_available_tables
from .schemas import (
    CreateReportRequest,
    FieldsResponse,
    ReportListResponse,
    ReportResponse,
    UpdateReportRequest,
)

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


@router.get("/custom", response_model=ReportListResponse)
async def list_reports(
    pool: asyncpg.Pool = Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """List all saved custom reports.

    Returns a summary list of all custom report templates. This endpoint
    does not include the full report configuration - use GET /custom/{id}
    to retrieve the complete report details.

    Args:
        pool: Database connection pool
        _auth: API key authentication

    Returns:
        ReportListResponse: List of report summaries with pagination metadata

    Raises:
        HTTPException: 500 if database error occurs
    """
    try:
        async with pool.acquire() as conn:
            # Get all reports ordered by most recently updated
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    name,
                    description,
                    created_by,
                    is_shared,
                    created_at,
                    updated_at,
                    last_executed_at,
                    execution_count
                FROM custom_reports
                ORDER BY updated_at DESC
                """
            )

            # Convert rows to response items
            reports = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "created_by": row["created_by"],
                    "is_shared": row["is_shared"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "last_executed_at": row["last_executed_at"],
                    "execution_count": row["execution_count"],
                }
                for row in rows
            ]

            return ReportListResponse(
                reports=reports,
                total=len(reports),
                page=1,
                page_size=len(reports),
            )

    except Exception as e:
        logger.error(f"Error listing reports: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list reports: {str(e)}",
        )


@router.get("/custom/{id}", response_model=ReportResponse)
async def get_report(
    id: str,
    pool: asyncpg.Pool = Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get a single custom report by ID.

    Retrieves the complete report configuration including all fields,
    filters, grouping, and sorting settings.

    Args:
        id: Report ID (UUID)
        pool: Database connection pool
        _auth: API key authentication

    Returns:
        ReportResponse: Complete report details including configuration

    Raises:
        HTTPException: 404 if report not found, 500 if database error occurs
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
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
                FROM custom_reports
                WHERE id = $1
                """,
                id,
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with id '{id}' not found",
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
        logger.error(f"Error getting report {id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get report: {str(e)}",
        )


@router.put("/custom/{id}", response_model=ReportResponse)
async def update_report(
    id: str,
    request: UpdateReportRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Update an existing custom report.

    This endpoint allows partial updates - only provided fields will be updated.
    The updated_at timestamp is automatically set to the current time.

    Args:
        id: Report ID (UUID)
        request: Update request with optional fields to modify
        pool: Database connection pool
        _auth: API key authentication

    Returns:
        ReportResponse: Updated report with all current values

    Raises:
        HTTPException: 404 if report not found, 400 if validation fails,
                      500 if database error occurs
    """
    try:
        async with pool.acquire() as conn:
            # First check if the report exists
            existing = await conn.fetchrow(
                "SELECT id FROM custom_reports WHERE id = $1",
                id,
            )

            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Report with id '{id}' not found",
                )

            # Build dynamic UPDATE query for only provided fields
            update_fields = []
            params = []
            param_idx = 1

            if request.name is not None:
                update_fields.append(f"name = ${param_idx}")
                params.append(request.name)
                param_idx += 1

            if request.description is not None:
                update_fields.append(f"description = ${param_idx}")
                params.append(request.description)
                param_idx += 1

            if request.config is not None:
                update_fields.append(f"config = ${param_idx}")
                params.append(json.dumps(request.config.model_dump()))
                param_idx += 1

            if request.is_shared is not None:
                update_fields.append(f"is_shared = ${param_idx}")
                params.append(request.is_shared)
                param_idx += 1

            if request.shared_with is not None:
                update_fields.append(f"shared_with = ${param_idx}")
                params.append(json.dumps(request.shared_with))
                param_idx += 1

            # Always update the updated_at timestamp
            update_fields.append(f"updated_at = ${param_idx}")
            params.append(datetime.now())
            param_idx += 1

            # Add the report ID as the final parameter
            params.append(id)

            # Execute the update and return the updated record
            query = f"""
                UPDATE custom_reports
                SET {', '.join(update_fields)}
                WHERE id = ${param_idx}
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
            """

            row = await conn.fetchrow(query, *params)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update report",
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
        logger.error(f"Error updating report {id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update report: {str(e)}",
        )
