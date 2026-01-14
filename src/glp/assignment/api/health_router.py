"""FastAPI router for device health aggregation endpoints.

Provides API endpoints for viewing aggregated device health metrics
by site and region, leveraging the device_health_aggregation view.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .dependencies import get_db_pool, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["Health"])


# ========== Response Schemas ==========


class DeviceHealthStats(BaseModel):
    """Device health statistics for a site/region."""
    site_id: str
    site_name: str
    region: str

    # Total device counts
    total_devices: int = 0
    central_devices: int = 0
    greenlake_devices: int = 0

    # Online/Offline status
    online_count: int = 0
    offline_count: int = 0
    status_unknown: int = 0

    # Firmware classification
    firmware_critical: int = 0
    firmware_recommended: int = 0
    firmware_current: int = 0
    firmware_unknown: int = 0

    # Device type breakdown
    access_points: int = 0
    switches: int = 0
    gateways: int = 0
    type_unknown: int = 0

    # Health percentage
    health_percentage: Optional[float] = None

    # Last sync timestamp
    last_synced_at: Optional[datetime] = None


class DeviceHealthResponse(BaseModel):
    """Paginated device health response."""
    items: list[DeviceHealthStats]
    total: int
    page: int
    page_size: int
    total_pages: int


class OverallHealthSummary(BaseModel):
    """Overall health summary across all sites."""
    total_devices: int = 0
    total_sites: int = 0
    online_count: int = 0
    offline_count: int = 0
    status_unknown: int = 0
    overall_health_percentage: Optional[float] = None
    firmware_critical: int = 0
    firmware_recommended: int = 0
    firmware_current: int = 0
    firmware_unknown: int = 0
    access_points: int = 0
    switches: int = 0
    gateways: int = 0
    type_unknown: int = 0


# ========== Endpoints ==========


@router.get("/device-health", response_model=DeviceHealthResponse)
async def get_device_health(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=10, le=1000, description="Items per page"),
    site_id: Optional[str] = Query(default=None, description="Filter by site ID - comma-delimited"),
    region: Optional[str] = Query(default=None, description="Filter by region - comma-delimited"),
    min_health: Optional[float] = Query(default=None, ge=0, le=100, description="Minimum health percentage"),
    max_health: Optional[float] = Query(default=None, ge=0, le=100, description="Maximum health percentage"),
    has_offline: Optional[bool] = Query(default=None, description="Filter sites with offline devices"),
    has_critical_firmware: Optional[bool] = Query(default=None, description="Filter sites with critical firmware"),
    sort_by: str = Query(default="total_devices", description="Sort field"),
    sort_order: str = Query(default="desc", description="Sort order (asc/desc)"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get device health aggregation by site and region.

    Returns health metrics including online/offline counts, firmware classification,
    and device type breakdown for each site.

    Supports filtering by:
    - site_id: Comma-delimited list of site IDs
    - region: Comma-delimited list of regions
    - min_health/max_health: Health percentage range
    - has_offline: Sites with offline devices
    - has_critical_firmware: Sites with critical firmware updates needed
    """
    async with pool.acquire() as conn:
        # Build WHERE clause with multi-value support
        where_clauses = []
        params = []
        param_idx = 1

        # Helper to add multi-value filter
        def add_multi_filter(value: str, column: str):
            nonlocal param_idx
            values = [v.strip() for v in value.split(',') if v.strip()]
            if values:
                where_clauses.append(f"{column} = ANY(${param_idx}::text[])")
                params.append(values)
                param_idx += 1

        # Parse comma-delimited filters
        if site_id:
            add_multi_filter(site_id, "site_id")

        if region:
            add_multi_filter(region, "region")

        # Health percentage range
        if min_health is not None:
            where_clauses.append(f"health_percentage >= ${param_idx}")
            params.append(min_health)
            param_idx += 1

        if max_health is not None:
            where_clauses.append(f"health_percentage <= ${param_idx}")
            params.append(max_health)
            param_idx += 1

        # Boolean filters
        if has_offline is not None and has_offline:
            where_clauses.append("offline_count > 0")

        if has_critical_firmware is not None and has_critical_firmware:
            where_clauses.append("firmware_critical > 0")

        # Build WHERE clause
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Validate sort field
        allowed_sort_fields = [
            "site_name",
            "region",
            "total_devices",
            "online_count",
            "offline_count",
            "health_percentage",
            "firmware_critical",
            "last_synced_at",
        ]
        if sort_by not in allowed_sort_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort_by field. Allowed: {', '.join(allowed_sort_fields)}",
            )

        # Validate sort order
        if sort_order.lower() not in ["asc", "desc"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid sort_order. Use 'asc' or 'desc'",
            )

        # Get total count
        count_query = f"""
            SELECT COUNT(*)
            FROM device_health_aggregation
            {where_sql}
        """
        total = await conn.fetchval(count_query, *params)

        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        offset = (page - 1) * page_size

        # Get paginated data
        data_query = f"""
            SELECT
                site_id,
                site_name,
                region,
                total_devices,
                central_devices,
                greenlake_devices,
                online_count,
                offline_count,
                status_unknown,
                firmware_critical,
                firmware_recommended,
                firmware_current,
                firmware_unknown,
                access_points,
                switches,
                gateways,
                type_unknown,
                health_percentage,
                last_synced_at
            FROM device_health_aggregation
            {where_sql}
            ORDER BY {sort_by} {sort_order.upper()}
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        rows = await conn.fetch(data_query, *params)

        # Convert to response models
        items = [
            DeviceHealthStats(
                site_id=row['site_id'],
                site_name=row['site_name'],
                region=row['region'],
                total_devices=row['total_devices'],
                central_devices=row['central_devices'],
                greenlake_devices=row['greenlake_devices'],
                online_count=row['online_count'],
                offline_count=row['offline_count'],
                status_unknown=row['status_unknown'],
                firmware_critical=row['firmware_critical'],
                firmware_recommended=row['firmware_recommended'],
                firmware_current=row['firmware_current'],
                firmware_unknown=row['firmware_unknown'],
                access_points=row['access_points'],
                switches=row['switches'],
                gateways=row['gateways'],
                type_unknown=row['type_unknown'],
                health_percentage=row['health_percentage'],
                last_synced_at=row['last_synced_at'],
            )
            for row in rows
        ]

        return DeviceHealthResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


@router.get("/summary", response_model=OverallHealthSummary)
async def get_overall_health_summary(
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get overall health summary across all sites.

    Returns aggregated metrics including total devices, online/offline counts,
    firmware status, and device type distribution.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                SUM(total_devices) AS total_devices,
                COUNT(*) AS total_sites,
                SUM(online_count) AS online_count,
                SUM(offline_count) AS offline_count,
                SUM(status_unknown) AS status_unknown,
                SUM(firmware_critical) AS firmware_critical,
                SUM(firmware_recommended) AS firmware_recommended,
                SUM(firmware_current) AS firmware_current,
                SUM(firmware_unknown) AS firmware_unknown,
                SUM(access_points) AS access_points,
                SUM(switches) AS switches,
                SUM(gateways) AS gateways,
                SUM(type_unknown) AS type_unknown,
                CASE
                    WHEN SUM(central_devices) > 0 THEN
                        ROUND(
                            (SUM(online_count)::NUMERIC / SUM(central_devices)::NUMERIC) * 100,
                            2
                        )
                    ELSE NULL
                END AS overall_health_percentage
            FROM device_health_aggregation
        """)

        return OverallHealthSummary(
            total_devices=row['total_devices'] or 0,
            total_sites=row['total_sites'] or 0,
            online_count=row['online_count'] or 0,
            offline_count=row['offline_count'] or 0,
            status_unknown=row['status_unknown'] or 0,
            overall_health_percentage=row['overall_health_percentage'],
            firmware_critical=row['firmware_critical'] or 0,
            firmware_recommended=row['firmware_recommended'] or 0,
            firmware_current=row['firmware_current'] or 0,
            firmware_unknown=row['firmware_unknown'] or 0,
            access_points=row['access_points'] or 0,
            switches=row['switches'] or 0,
            gateways=row['gateways'] or 0,
            type_unknown=row['type_unknown'] or 0,
        )
