"""FastAPI router for dashboard analytics endpoints."""

import json as json_module
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.glp.api.resilience import get_all_circuit_breaker_status

from .dependencies import get_db_pool, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Track sync status globally
_sync_status = {
    "is_running": False,
    "started_at": None,
    "progress": "",
    "error": None,
}


# ========== Response Schemas ==========


class DeviceStats(BaseModel):
    """Device statistics."""
    total: int = 0
    assigned: int = 0
    unassigned: int = 0
    archived: int = 0


class DeviceTypeBreakdown(BaseModel):
    """Device count by type."""
    device_type: str
    count: int
    assigned: int
    unassigned: int


class RegionBreakdown(BaseModel):
    """Device count by region."""
    region: str
    count: int


class SubscriptionStats(BaseModel):
    """Subscription statistics."""
    total: int = 0
    active: int = 0
    expired: int = 0
    expiring_soon: int = 0
    total_licenses: int = 0
    available_licenses: int = 0
    utilization_percent: float = 0.0


class SubscriptionTypeBreakdown(BaseModel):
    """Subscription count by type."""
    subscription_type: str
    count: int
    total_quantity: int
    available_quantity: int


class ExpiringItem(BaseModel):
    """Item expiring soon."""
    id: str
    identifier: str  # serial_number or subscription_key
    item_type: str  # 'device' or 'subscription'
    sub_type: Optional[str] = None  # device_type or subscription_type
    end_time: datetime
    days_remaining: int


class SyncHistoryItem(BaseModel):
    """Sync history record."""
    id: int
    resource_type: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    records_fetched: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_errors: int = 0
    duration_ms: Optional[int] = None


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status."""
    state: str
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    next_attempt_time: Optional[datetime] = None


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    circuit_breaker: Optional[CircuitBreakerStatus] = None


class DashboardResponse(BaseModel):
    """Complete dashboard data."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Device statistics
    device_stats: DeviceStats
    device_by_type: list[DeviceTypeBreakdown] = Field(default_factory=list)
    device_by_region: list[RegionBreakdown] = Field(default_factory=list)

    # Subscription statistics
    subscription_stats: SubscriptionStats
    subscription_by_type: list[SubscriptionTypeBreakdown] = Field(default_factory=list)

    # Expiring items (devices and subscriptions)
    expiring_items: list[ExpiringItem] = Field(default_factory=list)

    # Sync history
    sync_history: list[SyncHistoryItem] = Field(default_factory=list)

    # Last sync info
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None


# ========== Endpoints ==========


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    expiring_days: int = Query(default=90, ge=1, le=365, description="Days to look ahead for expiring items"),
    sync_history_limit: int = Query(default=10, ge=1, le=50, description="Number of sync history records to return"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get dashboard analytics data.

    Returns comprehensive statistics about devices, subscriptions,
    expiring items, and sync history.
    """
    async with pool.acquire() as conn:
        # 1. Device Statistics
        device_stats_row = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE assigned_state = 'ASSIGNED_TO_SERVICE' AND NOT archived) as assigned,
                COUNT(*) FILTER (WHERE assigned_state = 'UNASSIGNED' AND NOT archived) as unassigned,
                COUNT(*) FILTER (WHERE archived) as archived
            FROM devices
        """)

        device_stats = DeviceStats(
            total=device_stats_row['total'] or 0,
            assigned=device_stats_row['assigned'] or 0,
            unassigned=device_stats_row['unassigned'] or 0,
            archived=device_stats_row['archived'] or 0,
        )

        # 2. Device by Type
        device_type_rows = await conn.fetch("""
            SELECT
                COALESCE(device_type, 'UNKNOWN') as device_type,
                COUNT(*) as count,
                COUNT(*) FILTER (WHERE assigned_state = 'ASSIGNED_TO_SERVICE') as assigned,
                COUNT(*) FILTER (WHERE assigned_state = 'UNASSIGNED') as unassigned
            FROM devices
            WHERE NOT archived
            GROUP BY device_type
            ORDER BY count DESC
        """)

        device_by_type = [
            DeviceTypeBreakdown(
                device_type=row['device_type'],
                count=row['count'],
                assigned=row['assigned'],
                unassigned=row['unassigned'],
            )
            for row in device_type_rows
        ]

        # 3. Device by Region
        device_region_rows = await conn.fetch("""
            SELECT
                COALESCE(region, 'UNKNOWN') as region,
                COUNT(*) as count
            FROM devices
            WHERE NOT archived
            GROUP BY region
            ORDER BY count DESC
        """)

        device_by_region = [
            RegionBreakdown(region=row['region'], count=row['count'])
            for row in device_region_rows
        ]

        # 4. Subscription Statistics
        sub_stats_row = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE subscription_status = 'STARTED') as active,
                COUNT(*) FILTER (WHERE subscription_status = 'ENDED' OR subscription_status = 'CANCELLED') as expired,
                COUNT(*) FILTER (WHERE subscription_status = 'STARTED' AND end_time <= NOW() + INTERVAL '%s days') as expiring_soon,
                COALESCE(SUM(quantity), 0) as total_licenses,
                COALESCE(SUM(available_quantity), 0) as available_licenses
            FROM subscriptions
        """ % expiring_days)

        total_licenses = sub_stats_row['total_licenses'] or 0
        available_licenses = sub_stats_row['available_licenses'] or 0
        used_licenses = total_licenses - available_licenses
        utilization = (used_licenses / total_licenses * 100) if total_licenses > 0 else 0

        subscription_stats = SubscriptionStats(
            total=sub_stats_row['total'] or 0,
            active=sub_stats_row['active'] or 0,
            expired=sub_stats_row['expired'] or 0,
            expiring_soon=sub_stats_row['expiring_soon'] or 0,
            total_licenses=total_licenses,
            available_licenses=available_licenses,
            utilization_percent=round(utilization, 1),
        )

        # 5. Subscription by Type
        sub_type_rows = await conn.fetch("""
            SELECT
                COALESCE(subscription_type, 'UNKNOWN') as subscription_type,
                COUNT(*) as count,
                COALESCE(SUM(quantity), 0) as total_quantity,
                COALESCE(SUM(available_quantity), 0) as available_quantity
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
            GROUP BY subscription_type
            ORDER BY count DESC
        """)

        subscription_by_type = [
            SubscriptionTypeBreakdown(
                subscription_type=row['subscription_type'],
                count=row['count'],
                total_quantity=row['total_quantity'],
                available_quantity=row['available_quantity'],
            )
            for row in sub_type_rows
        ]

        # 6. Expiring Items (both devices with expiring subscriptions and subscriptions)
        expiring_items = []

        # Expiring subscriptions
        expiring_subs = await conn.fetch("""
            SELECT
                id::text,
                key,
                subscription_type,
                end_time,
                EXTRACT(DAY FROM (end_time - NOW()))::int as days_remaining
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND end_time <= NOW() + INTERVAL '%s days'
              AND end_time > NOW()
            ORDER BY end_time ASC
            LIMIT 20
        """ % expiring_days)

        for row in expiring_subs:
            expiring_items.append(ExpiringItem(
                id=row['id'],
                identifier=row['key'],
                item_type='subscription',
                sub_type=row['subscription_type'],
                end_time=row['end_time'],
                days_remaining=row['days_remaining'] or 0,
            ))

        # Devices with expiring subscriptions (via the view, with fallback)
        try:
            view_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.views
                    WHERE table_schema = 'public' AND table_name = 'devices_expiring_soon'
                )
            """)

            if view_exists:
                expiring_devices = await conn.fetch("""
                    SELECT
                        id::text,
                        serial_number,
                        device_type,
                        subscription_end,
                        EXTRACT(DAY FROM (subscription_end - NOW()))::int as days_remaining
                    FROM devices_expiring_soon
                    ORDER BY subscription_end ASC
                    LIMIT 20
                """)

                for row in expiring_devices:
                    expiring_items.append(ExpiringItem(
                        id=row['id'],
                        identifier=row['serial_number'],
                        item_type='device',
                        sub_type=row['device_type'],
                        end_time=row['subscription_end'],
                        days_remaining=row['days_remaining'] or 0,
                    ))
        except Exception as e:
            logger.warning(f"Could not fetch expiring devices: {e}")

        # Sort all expiring items by days remaining
        expiring_items.sort(key=lambda x: x.days_remaining)
        expiring_items = expiring_items[:20]  # Limit to top 20

        # 7. Sync History (with fallback if table doesn't exist)
        sync_history = []
        last_sync_at = None
        last_sync_status = None

        try:
            # Check if sync_history table exists
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'sync_history'
                )
            """)

            if table_exists:
                sync_rows = await conn.fetch("""
                    SELECT
                        id,
                        resource_type,
                        started_at,
                        completed_at,
                        status,
                        records_fetched,
                        records_inserted,
                        records_updated,
                        records_errors,
                        duration_ms
                    FROM sync_history
                    ORDER BY started_at DESC
                    LIMIT $1
                """, sync_history_limit)

                sync_history = [
                    SyncHistoryItem(
                        id=row['id'],
                        resource_type=row['resource_type'],
                        started_at=row['started_at'],
                        completed_at=row['completed_at'],
                        status=row['status'],
                        records_fetched=row['records_fetched'] or 0,
                        records_inserted=row['records_inserted'] or 0,
                        records_updated=row['records_updated'] or 0,
                        records_errors=row['records_errors'] or 0,
                        duration_ms=row['duration_ms'],
                    )
                    for row in sync_rows
                ]

                # Last sync info
                if sync_history:
                    last_sync_at = sync_history[0].completed_at or sync_history[0].started_at
                    last_sync_status = sync_history[0].status
        except Exception as e:
            logger.warning(f"Could not fetch sync history: {e}")

        return DashboardResponse(
            device_stats=device_stats,
            device_by_type=device_by_type,
            device_by_region=device_by_region,
            subscription_stats=subscription_stats,
            subscription_by_type=subscription_by_type,
            expiring_items=expiring_items,
            sync_history=sync_history,
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
        )


@router.get("/devices/search")
async def search_devices(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Search devices using full-text search."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM search_devices($1, $2)
        """, q, limit)

        return [dict(row) for row in rows]


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint with circuit breaker status.

    Returns the overall health status and circuit breaker state.
    If multiple circuit breakers exist, returns the most critical one
    (open > half_open > closed).
    """
    # Get all circuit breaker statuses
    cb_statuses = get_all_circuit_breaker_status()

    circuit_breaker_status = None
    if cb_statuses:
        # Sort by priority: open > half_open > closed
        state_priority = {"open": 0, "half_open": 1, "closed": 2}
        sorted_cbs = sorted(cb_statuses, key=lambda x: state_priority.get(x["state"], 999))
        most_critical = sorted_cbs[0]

        # Parse last_failure_at if present
        last_failure_time = None
        if most_critical.get("last_failure_at"):
            try:
                last_failure_time = datetime.fromisoformat(most_critical["last_failure_at"])
            except (ValueError, TypeError):
                pass

        # Calculate next_attempt_time for open circuits
        next_attempt_time = None
        if most_critical["state"] == "open" and last_failure_time:
            timeout_seconds = most_critical.get("timeout_seconds", 60.0)
            next_attempt_time = last_failure_time + timedelta(seconds=timeout_seconds)

        circuit_breaker_status = CircuitBreakerStatus(
            state=most_critical["state"],
            failure_count=most_critical.get("failure_count", 0),
            last_failure_time=last_failure_time,
            next_attempt_time=next_attempt_time,
        )

    # Overall health status based on circuit breaker state
    overall_status = "healthy"
    if circuit_breaker_status and circuit_breaker_status.state == "open":
        overall_status = "degraded"

    return HealthCheckResponse(
        status=overall_status,
        circuit_breaker=circuit_breaker_status,
    )


# ========== Sync Endpoints ==========


class SyncResponse(BaseModel):
    """Sync operation response."""
    status: str
    message: str
    started_at: Optional[datetime] = None
    devices: Optional[dict] = None
    subscriptions: Optional[dict] = None
    central: Optional[dict] = None


class SyncStatusResponse(BaseModel):
    """Sync status response."""
    is_running: bool
    started_at: Optional[datetime] = None
    progress: str = ""
    error: Optional[str] = None


async def _record_sync_history(
    pool,
    resource_type: str,
    started_at: datetime,
    result: dict,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Record sync history in database.

    Note: duration_ms is a generated column computed from started_at and completed_at.
    Status must be 'running', 'completed', or 'failed' per the CHECK constraint.
    Resource types: 'devices', 'subscriptions', 'all', 'central_devices', 'clients', 'firmware'.

    Field mapping:
        Syncers return: {total, upserted, errors} or {total, inserted, updated, errors}
        We normalize to: {records_fetched, records_inserted, records_updated, records_errors}
    """
    # Map legacy status values to allowed values
    status_map = {"success": "completed", "error": "failed"}
    normalized_status = status_map.get(status, status)

    # Map legacy resource types to allowed values
    resource_type_map = {"central": "central_devices"}
    normalized_resource_type = resource_type_map.get(resource_type, resource_type)

    # Normalize field names from syncer results
    # Syncers may return 'upserted' (combined insert/update) or separate 'inserted'/'updated'
    records_fetched = result.get("total", 0) or 0
    records_inserted = result.get("inserted", 0) or result.get("upserted", 0) or 0
    records_updated = result.get("updated", 0) or 0
    records_errors = result.get("errors", 0) or 0

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sync_history (
                    resource_type, started_at, completed_at, status,
                    records_fetched, records_inserted, records_updated,
                    records_errors, error_message
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                normalized_resource_type,
                started_at,
                datetime.now(timezone.utc),
                normalized_status,
                records_fetched,
                records_inserted,
                records_updated,
                records_errors,
                error_message,
            )
        logger.info(f"Recorded sync history: {normalized_resource_type} - {records_fetched} fetched, {records_inserted} inserted")
    except Exception as e:
        logger.warning(f"Failed to record sync history: {e}")


async def run_greenlake_sync(pool) -> dict:
    """Run the GreenLake and Aruba Central sync operation.

    Returns sync statistics for devices, subscriptions, and Central devices.
    """
    global _sync_status

    try:
        from src.glp.api import (
            ArubaCentralClient,
            ArubaCentralSyncer,
            ArubaTokenManager,
            DeviceSyncer,
            GLPClient,
            SubscriptionSyncer,
            TokenManager,
        )

        _sync_status["progress"] = "Initializing..."

        results = {"devices": None, "subscriptions": None, "central": None}

        # GreenLake sync
        try:
            token_manager = TokenManager()

            async with GLPClient(token_manager) as client:
                # Sync subscriptions FIRST (before devices)
                # This ensures subscription records exist before device_subscriptions
                # foreign key references are created during device sync
                _sync_status["progress"] = "Syncing subscriptions from GreenLake..."
                sub_started = datetime.now(timezone.utc)
                sub_syncer = SubscriptionSyncer(client=client, db_pool=pool)
                results["subscriptions"] = await sub_syncer.sync()
                logger.info(f"Subscription sync complete: {results['subscriptions']}")

                # Record subscription sync history (duration_ms computed from timestamps)
                await _record_sync_history(
                    pool, "subscriptions", sub_started, results["subscriptions"], "completed"
                )

                # Sync devices AFTER subscriptions exist
                _sync_status["progress"] = "Syncing devices from GreenLake..."
                device_started = datetime.now(timezone.utc)
                device_syncer = DeviceSyncer(client=client, db_pool=pool)
                results["devices"] = await device_syncer.sync()
                logger.info(f"Device sync complete: {results['devices']}")

                # Record device sync history (duration_ms computed from timestamps)
                await _record_sync_history(
                    pool, "devices", device_started, results["devices"], "completed"
                )
        except ValueError as e:
            logger.warning(f"GreenLake sync skipped (missing credentials): {e}")
            results["devices"] = {"skipped": True, "reason": str(e)}
            results["subscriptions"] = {"skipped": True, "reason": str(e)}

        # Aruba Central sync (enriches existing GreenLake devices)
        try:
            _sync_status["progress"] = "Syncing devices from Aruba Central..."
            central_started = datetime.now(timezone.utc)
            aruba_token_manager = ArubaTokenManager()

            async with ArubaCentralClient(aruba_token_manager) as central_client:
                central_syncer = ArubaCentralSyncer(client=central_client, db_pool=pool)
                results["central"] = await central_syncer.sync()
                logger.info(f"Aruba Central sync complete: {results['central']}")

                # Record central sync history (resource_type mapped to 'central_devices')
                await _record_sync_history(
                    pool, "central", central_started, results["central"], "completed"
                )
        except ValueError as e:
            logger.warning(f"Aruba Central sync skipped (missing credentials): {e}")
            results["central"] = {"skipped": True, "reason": str(e)}
        except Exception as e:
            logger.warning(f"Aruba Central sync failed: {e}")
            results["central"] = {"error": str(e)}
            # Record failed sync
            await _record_sync_history(
                pool, "central", central_started if 'central_started' in dir() else datetime.now(timezone.utc),
                {}, "failed", str(e)
            )

        _sync_status["progress"] = "Sync complete!"
        return results

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        _sync_status["error"] = str(e)
        raise


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Trigger a full sync with GreenLake API.

    This fetches fresh device and subscription data from the
    GreenLake API and updates the local database.
    """
    global _sync_status

    if _sync_status["is_running"]:
        raise HTTPException(
            status_code=409,
            detail="A sync operation is already in progress"
        )

    _sync_status["is_running"] = True
    _sync_status["started_at"] = datetime.now(timezone.utc)
    _sync_status["progress"] = "Starting sync..."
    _sync_status["error"] = None

    try:
        results = await run_greenlake_sync(pool)

        return SyncResponse(
            status="completed",
            message="Sync completed successfully",
            started_at=_sync_status["started_at"],
            devices=results["devices"],
            subscriptions=results["subscriptions"],
            central=results.get("central"),
        )

    except ValueError as e:
        # Configuration error (missing credentials)
        _sync_status["error"] = str(e)
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {e}. Check GLP_CLIENT_ID, GLP_CLIENT_SECRET, GLP_TOKEN_URL environment variables."
        )

    except Exception as e:
        _sync_status["error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

    finally:
        _sync_status["is_running"] = False


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(_auth: bool = Depends(verify_api_key)):
    """Get the current sync status."""
    return SyncStatusResponse(
        is_running=_sync_status["is_running"],
        started_at=_sync_status["started_at"],
        progress=_sync_status["progress"],
        error=_sync_status["error"],
    )


# ========== Paginated List Endpoints ==========


class DeviceListItem(BaseModel):
    """Device item for list view."""
    id: str
    serial_number: str
    mac_address: Optional[str] = None
    device_type: Optional[str] = None
    model: Optional[str] = None
    region: Optional[str] = None
    device_name: Optional[str] = None
    assigned_state: Optional[str] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    subscription_key: Optional[str] = None
    subscription_type: Optional[str] = None
    subscription_end: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # GreenLake tags
    tags: dict[str, str] = {}

    # Aruba Central fields - Core
    central_status: Optional[str] = None
    central_device_name: Optional[str] = None
    central_device_type: Optional[str] = None
    # Aruba Central fields - Hardware
    central_model: Optional[str] = None
    central_part_number: Optional[str] = None
    # Aruba Central fields - Connectivity
    central_ipv4: Optional[str] = None
    central_ipv6: Optional[str] = None
    central_software_version: Optional[str] = None
    central_uptime_millis: Optional[int] = None
    central_last_seen_at: Optional[datetime] = None
    # Aruba Central fields - Deployment
    central_deployment: Optional[str] = None
    central_device_role: Optional[str] = None
    central_device_function: Optional[str] = None
    # Aruba Central fields - Location
    central_site_name: Optional[str] = None
    central_cluster_name: Optional[str] = None
    # Aruba Central fields - Config
    central_config_status: Optional[str] = None
    central_config_last_modified_at: Optional[datetime] = None
    # Platform presence flags
    in_central: bool = False
    in_greenlake: bool = True


class DeviceListResponse(BaseModel):
    """Paginated device list response."""
    items: list[DeviceListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=100, ge=10, le=1000, description="Items per page (10, 100, 500, 1000)"),
    search: Optional[str] = Query(default=None, description="Search query (serial, MAC, name, model)"),
    device_type: Optional[str] = Query(default=None, description="Filter by device type"),
    region: Optional[str] = Query(default=None, description="Filter by region"),
    assigned_state: Optional[str] = Query(default=None, description="Filter by assignment state"),
    subscription_key: Optional[str] = Query(default=None, description="Filter by subscription key"),
    include_archived: bool = Query(default=False, description="Include archived devices"),
    sort_by: str = Query(default="updated_at", description="Sort field"),
    sort_order: str = Query(default="desc", description="Sort order (asc/desc)"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get paginated list of devices with optional filtering and search."""
    async with pool.acquire() as conn:
        # Build the query dynamically
        where_clauses = []
        params = []
        param_idx = 1

        # Handle archived filter - by default exclude archived
        if not include_archived:
            where_clauses.append("NOT d.archived")

        if search:
            # Use full-text search if search term provided
            where_clauses.append(f"d.search_vector @@ websearch_to_tsquery('english', ${param_idx})")
            params.append(search)
            param_idx += 1

        if device_type:
            where_clauses.append(f"d.device_type = ${param_idx}")
            params.append(device_type)
            param_idx += 1

        if region:
            where_clauses.append(f"d.region = ${param_idx}")
            params.append(region)
            param_idx += 1

        if assigned_state:
            where_clauses.append(f"d.assigned_state = ${param_idx}")
            params.append(assigned_state)
            param_idx += 1

        if subscription_key:
            where_clauses.append(f"s.key = ${param_idx}")
            params.append(subscription_key)
            param_idx += 1

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        # Validate sort column to prevent SQL injection
        valid_sort_cols = {"serial_number", "device_type", "model", "region", "device_name", "assigned_state", "updated_at", "created_at"}
        if sort_by not in valid_sort_cols:
            sort_by = "updated_at"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Count total - need JOIN if filtering by subscription_key
        if subscription_key:
            count_sql = f"""
                SELECT COUNT(*) FROM devices d
                LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
                LEFT JOIN subscriptions s ON ds.subscription_id = s.id
                WHERE {where_sql}
            """
        else:
            count_sql = f"SELECT COUNT(*) FROM devices d WHERE {where_sql}"
        total = await conn.fetchval(count_sql, *params)

        # Calculate pagination
        offset = (page - 1) * page_size
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Fetch items with subscription info and Central data
        query_sql = f"""
            SELECT
                d.id::text,
                d.serial_number,
                d.mac_address,
                d.device_type,
                d.model,
                d.region,
                d.device_name,
                d.assigned_state,
                d.location_city,
                d.location_country,
                d.updated_at,
                s.key as subscription_key,
                s.subscription_type,
                s.end_time as subscription_end,
                -- GreenLake tags
                d.raw_data->'tags' as tags,
                -- Aruba Central fields - Core
                d.central_status,
                d.central_device_name,
                d.central_device_type,
                -- Aruba Central fields - Hardware
                d.central_model,
                d.central_part_number,
                -- Aruba Central fields - Connectivity
                d.central_ipv4,
                d.central_ipv6,
                d.central_software_version,
                d.central_uptime_millis,
                d.central_last_seen_at,
                -- Aruba Central fields - Deployment
                d.central_deployment,
                d.central_device_role,
                d.central_device_function,
                -- Aruba Central fields - Location
                d.central_site_name,
                d.central_cluster_name,
                -- Aruba Central fields - Config
                d.central_config_status,
                d.central_config_last_modified_at,
                -- Platform presence flags
                COALESCE(d.in_central, FALSE) as in_central,
                COALESCE(d.in_greenlake, TRUE) as in_greenlake
            FROM devices d
            LEFT JOIN device_subscriptions ds ON d.id = ds.device_id
            LEFT JOIN subscriptions s ON ds.subscription_id = s.id
            WHERE {where_sql}
            ORDER BY d.{sort_by} {sort_direction} NULLS LAST
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        rows = await conn.fetch(query_sql, *params)

        items = [
            DeviceListItem(
                id=row['id'],
                serial_number=row['serial_number'],
                mac_address=row['mac_address'],
                device_type=row['device_type'],
                model=row['model'],
                region=row['region'],
                device_name=row['device_name'],
                assigned_state=row['assigned_state'],
                location_city=row['location_city'],
                location_country=row['location_country'],
                subscription_key=row['subscription_key'],
                subscription_type=row['subscription_type'],
                subscription_end=row['subscription_end'],
                updated_at=row['updated_at'],
                # GreenLake tags (parse from JSON string if needed, default to empty dict)
                tags=(row['tags'] if isinstance(row['tags'], dict) else (json_module.loads(row['tags']) if row['tags'] else {})) or {},
                # Aruba Central fields - Core
                central_status=row['central_status'],
                central_device_name=row['central_device_name'],
                central_device_type=row['central_device_type'],
                # Aruba Central fields - Hardware
                central_model=row['central_model'],
                central_part_number=row['central_part_number'],
                # Aruba Central fields - Connectivity
                central_ipv4=row['central_ipv4'],
                central_ipv6=row['central_ipv6'],
                central_software_version=row['central_software_version'],
                central_uptime_millis=row['central_uptime_millis'],
                central_last_seen_at=row['central_last_seen_at'],
                # Aruba Central fields - Deployment
                central_deployment=row['central_deployment'],
                central_device_role=row['central_device_role'],
                central_device_function=row['central_device_function'],
                # Aruba Central fields - Location
                central_site_name=row['central_site_name'],
                central_cluster_name=row['central_cluster_name'],
                # Aruba Central fields - Config
                central_config_status=row['central_config_status'],
                central_config_last_modified_at=row['central_config_last_modified_at'],
                # Platform presence flags
                in_central=row['in_central'],
                in_greenlake=row['in_greenlake'],
            )
            for row in rows
        ]

        return DeviceListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class SubscriptionListItem(BaseModel):
    """Subscription item for list view."""
    id: str
    key: str
    subscription_type: Optional[str] = None
    subscription_status: Optional[str] = None
    tier: Optional[str] = None
    sku: Optional[str] = None
    quantity: int = 0
    available_quantity: int = 0
    used_quantity: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    days_remaining: Optional[int] = None
    is_eval: bool = False
    device_count: int = 0


class SubscriptionListResponse(BaseModel):
    """Paginated subscription list response."""
    items: list[SubscriptionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/subscriptions", response_model=SubscriptionListResponse)
async def list_subscriptions(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=100, ge=10, le=1000, description="Items per page"),
    search: Optional[str] = Query(default=None, description="Search query (key, SKU, tier)"),
    subscription_type: Optional[str] = Query(default=None, description="Filter by subscription type"),
    subscription_status: Optional[str] = Query(default=None, description="Filter by status"),
    sort_by: str = Query(default="end_time", description="Sort field"),
    sort_order: str = Query(default="asc", description="Sort order (asc/desc)"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get paginated list of subscriptions with device counts."""
    async with pool.acquire() as conn:
        # Build the query dynamically
        where_clauses = ["1=1"]
        params = []
        param_idx = 1

        if search:
            where_clauses.append(f"s.search_vector @@ websearch_to_tsquery('english', ${param_idx})")
            params.append(search)
            param_idx += 1

        if subscription_type:
            where_clauses.append(f"s.subscription_type = ${param_idx}")
            params.append(subscription_type)
            param_idx += 1

        if subscription_status:
            where_clauses.append(f"s.subscription_status = ${param_idx}")
            params.append(subscription_status)
            param_idx += 1

        where_sql = " AND ".join(where_clauses)

        # Validate sort column
        valid_sort_cols = {"key", "subscription_type", "subscription_status", "tier", "quantity", "available_quantity", "start_time", "end_time"}
        if sort_by not in valid_sort_cols:
            sort_by = "end_time"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Count total
        count_sql = f"SELECT COUNT(*) FROM subscriptions s WHERE {where_sql}"
        total = await conn.fetchval(count_sql, *params)

        # Calculate pagination
        offset = (page - 1) * page_size
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Fetch items with device count
        query_sql = f"""
            SELECT
                s.id::text,
                s.key,
                s.subscription_type,
                s.subscription_status,
                s.tier,
                s.sku,
                s.quantity,
                s.available_quantity,
                s.start_time,
                s.end_time,
                s.is_eval,
                COALESCE(dc.device_count, 0) as device_count,
                CASE
                    WHEN s.end_time IS NOT NULL AND s.end_time > NOW()
                    THEN EXTRACT(DAY FROM (s.end_time - NOW()))::int
                    ELSE NULL
                END as days_remaining
            FROM subscriptions s
            LEFT JOIN (
                SELECT subscription_id, COUNT(*) as device_count
                FROM device_subscriptions
                GROUP BY subscription_id
            ) dc ON s.id = dc.subscription_id
            WHERE {where_sql}
            ORDER BY s.{sort_by} {sort_direction} NULLS LAST
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        rows = await conn.fetch(query_sql, *params)

        items = [
            SubscriptionListItem(
                id=row['id'],
                key=row['key'],
                subscription_type=row['subscription_type'],
                subscription_status=row['subscription_status'],
                tier=row['tier'],
                sku=row['sku'],
                quantity=row['quantity'] or 0,
                available_quantity=row['available_quantity'] or 0,
                used_quantity=(row['quantity'] or 0) - (row['available_quantity'] or 0),
                start_time=row['start_time'],
                end_time=row['end_time'],
                days_remaining=row['days_remaining'],
                is_eval=row['is_eval'] or False,
                device_count=row['device_count'],
            )
            for row in rows
        ]

        return SubscriptionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class FilterOptions(BaseModel):
    """Available filter options."""
    device_types: list[str]
    regions: list[str]
    subscription_types: list[str]
    subscription_statuses: list[str]


@router.get("/filters", response_model=FilterOptions)
async def get_filter_options(
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get available filter options for devices and subscriptions."""
    async with pool.acquire() as conn:
        device_types = await conn.fetch("""
            SELECT DISTINCT device_type FROM devices WHERE device_type IS NOT NULL ORDER BY device_type
        """)
        regions = await conn.fetch("""
            SELECT DISTINCT region FROM devices WHERE region IS NOT NULL ORDER BY region
        """)
        sub_types = await conn.fetch("""
            SELECT DISTINCT subscription_type FROM subscriptions WHERE subscription_type IS NOT NULL ORDER BY subscription_type
        """)
        sub_statuses = await conn.fetch("""
            SELECT DISTINCT subscription_status FROM subscriptions WHERE subscription_status IS NOT NULL ORDER BY subscription_status
        """)

        return FilterOptions(
            device_types=[r['device_type'] for r in device_types],
            regions=[r['region'] for r in regions],
            subscription_types=[r['subscription_type'] for r in sub_types],
            subscription_statuses=[r['subscription_status'] for r in sub_statuses],
        )
