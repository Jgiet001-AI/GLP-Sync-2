"""Custom report builder API endpoints.

This module provides REST endpoints for creating, managing, and executing
custom reports with a drag-and-drop report builder interface.

Security:
- All endpoints require API key authentication
- Field names validated against whitelist to prevent SQL injection
- Parameterized queries for all user inputs
"""

import io
import json
import logging
import time
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..assignment.api.dependencies import get_db_pool, verify_api_key
from .query_builder import QueryBuilder, QueryBuilderError, get_available_tables
from .schemas import (
    CreateReportRequest,
    ExecuteReportResponse,
    ExportFormat,
    FieldsResponse,
    ReportConfig,
    ReportListResponse,
    ReportResponse,
    UpdateReportRequest,
)
from .security import SecurityValidationError, validate_report_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports/custom", tags=["custom-reports"])


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


@router.post("/", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
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
        config_json_str = json.dumps(config_json)

        # Security validation: check config size and complexity
        try:
            validate_report_config(request.config, config_json_str)
        except SecurityValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security validation failed: {str(e)}",
            )

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
                config_json_str,
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


@router.get("/", response_model=ReportListResponse)
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


@router.get("/{id}", response_model=ReportResponse)
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


@router.put("/{id}", response_model=ReportResponse)
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
                # Security validation for updated config
                config_json_str = json.dumps(request.config.model_dump())
                try:
                    validate_report_config(request.config, config_json_str)
                except SecurityValidationError as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Security validation failed: {str(e)}",
                    )

                update_fields.append(f"config = ${param_idx}")
                params.append(config_json_str)
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


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    id: str,
    pool: asyncpg.Pool = Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Delete a custom report by ID.

    This endpoint permanently deletes a report template. The operation
    cannot be undone.

    Args:
        id: Report ID (UUID)
        pool: Database connection pool
        _auth: API key authentication

    Returns:
        None (204 No Content on success)

    Raises:
        HTTPException: 404 if report not found, 500 if database error occurs
    """
    try:
        async with pool.acquire() as conn:
            # Delete the report and check if it existed
            result = await conn.execute(
                "DELETE FROM custom_reports WHERE id = $1",
                id,
            )

        # PostgreSQL returns "DELETE n" where n is the number of rows deleted
        rows_deleted = int(result.split()[-1]) if result else 0

        if rows_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with id '{id}' not found",
            )

        # Return None with 204 No Content status
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting report {id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete report: {str(e)}",
        )


@router.post("/{id}/execute", response_model=ExecuteReportResponse)
async def execute_report(
    id: str,
    format: ExportFormat = Query(ExportFormat.JSON, description="Output format"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(100, ge=1, le=1000, description="Rows per page"),
    pool: asyncpg.Pool = Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Execute a custom report and return the results.

    This endpoint runs a saved report template and returns the results in the
    requested format. The report configuration is used to generate a SQL query
    that is executed against the database.

    Supports three output formats:
    - JSON: Returns structured JSON with metadata (default)
    - CSV: Downloads results as CSV file
    - XLSX: Downloads results as Excel file

    The endpoint also updates the report's execution statistics (last_executed_at
    and execution_count).

    Args:
        id: Report ID (UUID)
        format: Output format (json, csv, xlsx)
        page: Page number for pagination (default: 1)
        page_size: Number of rows per page (default: 100, max: 1000)
        pool: Database connection pool
        _auth: API key authentication

    Returns:
        ExecuteReportResponse: For JSON format with results and metadata
        StreamingResponse: For CSV/XLSX formats as file download

    Raises:
        HTTPException: 404 if report not found, 400 if query build fails,
                      500 if execution error occurs
    """
    try:
        # Fetch the report configuration
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    name,
                    config
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

        # Parse the report configuration
        config_data = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        config = ReportConfig(**config_data)

        # Security validation (defense in depth - config should already be validated on create/update)
        try:
            validate_report_config(config)
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for report {id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid report configuration: {str(e)}",
            )

        # Build the SQL query using QueryBuilder
        try:
            builder = QueryBuilder()
            offset = (page - 1) * page_size
            sql, params = builder.build_query(config, offset=offset)
        except QueryBuilderError as e:
            logger.error(f"Error building query for report {id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid report configuration: {str(e)}",
            )

        # Execute the query and measure execution time
        start_time = time.perf_counter()

        async with pool.acquire() as conn:
            # Convert parameter dict to positional list for asyncpg
            # asyncpg expects $1, $2, etc. but we need to map our param names
            param_values = []
            query_with_placeholders = sql

            # Replace named parameters ($param_1, $param_2) with positional ones ($1, $2)
            for i, (param_name, param_value) in enumerate(sorted(params.items()), start=1):
                query_with_placeholders = query_with_placeholders.replace(f"${param_name}", f"${i}")
                param_values.append(param_value)

            # Execute the query
            rows = await conn.fetch(query_with_placeholders, *param_values)

        execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms

        # Update report execution statistics
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE custom_reports
                SET
                    last_executed_at = $1,
                    execution_count = execution_count + 1
                WHERE id = $2
                """,
                datetime.now(),
                id,
            )

        # Convert rows to list of dicts
        data = [dict(row) for row in rows]

        # Extract column names from first row (if any)
        columns = list(data[0].keys()) if data else []

        # Handle different output formats
        if format == ExportFormat.JSON:
            # Return JSON response with metadata
            return ExecuteReportResponse(
                success=True,
                columns=columns,
                data=data,
                total_rows=len(data),
                page=page,
                page_size=page_size,
                execution_time_ms=execution_time,
                generated_sql=sql,
                errors=[],
            )
        elif format == ExportFormat.CSV:
            # Generate CSV and return as download
            csv_content = _generate_csv(data, columns)
            filename = f"{row['name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

            return StreamingResponse(
                io.BytesIO(csv_content.encode("utf-8")),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store, no-cache, must-revalidate, private",
                    "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        elif format == ExportFormat.XLSX:
            # For now, XLSX is not implemented - return error
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="XLSX export format is not yet implemented. Please use JSON or CSV.",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing report {id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute report: {str(e)}",
        )


def _generate_csv(data: list[dict], columns: list[str]) -> str:
    """Generate CSV content from query results.

    Args:
        data: List of row dictionaries
        columns: List of column names in order

    Returns:
        CSV content as string
    """
    import csv
    from io import StringIO

    output = StringIO()

    if not data:
        return ""

    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()

    for row in data:
        # Convert any non-string values to strings for CSV
        csv_row = {}
        for col in columns:
            value = row.get(col)
            if value is None:
                csv_row[col] = ""
            elif isinstance(value, (datetime,)):
                csv_row[col] = value.isoformat()
            else:
                csv_row[col] = str(value)
        writer.writerow(csv_row)

    return output.getvalue()
