"""Report API endpoints for comprehensive data exports.

This module provides REST endpoints for generating and downloading
reports across all pages and workflows in the application.

Security:
- All endpoints require API key authentication
- Response headers include security best practices
- Cell values are sanitized to prevent formula injection
"""

import io
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..assignment.api.dependencies import get_db_pool, verify_api_key
from .assignment_template import AssignmentTemplateGenerator
from .clients_report import ClientsReportGenerator
from .dashboard_report import DashboardReportGenerator
from .devices_report import DevicesReportGenerator
from .subscriptions_report import SubscriptionsReportGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Security headers for downloads
DOWNLOAD_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


def get_filename(report_type: str, format: str) -> str:
    """Generate a timestamped filename for the report."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"hpe_greenlake_{report_type}_{timestamp}.{format}"


@router.get("/dashboard/export")
async def export_dashboard(
    format: str = Query("xlsx", regex="^(csv|xlsx|json)$", description="Export format"),
    expiring_days: int = Query(90, ge=1, le=365, description="Days for expiring items"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Export dashboard data as Excel, CSV, or JSON.

    Generates a comprehensive dashboard report including:
    - Executive summary with KPIs
    - Device inventory breakdown
    - Subscription analysis
    - Expiring items list
    - Sync history
    """
    # Fetch dashboard data
    async with pool.acquire() as conn:
        # Device stats
        device_stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE assigned_state = 'ASSIGNED_TO_SERVICE') as assigned,
                COUNT(*) FILTER (WHERE assigned_state = 'UNASSIGNED') as unassigned,
                COUNT(*) FILTER (WHERE archived = true) as archived
            FROM devices
        """)

        # Device by type
        device_by_type = await conn.fetch("""
            SELECT
                device_type,
                COUNT(*) as count,
                COUNT(*) FILTER (WHERE assigned_state = 'ASSIGNED_TO_SERVICE') as assigned,
                COUNT(*) FILTER (WHERE assigned_state = 'UNASSIGNED') as unassigned
            FROM devices
            WHERE device_type IS NOT NULL
            GROUP BY device_type
            ORDER BY count DESC
        """)

        # Device by region
        device_by_region = await conn.fetch("""
            SELECT region, COUNT(*) as count
            FROM devices
            WHERE region IS NOT NULL
            GROUP BY region
            ORDER BY count DESC
        """)

        # Subscription stats
        sub_stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE subscription_status = 'STARTED') as active,
                COUNT(*) FILTER (WHERE subscription_status IN ('ENDED', 'CANCELLED')) as expired,
                COUNT(*) FILTER (WHERE subscription_status = 'STARTED' AND end_time IS NOT NULL
                    AND end_time <= NOW() + INTERVAL '90 days') as expiring_soon,
                COALESCE(SUM(quantity), 0) as total_licenses,
                COALESCE(SUM(available_quantity), 0) as available_licenses
            FROM subscriptions
        """)

        total_licenses = sub_stats["total_licenses"] or 1
        available = sub_stats["available_licenses"] or 0
        utilization = int((total_licenses - available) / total_licenses * 100)

        # Subscription by type
        sub_by_type = await conn.fetch("""
            SELECT
                subscription_type,
                COUNT(*) as count,
                COALESCE(SUM(quantity), 0) as total_quantity,
                COALESCE(SUM(available_quantity), 0) as available_quantity
            FROM subscriptions
            WHERE subscription_type IS NOT NULL
            GROUP BY subscription_type
            ORDER BY total_quantity DESC
        """)

        # Expiring items
        expiring_items = await conn.fetch(f"""
            SELECT
                id::text,
                key as identifier,
                'subscription' as item_type,
                subscription_type as sub_type,
                end_time::text,
                EXTRACT(DAY FROM end_time - NOW())::int as days_remaining
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
                AND end_time IS NOT NULL
                AND end_time <= NOW() + INTERVAL '{expiring_days} days'
            ORDER BY end_time
            LIMIT 50
        """)

        # Sync history
        sync_history = await conn.fetch("""
            SELECT
                id,
                resource_type,
                started_at::text,
                completed_at::text,
                status,
                records_fetched,
                records_inserted,
                records_updated,
                records_errors,
                EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000 as duration_ms
            FROM sync_history
            ORDER BY started_at DESC
            LIMIT 10
        """)

    # Build data structure
    data = {
        "device_stats": dict(device_stats) if device_stats else {},
        "device_by_type": [dict(r) for r in device_by_type],
        "device_by_region": [dict(r) for r in device_by_region],
        "subscription_stats": {
            **(dict(sub_stats) if sub_stats else {}),
            "utilization_percent": utilization,
        },
        "subscription_by_type": [dict(r) for r in sub_by_type],
        "expiring_items": [dict(r) for r in expiring_items],
        "sync_history": [dict(r) for r in sync_history],
    }

    generator = DashboardReportGenerator()
    filename = get_filename("dashboard", format)

    if format == "xlsx":
        content = await generator.generate_excel_async(data)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "csv":
        content = await generator.generate_csv_async(data)
        content = content.encode("utf-8")
        media_type = "text/csv"
    else:  # json
        content = await generator.generate_json_async(data)
        content = content.encode("utf-8")
        media_type = "application/json"

    headers = {
        **DOWNLOAD_HEADERS,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers=headers,
    )


@router.get("/devices/export")
async def export_devices(
    format: str = Query("xlsx", regex="^(csv|xlsx)$"),
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    region: Optional[str] = Query(None, description="Filter by region"),
    assigned_state: Optional[str] = Query(None, description="Filter by assignment state"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum records"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Export device inventory as Excel or CSV.

    Supports filtering by device type, region, assignment state, and search.
    """
    # Build query with filters
    where_clauses = []
    params = []
    param_idx = 1

    if device_type:
        where_clauses.append(f"device_type = ${param_idx}")
        params.append(device_type)
        param_idx += 1

    if region:
        where_clauses.append(f"region = ${param_idx}")
        params.append(region)
        param_idx += 1

    if assigned_state:
        where_clauses.append(f"assigned_state = ${param_idx}")
        params.append(assigned_state)
        param_idx += 1

    if search:
        where_clauses.append(f"""
            (serial_number ILIKE ${param_idx}
            OR mac_address ILIKE ${param_idx}
            OR device_name ILIKE ${param_idx}
            OR model ILIKE ${param_idx})
        """)
        params.append(f"%{search}%")
        param_idx += 1

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    async with pool.acquire() as conn:
        devices = await conn.fetch(f"""
            SELECT
                id::text,
                serial_number,
                mac_address,
                device_type,
                model,
                region,
                device_name,
                assigned_state,
                city as location_city,
                country as location_country,
                raw_data->'subscriptions'->0->>'subscription_key' as subscription_key,
                raw_data->'subscriptions'->0->>'subscription_type' as subscription_type,
                raw_data->'subscriptions'->0->>'end_time' as subscription_end,
                COALESCE(
                    (SELECT jsonb_object_agg(t.key, t.value)
                     FROM device_tags t WHERE t.device_id = devices.id),
                    '{{}}'::jsonb
                ) as tags,
                aruba_status as central_status,
                aruba_device_name as central_device_name,
                aruba_device_type as central_device_type,
                aruba_model as central_model,
                aruba_part_number as central_part_number,
                aruba_ipv4 as central_ipv4,
                aruba_ipv6 as central_ipv6,
                aruba_software_version as central_software_version,
                aruba_uptime_millis as central_uptime_millis,
                aruba_last_seen_at as central_last_seen_at,
                aruba_deployment as central_deployment,
                aruba_device_role as central_device_role,
                aruba_device_function as central_device_function,
                aruba_site_name as central_site_name,
                aruba_cluster_name as central_cluster_name,
                aruba_config_status as central_config_status,
                aruba_config_last_modified_at as central_config_last_modified_at,
                (aruba_status IS NOT NULL) as in_central,
                true as in_greenlake,
                updated_at::text
            FROM devices
            {where_sql}
            ORDER BY updated_at DESC
            LIMIT ${param_idx}
        """, *params, limit)

        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM devices {where_sql}
        """, *params)

    data = {
        "items": [dict(r) for r in devices],
        "total": total,
    }

    filters = {
        "device_type": device_type,
        "region": region,
        "assigned_state": assigned_state,
        "search": search,
    }

    generator = DevicesReportGenerator()
    filename = get_filename("devices", format)

    if format == "xlsx":
        content = await generator.generate_excel_async(data, filters)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = await generator.generate_csv_async(data, filters)
        content = content.encode("utf-8")
        media_type = "text/csv"

    headers = {
        **DOWNLOAD_HEADERS,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers=headers,
    )


@router.get("/subscriptions/export")
async def export_subscriptions(
    format: str = Query("xlsx", regex="^(csv|xlsx)$"),
    subscription_type: Optional[str] = Query(None, description="Filter by type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum records"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Export subscription inventory as Excel or CSV."""
    where_clauses = []
    params = []
    param_idx = 1

    if subscription_type:
        where_clauses.append(f"subscription_type = ${param_idx}")
        params.append(subscription_type)
        param_idx += 1

    if status:
        where_clauses.append(f"subscription_status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if search:
        where_clauses.append(f"""
            (key ILIKE ${param_idx}
            OR sku ILIKE ${param_idx}
            OR tier ILIKE ${param_idx})
        """)
        params.append(f"%{search}%")
        param_idx += 1

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    async with pool.acquire() as conn:
        subscriptions = await conn.fetch(f"""
            SELECT
                s.id::text,
                s.key,
                s.subscription_type,
                s.subscription_status,
                s.tier,
                s.sku,
                s.quantity,
                s.available_quantity,
                (s.quantity - s.available_quantity) as used_quantity,
                s.start_time::text,
                s.end_time::text,
                CASE
                    WHEN s.end_time IS NOT NULL
                    THEN EXTRACT(DAY FROM s.end_time - NOW())::int
                    ELSE NULL
                END as days_remaining,
                s.is_eval,
                COALESCE(
                    (SELECT COUNT(*) FROM device_subscriptions ds WHERE ds.subscription_id = s.id),
                    0
                ) as device_count
            FROM subscriptions s
            {where_sql}
            ORDER BY s.end_time ASC NULLS LAST
            LIMIT ${param_idx}
        """, *params, limit)

        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM subscriptions {where_sql}
        """, *params)

    data = {
        "items": [dict(r) for r in subscriptions],
        "total": total,
    }

    filters = {
        "subscription_type": subscription_type,
        "status": status,
        "search": search,
    }

    generator = SubscriptionsReportGenerator()
    filename = get_filename("subscriptions", format)

    if format == "xlsx":
        content = await generator.generate_excel_async(data, filters)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = await generator.generate_csv_async(data, filters)
        content = content.encode("utf-8")
        media_type = "text/csv"

    headers = {
        **DOWNLOAD_HEADERS,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers=headers,
    )


@router.get("/clients/export")
async def export_clients(
    format: str = Query("xlsx", regex="^(csv|xlsx)$"),
    type: Optional[str] = Query(None, description="Filter by type (Wired/Wireless)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    health: Optional[str] = Query(None, description="Filter by health"),
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum records"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Export network clients as Excel or CSV."""
    where_clauses = []
    params = []
    param_idx = 1

    if type:
        where_clauses.append(f"c.type = ${param_idx}")
        params.append(type)
        param_idx += 1

    if status:
        where_clauses.append(f"c.status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if health:
        where_clauses.append(f"c.health = ${param_idx}")
        params.append(health)
        param_idx += 1

    if site_id:
        where_clauses.append(f"c.site_id = ${param_idx}")
        params.append(site_id)
        param_idx += 1

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    async with pool.acquire() as conn:
        clients = await conn.fetch(f"""
            SELECT
                c.id,
                c.mac::text as mac,
                c.name,
                s.site_name,
                c.health,
                c.status,
                c.type,
                c.ipv4::text as ipv4,
                c.ipv6::text as ipv6,
                c.network,
                c.vlan_id::text as vlan_id,
                c.port,
                c.connected_to,
                c.connected_since::text,
                c.last_seen_at::text,
                c.authentication,
                c.key_management
            FROM clients c
            LEFT JOIN sites s ON c.site_id = s.site_id
            {where_sql}
            ORDER BY c.last_seen_at DESC NULLS LAST
            LIMIT ${param_idx}
        """, *params, limit)

        total = await conn.fetchval(f"""
            SELECT COUNT(*) FROM clients c {where_sql}
        """, *params)

        # Get summary stats
        summary = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_clients,
                COUNT(*) FILTER (WHERE status = 'Connected') as connected,
                COUNT(*) FILTER (WHERE type = 'Wired') as wired,
                COUNT(*) FILTER (WHERE type = 'Wireless') as wireless,
                COUNT(*) FILTER (WHERE health = 'Good') as health_good,
                COUNT(*) FILTER (WHERE health = 'Fair') as health_fair,
                COUNT(*) FILTER (WHERE health = 'Poor') as health_poor,
                COUNT(*) FILTER (WHERE health IS NULL OR health NOT IN ('Good', 'Fair', 'Poor')) as health_unknown
            FROM clients
        """)

    data = {
        "items": [dict(r) for r in clients],
        "total": total,
        "summary": dict(summary) if summary else {},
    }

    filters = {
        "type": type,
        "status": status,
        "health": health,
        "site_id": site_id,
    }

    generator = ClientsReportGenerator()
    filename = get_filename("clients", format)

    if format == "xlsx":
        content = await generator.generate_excel_async(data, filters)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = await generator.generate_csv_async(data, filters)
        content = content.encode("utf-8")
        media_type = "text/csv"

    headers = {
        **DOWNLOAD_HEADERS,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers=headers,
    )


@router.get("/assignment/template")
async def download_assignment_template(
    format: str = Query("xlsx", regex="^(csv|xlsx)$"),
    _auth: bool = Depends(verify_api_key),
):
    """Download sample CSV/Excel template for device assignments.

    The template includes:
    - Column headers with descriptions
    - Example data rows (to be deleted before use)
    - Data validation for device types
    - Instructions sheet (Excel only)
    """
    generator = AssignmentTemplateGenerator()
    filename = f"device_assignment_template.{format}"

    if format == "xlsx":
        content = await generator.generate_excel_async({})
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = await generator.generate_csv_async({})
        content = content.encode("utf-8")
        media_type = "text/csv"

    headers = {
        **DOWNLOAD_HEADERS,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers=headers,
    )
