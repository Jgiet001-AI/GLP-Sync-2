"""
FastMCP Server for HPE GreenLake Device & Subscription Inventory

A read-only MCP server providing tools, resources, prompts, and sampling
for querying the PostgreSQL database.

Usage:
    python server.py                              # stdio transport (default)
    python server.py --transport http --port 8000 # HTTP transport
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import asyncpg
from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# Write Operation Risk Assessment (for confirmation workflows)
# =============================================================================

from enum import Enum


class RiskLevel(str, Enum):
    """Risk level of operations for confirmation requirements."""

    LOW = "low"  # No confirmation needed
    MEDIUM = "medium"  # Confirmation recommended
    HIGH = "high"  # Confirmation required
    CRITICAL = "critical"  # Multi-step confirmation required


class OperationType(str, Enum):
    """Types of write operations."""

    ADD_DEVICE = "add_device"
    UPDATE_TAGS = "update_tags"
    APPLY_ASSIGNMENTS = "apply_assignments"
    ARCHIVE_DEVICES = "archive_devices"
    UNARCHIVE_DEVICES = "unarchive_devices"


# Risk assessment configuration
RISK_THRESHOLDS = {
    OperationType.ADD_DEVICE: RiskLevel.LOW,
    OperationType.UPDATE_TAGS: RiskLevel.LOW,
    OperationType.APPLY_ASSIGNMENTS: RiskLevel.MEDIUM,
    OperationType.ARCHIVE_DEVICES: RiskLevel.HIGH,
    OperationType.UNARCHIVE_DEVICES: RiskLevel.MEDIUM,
}

# Device count thresholds for elevated risk
BULK_THRESHOLD = 5  # > 5 devices elevates risk
MASS_THRESHOLD = 20  # > 20 devices requires critical confirmation


def _assess_risk(
    operation_type: OperationType,
    device_count: int = 0,
) -> RiskLevel:
    """Assess the risk level of an operation.

    Args:
        operation_type: Type of operation
        device_count: Number of devices affected

    Returns:
        Assessed risk level
    """
    base_risk = RISK_THRESHOLDS.get(operation_type, RiskLevel.MEDIUM)

    # Elevate risk based on number of devices affected
    if device_count > MASS_THRESHOLD:
        return RiskLevel.CRITICAL
    elif device_count > BULK_THRESHOLD:
        # Elevate by one level
        if base_risk == RiskLevel.LOW:
            return RiskLevel.MEDIUM
        elif base_risk == RiskLevel.MEDIUM:
            return RiskLevel.HIGH

    return base_risk


def _get_confirmation_message(
    operation_type: OperationType,
    device_count: int,
    risk_level: RiskLevel,
) -> str:
    """Generate a confirmation message for the user.

    Args:
        operation_type: Type of operation
        device_count: Number of devices affected
        risk_level: Assessed risk level

    Returns:
        Confirmation message
    """
    messages = {
        OperationType.ARCHIVE_DEVICES: (
            f"Are you sure you want to archive {device_count} device(s)? "
            "Archived devices will no longer receive updates and will be hidden from normal views."
        ),
        OperationType.UNARCHIVE_DEVICES: (
            f"Restore {device_count} archived device(s)?"
        ),
        OperationType.APPLY_ASSIGNMENTS: (
            f"Apply assignments to {device_count} device(s)?"
        ),
    }

    base_message = messages.get(
        operation_type,
        f"Execute {operation_type.value} on {device_count} device(s)?",
    )

    if risk_level == RiskLevel.CRITICAL:
        return f"⚠️ WARNING: High-risk operation affecting {device_count} devices. {base_message}"

    return base_message


# =============================================================================
# Assignment Module Dependencies (optional - for write tools)
# =============================================================================

# Try to import assignment module dependencies for write operations
try:
    from src.glp.assignment.adapters import (
        GLPDeviceManagerAdapter,
        DeviceSyncerAdapter,
        PostgresDeviceRepository,
        PostgresSubscriptionRepository,
    )
    from src.glp.assignment.domain.entities import DeviceAssignment, WorkflowAction
    from src.glp.assignment.use_cases.apply_assignments import ApplyAssignmentsUseCase
    from src.glp.assignment.use_cases.device_actions import DeviceActionsUseCase
    from src.glp.api.auth import TokenManager
    from src.glp.api.client import GLPClient
    from src.glp.api.device_manager import DeviceManager
    from src.glp.api.devices import DeviceSyncer
    from src.glp.api.resilience import SequentialRateLimiter
    from src.glp.api.subscriptions import SubscriptionSyncer

    ASSIGNMENT_MODULE_AVAILABLE = True
    logger.info("Assignment module dependencies loaded successfully")
except ImportError as e:
    ASSIGNMENT_MODULE_AVAILABLE = False
    logger.warning(f"Assignment module not available (write tools will not work): {e}")
    # Define placeholders to avoid NameError
    GLPDeviceManagerAdapter = None
    DeviceSyncerAdapter = None
    PostgresDeviceRepository = None
    PostgresSubscriptionRepository = None
    DeviceAssignment = None
    WorkflowAction = None
    ApplyAssignmentsUseCase = None
    DeviceActionsUseCase = None
    TokenManager = None
    GLPClient = None
    DeviceManager = None
    DeviceSyncer = None
    SubscriptionSyncer = None
    SequentialRateLimiter = None

# =============================================================================
# Database Connection Pool (Lifespan)
# =============================================================================

# Global pool reference for REST API access
_DB_POOL: asyncpg.Pool | None = None

# Global GLP client and dependencies for write operations
_GLP_CLIENT = None
_TOKEN_MANAGER = None
_DEVICE_MANAGER = None
_DEVICE_SYNCER = None
_SUBSCRIPTION_SYNCER = None

# Global repositories, adapters, and use cases for write operations
_DEVICE_REPO = None
_SUBSCRIPTION_REPO = None
_DEVICE_MANAGER_ADAPTER = None
_DEVICE_SYNCER_ADAPTER = None
_APPLY_ASSIGNMENTS_USE_CASE = None
_DEVICE_ACTIONS_USE_CASE = None

# Global rate limiters for write operations
_PATCH_RATE_LIMITER = None  # For PATCH operations (20/min limit)
_POST_RATE_LIMITER = None   # For POST operations (25/min limit)

# Global pending operations tracking (for confirmation workflows)
_PENDING_OPERATIONS: dict[str, dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize and cleanup database connection pool, GLP client, and use cases."""
    global _DB_POOL, _GLP_CLIENT, _TOKEN_MANAGER, _DEVICE_MANAGER
    global _DEVICE_SYNCER, _SUBSCRIPTION_SYNCER
    global _DEVICE_REPO, _SUBSCRIPTION_REPO
    global _DEVICE_MANAGER_ADAPTER, _DEVICE_SYNCER_ADAPTER
    global _APPLY_ASSIGNMENTS_USE_CASE, _DEVICE_ACTIONS_USE_CASE
    global _PATCH_RATE_LIMITER, _POST_RATE_LIMITER

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    # Pool configuration optimized for MCP server workloads
    pool = await asyncpg.create_pool(
        database_url,
        min_size=int(os.environ.get("DB_POOL_MIN", "2")),
        max_size=int(os.environ.get("DB_POOL_MAX", "10")),
        command_timeout=60,
        # Connection health and timeout settings
        max_inactive_connection_lifetime=300,  # Close idle connections after 5 min
    )
    _DB_POOL = pool  # Store globally for REST API access

    # Initialize GLP client for write operations (if assignment module is available)
    if ASSIGNMENT_MODULE_AVAILABLE:
        try:
            _TOKEN_MANAGER = TokenManager()
            _GLP_CLIENT = GLPClient(_TOKEN_MANAGER)
            await _GLP_CLIENT.__aenter__()
            _DEVICE_MANAGER = DeviceManager(_GLP_CLIENT)
            _DEVICE_SYNCER = DeviceSyncer(_GLP_CLIENT, pool)
            _SUBSCRIPTION_SYNCER = SubscriptionSyncer(_GLP_CLIENT, pool)

            logger.info("GLP client initialized successfully")

            # Initialize repositories
            _DEVICE_REPO = PostgresDeviceRepository(pool)
            _SUBSCRIPTION_REPO = PostgresSubscriptionRepository(pool)
            logger.info("Repositories initialized successfully")

            # Initialize adapters
            _DEVICE_MANAGER_ADAPTER = GLPDeviceManagerAdapter(_DEVICE_MANAGER)
            _DEVICE_SYNCER_ADAPTER = DeviceSyncerAdapter(_DEVICE_SYNCER)
            logger.info("Adapters initialized successfully")

            # Initialize use cases
            _APPLY_ASSIGNMENTS_USE_CASE = ApplyAssignmentsUseCase(
                device_repo=_DEVICE_REPO,
                subscription_repo=_SUBSCRIPTION_REPO,
                device_manager=_DEVICE_MANAGER_ADAPTER,
                device_syncer=_DEVICE_SYNCER_ADAPTER,
            )
            _DEVICE_ACTIONS_USE_CASE = DeviceActionsUseCase(
                device_manager=_DEVICE_MANAGER_ADAPTER,
            )
            logger.info("Use cases initialized successfully")

            # Initialize rate limiters for write operations
            # PATCH operations: 3.5s interval (for 20/min limits, yields ~17 req/min)
            # POST operations: 2.6s interval (for 25/min limits, yields ~23 req/min)
            _PATCH_RATE_LIMITER = SequentialRateLimiter(operation_type="patch")
            _POST_RATE_LIMITER = SequentialRateLimiter(operation_type="post")
            logger.info("Rate limiters initialized successfully")

        except Exception as e:
            logger.warning(f"Failed to initialize GLP client (write tools will not work): {e}")
    else:
        logger.warning("Assignment module not available - write tools disabled")

    try:
        yield {"db_pool": pool}
    finally:
        # Cleanup (reverse order of initialization)
        _PATCH_RATE_LIMITER = None
        _POST_RATE_LIMITER = None
        _APPLY_ASSIGNMENTS_USE_CASE = None
        _DEVICE_ACTIONS_USE_CASE = None
        _DEVICE_MANAGER_ADAPTER = None
        _DEVICE_SYNCER_ADAPTER = None
        _DEVICE_REPO = None
        _SUBSCRIPTION_REPO = None

        # Cleanup GLP client
        if _GLP_CLIENT:
            await _GLP_CLIENT.__aexit__(None, None, None)
        _DB_POOL = None
        _GLP_CLIENT = None
        _TOKEN_MANAGER = None
        _DEVICE_MANAGER = None
        _DEVICE_SYNCER = None
        _SUBSCRIPTION_SYNCER = None
        await pool.close()


# =============================================================================
# FastMCP Server
# =============================================================================

mcp = FastMCP(
    name="GreenLake Inventory",
    instructions=(
        "This server provides access to HPE GreenLake device and subscription inventory. "
        "Use the read-only tools to search devices, list subscriptions, and analyze inventory data. "
        "Use the write tools (add_devices, apply_device_assignments, archive_devices, unarchive_devices, update_device_tags) to add new devices, "
        "assign subscriptions/applications/tags to devices, archive devices, restore archived devices, and update device tags. "
        "Write operations require proper GreenLake API credentials."
    ),
    lifespan=lifespan,
)


# =============================================================================
# Health Check Endpoint (for HTTP transport)
# =============================================================================


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker/Kubernetes probes."""
    return JSONResponse({
        "status": "healthy",
        "service": "greenlake-mcp",
        "tools": 32,  # 27 read-only + 5 write (apply_device_assignments, add_devices, archive_devices, unarchive_devices, update_device_tags)
    })


# =============================================================================
# REST API Endpoints for Agent Chatbot
# =============================================================================


# Registry of all tools for REST API (populated dynamically from FastMCP)
_TOOL_REGISTRY: dict[str, dict] = {}
_TOOLS_INITIALIZED = False


def _init_tool_registry():
    """Initialize tool registry from FastMCP tools."""
    global _TOOLS_INITIALIZED
    if _TOOLS_INITIALIZED:
        return

    # Get tools from FastMCP's internal registry
    # FastMCP stores tools in _tool_manager._tools dict
    if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
        for name, tool in mcp._tool_manager._tools.items():
            # Convert annotations to dict if it's an object
            annotations = {"readOnlyHint": True}
            if hasattr(tool, "annotations") and tool.annotations:
                if hasattr(tool.annotations, "__dict__"):
                    annotations = {k: v for k, v in tool.annotations.__dict__.items() if not k.startswith("_")}
                elif isinstance(tool.annotations, dict):
                    annotations = tool.annotations

            _TOOL_REGISTRY[name] = {
                "name": name,
                "description": tool.description or "",
                "func": tool.fn,
                "inputSchema": tool.parameters if hasattr(tool, "parameters") else {},
                "annotations": annotations,
            }
    _TOOLS_INITIALIZED = True


@mcp.custom_route("/mcp/v1/tools/list", methods=["POST"])
async def rest_list_tools(request: Request) -> JSONResponse:
    """REST endpoint to list all available tools."""
    _init_tool_registry()
    tools = [
        {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
            "annotations": t["annotations"],
        }
        for t in _TOOL_REGISTRY.values()
    ]
    return JSONResponse({"tools": tools})


@mcp.custom_route("/mcp/v1/tools/call", methods=["POST"])
async def rest_call_tool(request: Request) -> JSONResponse:
    """REST endpoint to call a tool by name."""
    _init_tool_registry()
    try:
        body = await request.json()
        tool_name = body.get("name")
        arguments = body.get("arguments", {})

        if not tool_name:
            return JSONResponse({"error": "Tool name required"}, status_code=400)

        if tool_name not in _TOOL_REGISTRY:
            return JSONResponse({"error": f"Tool not found: {tool_name}"}, status_code=404)

        tool = _TOOL_REGISTRY[tool_name]
        func = tool["func"]

        # Use global database pool
        pool = _DB_POOL

        # Create a mock context for tools that need it
        class MockContext:
            def __init__(self, db_pool):
                self._pool = db_pool
                self.request_context = type("RC", (), {"lifespan_context": {"db_pool": db_pool}})()

        ctx = MockContext(pool) if pool else None

        # Call the tool function
        if "ctx" in func.__code__.co_varnames[:func.__code__.co_argcount]:
            result = await func(ctx=ctx, **arguments)
        else:
            result = await func(**arguments)

        # Format result as MCP content
        import json
        if isinstance(result, (dict, list)):
            text = json.dumps(result)
        else:
            text = str(result)

        return JSONResponse({
            "content": [{"type": "text", "text": text}]
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================================
# Helper Functions
# =============================================================================


def get_pool(ctx: Context) -> asyncpg.Pool:
    """Get the database pool from the lifespan context."""
    return ctx.request_context.lifespan_context["db_pool"]


def rows_to_dicts(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    """Convert asyncpg Records to list of dicts."""
    return [dict(row) for row in rows]


def validate_readonly_sql(sql: str) -> bool:
    """Validate that SQL is read-only (SELECT only)."""
    normalized = sql.strip().upper()
    # Remove comments
    normalized = re.sub(r"--.*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)
    normalized = normalized.strip()

    # Must start with SELECT or WITH (for CTEs)
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return False

    # Disallow dangerous keywords
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
    for keyword in dangerous:
        if re.search(rf"\b{keyword}\b", normalized):
            return False

    return True


# =============================================================================
# TOOLS: Read-Only Database Queries
# =============================================================================


@mcp.tool(annotations={"readOnlyHint": True})
async def search_devices(query: str, limit: int = 50, ctx: Context = None) -> list[dict]:
    """
    Full-text search across devices using PostgreSQL search vector.

    Args:
        query: Search terms (e.g., "aruba 6200", "serial number", model name)
        limit: Maximum number of results (default 50, max 200)

    Returns:
        List of matching devices with id, serial_number, device_name, device_type, model, region, and rank
    """
    limit = min(limit, 200)
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM search_devices($1, $2)",
            query,
            limit,
        )
    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_device_by_serial(serial_number: str, ctx: Context = None) -> dict | None:
    """
    Get a device by its serial number.

    Args:
        serial_number: The device serial number (e.g., "VNT9KWC01V")

    Returns:
        Device details or None if not found
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, serial_number, mac_address, device_type, model, region,
                   device_name, secondary_name, assigned_state, archived,
                   location_name, location_city, location_country,
                   created_at, updated_at
            FROM devices
            WHERE serial_number = $1
            """,
            serial_number,
        )
    return dict(row) if row else None


@mcp.tool(annotations={"readOnlyHint": True})
async def list_devices(
    device_type: str | None = None,
    region: str | None = None,
    assigned_state: str | None = None,
    archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    ctx: Context = None,
) -> list[dict]:
    """
    List devices with optional filters.

    Args:
        device_type: Filter by type (SWITCH, IAP, GATEWAY, AP)
        region: Filter by region (us-west, us-east, eu-central, etc.)
        assigned_state: Filter by assignment (ASSIGNED_TO_SERVICE, UNASSIGNED)
        archived: Include archived devices (default False)
        limit: Maximum results (default 50, max 200)
        offset: Pagination offset

    Returns:
        List of devices matching the filters
    """
    limit = min(limit, 200)
    pool = get_pool(ctx)

    conditions = ["archived = $1"]
    params: list[Any] = [archived]
    param_idx = 2

    if device_type:
        conditions.append(f"device_type = ${param_idx}")
        params.append(device_type)
        param_idx += 1

    if region:
        conditions.append(f"region = ${param_idx}")
        params.append(region)
        param_idx += 1

    if assigned_state:
        conditions.append(f"assigned_state = ${param_idx}")
        params.append(assigned_state)
        param_idx += 1

    params.extend([limit, offset])

    query = f"""
        SELECT id, serial_number, mac_address, device_type, model, region,
               device_name, assigned_state, updated_at
        FROM devices
        WHERE {" AND ".join(conditions)}
        ORDER BY updated_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_device_subscriptions(serial_number: str, ctx: Context = None) -> dict:
    """
    Get all subscriptions linked to a device.

    Args:
        serial_number: The device serial number

    Returns:
        Device info with list of linked subscriptions
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        # Get device
        device = await conn.fetchrow(
            "SELECT id, serial_number, device_type, model FROM devices WHERE serial_number = $1",
            serial_number,
        )
        if not device:
            return {"error": f"Device not found: {serial_number}"}

        # Get subscriptions via join table
        subs = await conn.fetch(
            """
            SELECT s.id, s.key, s.subscription_type, s.subscription_status,
                   s.quantity, s.available_quantity, s.start_time, s.end_time, s.tier
            FROM subscriptions s
            JOIN device_subscriptions ds ON s.id = ds.subscription_id
            WHERE ds.device_id = $1
            """,
            device["id"],
        )

    return {
        "device": dict(device),
        "subscriptions": rows_to_dicts(subs),
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def search_subscriptions(query: str, limit: int = 50, ctx: Context = None) -> list[dict]:
    """
    Full-text search across subscriptions.

    Args:
        query: Search terms (key, SKU, tier, contract number)
        limit: Maximum results (default 50, max 200)

    Returns:
        List of matching subscriptions
    """
    limit = min(limit, 200)
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, key, subscription_type, subscription_status,
                   quantity, available_quantity, sku, tier,
                   start_time, end_time,
                   ts_rank(search_vector, websearch_to_tsquery('english', $1)) as rank
            FROM subscriptions
            WHERE search_vector @@ websearch_to_tsquery('english', $1)
            ORDER BY rank DESC
            LIMIT $2
            """,
            query,
            limit,
        )
    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_subscription_by_key(key: str, ctx: Context = None) -> dict | None:
    """
    Get a subscription by its key.

    Args:
        key: The subscription key (e.g., "PAT4DYYJAEEEJA")

    Returns:
        Subscription details or None if not found
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, key, subscription_type, subscription_status,
                   quantity, available_quantity, sku, sku_description,
                   tier, tier_description, product_type, is_eval,
                   contract, quote, po, start_time, end_time,
                   created_at, updated_at
            FROM subscriptions
            WHERE key = $1
            """,
            key,
        )
    return dict(row) if row else None


@mcp.tool(annotations={"readOnlyHint": True})
async def list_expiring_subscriptions(days: int = 90, limit: int = 50, ctx: Context = None) -> list[dict]:
    """
    List subscriptions expiring within a specified number of days.

    Args:
        days: Number of days to look ahead (default 90)
        limit: Maximum results (default 50, max 200)

    Returns:
        List of expiring subscriptions sorted by expiration date
    """
    limit = min(limit, 200)
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, key, subscription_type, tier, sku,
                   quantity, available_quantity, end_time,
                   (end_time - NOW()) as time_remaining,
                   DATE_PART('day', end_time - NOW()) as days_remaining
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND end_time > NOW()
              AND end_time < NOW() + ($1 || ' days')::interval
            ORDER BY end_time ASC
            LIMIT $2
            """,
            str(days),
            limit,
        )
    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_device_summary(ctx: Context = None) -> list[dict]:
    """
    Get device counts grouped by type and region.

    Returns:
        Summary with total, assigned, unassigned, and archived counts
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM device_summary")
    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_subscription_summary(ctx: Context = None) -> list[dict]:
    """
    Get subscription counts grouped by type and status.

    Returns:
        Summary with total count and quantities by type/status
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM subscription_summary")
    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def run_query(sql: str, ctx: Context = None) -> list[dict]:
    """
    Execute a read-only SQL query against the database.

    Only SELECT queries are allowed. Dangerous operations (INSERT, UPDATE, DELETE, etc.)
    are blocked for security.

    Args:
        sql: A SELECT query to execute

    Returns:
        Query results as a list of dictionaries
    """
    if not validate_readonly_sql(sql):
        return [{"error": "Only SELECT queries are allowed. Dangerous operations are blocked."}]

    pool = get_pool(ctx)

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return rows_to_dicts(rows)
    except Exception as e:
        return [{"error": str(e)}]


# =============================================================================
# DEVICE ANALYTICS TOOLS
# =============================================================================


@mcp.tool(annotations={"readOnlyHint": True})
async def get_devices_by_location(
    country: str | None = None,
    city: str | None = None,
    limit: int = 100,
    ctx: Context = None,
) -> dict:
    """
    Get device counts and details grouped by location.

    Args:
        country: Filter by country name (optional)
        city: Filter by city name (optional)
        limit: Maximum devices to return per location (default 100)

    Returns:
        Location breakdown with device counts and sample devices
    """
    pool = get_pool(ctx)
    limit = min(limit, 500)

    async with pool.acquire() as conn:
        # Get location summary
        if country and city:
            summary = await conn.fetch(
                """
                SELECT location_country, location_city, device_type, COUNT(*) as count
                FROM devices
                WHERE NOT archived AND location_country = $1 AND location_city = $2
                GROUP BY location_country, location_city, device_type
                ORDER BY count DESC
                """,
                country,
                city,
            )
            devices = await conn.fetch(
                """
                SELECT serial_number, device_type, model, device_name, location_name
                FROM devices
                WHERE NOT archived AND location_country = $1 AND location_city = $2
                ORDER BY updated_at DESC LIMIT $3
                """,
                country,
                city,
                limit,
            )
        elif country:
            summary = await conn.fetch(
                """
                SELECT location_country, location_city, device_type, COUNT(*) as count
                FROM devices
                WHERE NOT archived AND location_country = $1
                GROUP BY location_country, location_city, device_type
                ORDER BY location_city, count DESC
                """,
                country,
            )
            devices = await conn.fetch(
                """
                SELECT serial_number, device_type, model, location_city, location_name
                FROM devices
                WHERE NOT archived AND location_country = $1
                ORDER BY location_city, updated_at DESC LIMIT $2
                """,
                country,
                limit,
            )
        else:
            summary = await conn.fetch(
                """
                SELECT location_country, COUNT(*) as count,
                       COUNT(DISTINCT location_city) as cities
                FROM devices
                WHERE NOT archived AND location_country IS NOT NULL
                GROUP BY location_country
                ORDER BY count DESC
                """
            )
            devices = []

    return {
        "summary": rows_to_dicts(summary),
        "devices": rows_to_dicts(devices) if devices else [],
        "total_locations": len(summary),
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_device_age_analysis(ctx: Context = None) -> dict:
    """
    Analyze device inventory by age (based on created_at timestamp).

    Returns:
        Age distribution with device counts by age bracket
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        # Age distribution
        age_dist = await conn.fetch(
            """
            SELECT
                CASE
                    WHEN created_at > NOW() - INTERVAL '30 days' THEN '< 30 days'
                    WHEN created_at > NOW() - INTERVAL '90 days' THEN '30-90 days'
                    WHEN created_at > NOW() - INTERVAL '180 days' THEN '90-180 days'
                    WHEN created_at > NOW() - INTERVAL '1 year' THEN '6-12 months'
                    WHEN created_at > NOW() - INTERVAL '2 years' THEN '1-2 years'
                    ELSE '> 2 years'
                END as age_bracket,
                COUNT(*) as count,
                device_type
            FROM devices
            WHERE NOT archived AND created_at IS NOT NULL
            GROUP BY age_bracket, device_type
            ORDER BY
                CASE age_bracket
                    WHEN '< 30 days' THEN 1
                    WHEN '30-90 days' THEN 2
                    WHEN '90-180 days' THEN 3
                    WHEN '6-12 months' THEN 4
                    WHEN '1-2 years' THEN 5
                    ELSE 6
                END
            """
        )

        # Oldest and newest devices
        oldest = await conn.fetch(
            """
            SELECT serial_number, device_type, model, created_at,
                   DATE_PART('day', NOW() - created_at) as age_days
            FROM devices
            WHERE NOT archived AND created_at IS NOT NULL
            ORDER BY created_at ASC LIMIT 5
            """
        )

        newest = await conn.fetch(
            """
            SELECT serial_number, device_type, model, created_at,
                   DATE_PART('day', NOW() - created_at) as age_days
            FROM devices
            WHERE NOT archived AND created_at IS NOT NULL
            ORDER BY created_at DESC LIMIT 5
            """
        )

    return {
        "age_distribution": rows_to_dicts(age_dist),
        "oldest_devices": rows_to_dicts(oldest),
        "newest_devices": rows_to_dicts(newest),
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_model_distribution(
    device_type: str | None = None, ctx: Context = None
) -> list[dict]:
    """
    Get device counts by model, optionally filtered by device type.

    Args:
        device_type: Filter by type (SWITCH, IAP, GATEWAY, AP) - optional

    Returns:
        Model distribution with counts and percentages
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        if device_type:
            rows = await conn.fetch(
                """
                WITH model_counts AS (
                    SELECT model, device_type, COUNT(*) as count
                    FROM devices
                    WHERE NOT archived AND device_type = $1
                    GROUP BY model, device_type
                ),
                total AS (
                    SELECT SUM(count) as total FROM model_counts
                )
                SELECT mc.model, mc.device_type, mc.count,
                       ROUND(mc.count * 100.0 / t.total, 2) as percentage
                FROM model_counts mc, total t
                ORDER BY mc.count DESC
                """,
                device_type,
            )
        else:
            rows = await conn.fetch(
                """
                WITH model_counts AS (
                    SELECT model, device_type, COUNT(*) as count
                    FROM devices
                    WHERE NOT archived
                    GROUP BY model, device_type
                ),
                total AS (
                    SELECT SUM(count) as total FROM model_counts
                )
                SELECT mc.model, mc.device_type, mc.count,
                       ROUND(mc.count * 100.0 / t.total, 2) as percentage
                FROM model_counts mc, total t
                ORDER BY mc.count DESC
                """
            )

    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_unassigned_devices(
    device_type: str | None = None, region: str | None = None, limit: int = 100, ctx: Context = None
) -> dict:
    """
    Get devices that are not assigned to any service.

    Args:
        device_type: Filter by type (optional)
        region: Filter by region (optional)
        limit: Maximum results (default 100)

    Returns:
        Unassigned devices with summary counts
    """
    pool = get_pool(ctx)
    limit = min(limit, 500)

    conditions = ["NOT archived", "assigned_state = 'UNASSIGNED'"]
    params: list[Any] = []
    param_idx = 1

    if device_type:
        conditions.append(f"device_type = ${param_idx}")
        params.append(device_type)
        param_idx += 1

    if region:
        conditions.append(f"region = ${param_idx}")
        params.append(region)
        param_idx += 1

    params.append(limit)

    async with pool.acquire() as conn:
        # Get unassigned devices
        devices = await conn.fetch(
            f"""
            SELECT serial_number, device_type, model, region, device_name, created_at
            FROM devices
            WHERE {" AND ".join(conditions)}
            ORDER BY created_at DESC
            LIMIT ${param_idx}
            """,
            *params,
        )

        # Get summary
        summary = await conn.fetch(
            """
            SELECT device_type, region, COUNT(*) as count
            FROM devices
            WHERE NOT archived AND assigned_state = 'UNASSIGNED'
            GROUP BY device_type, region
            ORDER BY count DESC
            """
        )

    return {
        "devices": rows_to_dicts(devices),
        "summary": rows_to_dicts(summary),
        "total_unassigned": sum(r["count"] for r in summary),
    }


# =============================================================================
# SUBSCRIPTION INSIGHTS TOOLS
# =============================================================================


@mcp.tool(annotations={"readOnlyHint": True})
async def get_license_utilization(ctx: Context = None) -> dict:
    """
    Analyze subscription license utilization across all active subscriptions.

    Returns:
        Utilization breakdown by subscription type with total, used, available, and percentage
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        # Overall utilization by type
        by_type = await conn.fetch(
            """
            SELECT
                subscription_type,
                COUNT(*) as subscription_count,
                SUM(quantity) as total_licenses,
                SUM(quantity - available_quantity) as used_licenses,
                SUM(available_quantity) as available_licenses,
                ROUND(
                    CASE WHEN SUM(quantity) > 0
                         THEN (SUM(quantity) - SUM(available_quantity)) * 100.0 / SUM(quantity)
                         ELSE 0
                    END, 2
                ) as utilization_pct
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
            GROUP BY subscription_type
            ORDER BY total_licenses DESC
            """
        )

        # Overall totals
        totals = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total_subscriptions,
                SUM(quantity) as total_licenses,
                SUM(quantity - available_quantity) as used_licenses,
                SUM(available_quantity) as available_licenses,
                ROUND(
                    CASE WHEN SUM(quantity) > 0
                         THEN (SUM(quantity) - SUM(available_quantity)) * 100.0 / SUM(quantity)
                         ELSE 0
                    END, 2
                ) as overall_utilization_pct
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
            """
        )

        # Subscriptions with low utilization (< 50%)
        low_util = await conn.fetch(
            """
            SELECT key, subscription_type, tier, quantity, available_quantity,
                   ROUND((quantity - available_quantity) * 100.0 / NULLIF(quantity, 0), 2) as utilization_pct
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND quantity > 0
              AND (quantity - available_quantity) * 100.0 / quantity < 50
            ORDER BY utilization_pct ASC
            LIMIT 20
            """
        )

        # Fully utilized subscriptions (0 available)
        full_util = await conn.fetch(
            """
            SELECT key, subscription_type, tier, quantity, end_time
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND available_quantity = 0
            ORDER BY end_time ASC
            LIMIT 20
            """
        )

    return {
        "by_type": rows_to_dicts(by_type),
        "totals": dict(totals) if totals else {},
        "low_utilization": rows_to_dicts(low_util),
        "fully_utilized": rows_to_dicts(full_util),
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_subscription_timeline(
    months_ahead: int = 12, ctx: Context = None
) -> list[dict]:
    """
    Get subscription expiration timeline for planning renewals.

    Args:
        months_ahead: Number of months to look ahead (default 12, max 36)

    Returns:
        Monthly breakdown of expiring subscriptions with counts and license quantities
    """
    pool = get_pool(ctx)
    months_ahead = min(months_ahead, 36)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                DATE_TRUNC('month', end_time) as month,
                subscription_type,
                COUNT(*) as expiring_count,
                SUM(quantity) as expiring_licenses
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND end_time > NOW()
              AND end_time < NOW() + ($1 || ' months')::interval
            GROUP BY DATE_TRUNC('month', end_time), subscription_type
            ORDER BY month, subscription_type
            """,
            str(months_ahead),
        )

    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_subscription_by_tier(tier: str | None = None, ctx: Context = None) -> dict:
    """
    Get subscription statistics grouped by tier level.

    Args:
        tier: Filter by specific tier (optional, e.g., "FOUNDATION_AP", "FOUNDATION_SWITCH_6200")

    Returns:
        Tier-level summary with subscription counts and license totals
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        if tier:
            rows = await conn.fetch(
                """
                SELECT
                    tier, tier_description, subscription_type,
                    COUNT(*) as count,
                    SUM(quantity) as total_licenses,
                    SUM(available_quantity) as available_licenses,
                    MIN(end_time) as earliest_expiry,
                    MAX(end_time) as latest_expiry
                FROM subscriptions
                WHERE subscription_status = 'STARTED' AND tier = $1
                GROUP BY tier, tier_description, subscription_type
                ORDER BY count DESC
                """,
                tier,
            )
            details = await conn.fetch(
                """
                SELECT key, sku, quantity, available_quantity, end_time
                FROM subscriptions
                WHERE subscription_status = 'STARTED' AND tier = $1
                ORDER BY end_time ASC
                LIMIT 50
                """,
                tier,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    tier, tier_description,
                    COUNT(*) as count,
                    SUM(quantity) as total_licenses,
                    SUM(available_quantity) as available_licenses
                FROM subscriptions
                WHERE subscription_status = 'STARTED'
                GROUP BY tier, tier_description
                ORDER BY count DESC
                """
            )
            details = []

    return {
        "summary": rows_to_dicts(rows),
        "details": rows_to_dicts(details) if details else [],
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_eval_subscriptions(ctx: Context = None) -> dict:
    """
    Get all evaluation/trial subscriptions.

    Returns:
        List of eval subscriptions with expiration info
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        active = await conn.fetch(
            """
            SELECT key, subscription_type, tier, quantity, available_quantity,
                   start_time, end_time,
                   DATE_PART('day', end_time - NOW()) as days_remaining
            FROM subscriptions
            WHERE is_eval = true AND subscription_status = 'STARTED'
            ORDER BY end_time ASC
            """
        )

        expired = await conn.fetch(
            """
            SELECT key, subscription_type, tier, quantity, end_time
            FROM subscriptions
            WHERE is_eval = true AND subscription_status != 'STARTED'
            ORDER BY end_time DESC
            LIMIT 20
            """
        )

        summary = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE subscription_status = 'STARTED') as active_evals,
                COUNT(*) FILTER (WHERE subscription_status != 'STARTED') as ended_evals,
                SUM(quantity) FILTER (WHERE subscription_status = 'STARTED') as active_licenses
            FROM subscriptions
            WHERE is_eval = true
            """
        )

    return {
        "active_evals": rows_to_dicts(active),
        "expired_evals": rows_to_dicts(expired),
        "summary": dict(summary) if summary else {},
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_renewal_forecast(days: int = 90, ctx: Context = None) -> dict:
    """
    Get a renewal forecast showing subscriptions expiring in the specified window.

    Args:
        days: Number of days to look ahead (default 90)

    Returns:
        Expiring subscriptions grouped by urgency (critical, soon, upcoming)
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        # Critical: expires within 30 days
        critical = await conn.fetch(
            """
            SELECT key, subscription_type, tier, quantity, available_quantity,
                   end_time, DATE_PART('day', end_time - NOW()) as days_remaining
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND end_time > NOW()
              AND end_time < NOW() + INTERVAL '30 days'
            ORDER BY end_time ASC
            """
        )

        # Soon: 30-60 days
        soon = await conn.fetch(
            """
            SELECT key, subscription_type, tier, quantity, available_quantity,
                   end_time, DATE_PART('day', end_time - NOW()) as days_remaining
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND end_time >= NOW() + INTERVAL '30 days'
              AND end_time < NOW() + INTERVAL '60 days'
            ORDER BY end_time ASC
            """
        )

        # Upcoming: 60+ days but within window
        upcoming = await conn.fetch(
            f"""
            SELECT key, subscription_type, tier, quantity, available_quantity,
                   end_time, DATE_PART('day', end_time - NOW()) as days_remaining
            FROM subscriptions
            WHERE subscription_status = 'STARTED'
              AND end_time >= NOW() + INTERVAL '60 days'
              AND end_time < NOW() + ('{days} days')::interval
            ORDER BY end_time ASC
            """
        )

    return {
        "critical": {"count": len(critical), "items": rows_to_dicts(critical)},
        "soon": {"count": len(soon), "items": rows_to_dicts(soon)},
        "upcoming": {"count": len(upcoming), "items": rows_to_dicts(upcoming)},
        "total_expiring": len(critical) + len(soon) + len(upcoming),
    }


# =============================================================================
# TAG MANAGEMENT TOOLS
# =============================================================================


@mcp.tool(annotations={"readOnlyHint": True})
async def get_devices_by_tag(
    tag_key: str, tag_value: str | None = None, limit: int = 100, ctx: Context = None
) -> dict:
    """
    Find devices by tag key and optional value.

    Args:
        tag_key: The tag key to search for
        tag_value: Optional tag value to match
        limit: Maximum results (default 100)

    Returns:
        Matching devices with tag information
    """
    pool = get_pool(ctx)
    limit = min(limit, 500)

    async with pool.acquire() as conn:
        if tag_value:
            devices = await conn.fetch(
                """
                SELECT d.serial_number, d.device_type, d.model, d.region,
                       dt.tag_key, dt.tag_value
                FROM devices d
                JOIN device_tags dt ON d.id = dt.device_id
                WHERE NOT d.archived AND dt.tag_key = $1 AND dt.tag_value = $2
                ORDER BY d.updated_at DESC
                LIMIT $3
                """,
                tag_key,
                tag_value,
                limit,
            )
        else:
            devices = await conn.fetch(
                """
                SELECT d.serial_number, d.device_type, d.model, d.region,
                       dt.tag_key, dt.tag_value
                FROM devices d
                JOIN device_tags dt ON d.id = dt.device_id
                WHERE NOT d.archived AND dt.tag_key = $1
                ORDER BY dt.tag_value, d.updated_at DESC
                LIMIT $2
                """,
                tag_key,
                limit,
            )

        # Get value distribution for this key
        value_dist = await conn.fetch(
            """
            SELECT tag_value, COUNT(*) as count
            FROM device_tags
            WHERE tag_key = $1
            GROUP BY tag_value
            ORDER BY count DESC
            """,
            tag_key,
        )

    return {
        "devices": rows_to_dicts(devices),
        "value_distribution": rows_to_dicts(value_dist),
        "total_matches": len(devices),
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_tag_statistics(ctx: Context = None) -> dict:
    """
    Get statistics on device and subscription tags.

    Returns:
        Tag usage statistics for devices and subscriptions
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        # Device tag stats
        device_tags = await conn.fetch(
            """
            SELECT tag_key, COUNT(DISTINCT tag_value) as unique_values,
                   COUNT(*) as device_count
            FROM device_tags
            GROUP BY tag_key
            ORDER BY device_count DESC
            """
        )

        # Subscription tag stats
        sub_tags = await conn.fetch(
            """
            SELECT tag_key, COUNT(DISTINCT tag_value) as unique_values,
                   COUNT(*) as subscription_count
            FROM subscription_tags
            GROUP BY tag_key
            ORDER BY subscription_count DESC
            """
        )

        # Totals
        device_total = await conn.fetchrow(
            "SELECT COUNT(DISTINCT device_id) as tagged_devices FROM device_tags"
        )
        sub_total = await conn.fetchrow(
            "SELECT COUNT(DISTINCT subscription_id) as tagged_subs FROM subscription_tags"
        )

    return {
        "device_tags": rows_to_dicts(device_tags),
        "subscription_tags": rows_to_dicts(sub_tags),
        "tagged_device_count": device_total["tagged_devices"] if device_total else 0,
        "tagged_subscription_count": sub_total["tagged_subs"] if sub_total else 0,
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_subscriptions_by_tag(
    tag_key: str, tag_value: str | None = None, limit: int = 100, ctx: Context = None
) -> dict:
    """
    Find subscriptions by tag key and optional value.

    Args:
        tag_key: The tag key to search for
        tag_value: Optional tag value to match
        limit: Maximum results (default 100)

    Returns:
        Matching subscriptions with tag information
    """
    pool = get_pool(ctx)
    limit = min(limit, 500)

    async with pool.acquire() as conn:
        if tag_value:
            subs = await conn.fetch(
                """
                SELECT s.key, s.subscription_type, s.tier, s.quantity,
                       s.available_quantity, s.end_time, st.tag_key, st.tag_value
                FROM subscriptions s
                JOIN subscription_tags st ON s.id = st.subscription_id
                WHERE s.subscription_status = 'STARTED'
                  AND st.tag_key = $1 AND st.tag_value = $2
                ORDER BY s.end_time ASC
                LIMIT $3
                """,
                tag_key,
                tag_value,
                limit,
            )
        else:
            subs = await conn.fetch(
                """
                SELECT s.key, s.subscription_type, s.tier, s.quantity,
                       s.available_quantity, s.end_time, st.tag_key, st.tag_value
                FROM subscriptions s
                JOIN subscription_tags st ON s.id = st.subscription_id
                WHERE s.subscription_status = 'STARTED' AND st.tag_key = $1
                ORDER BY st.tag_value, s.end_time ASC
                LIMIT $2
                """,
                tag_key,
                limit,
            )

        # Get value distribution
        value_dist = await conn.fetch(
            """
            SELECT tag_value, COUNT(*) as count
            FROM subscription_tags
            WHERE tag_key = $1
            GROUP BY tag_value
            ORDER BY count DESC
            """,
            tag_key,
        )

    return {
        "subscriptions": rows_to_dicts(subs),
        "value_distribution": rows_to_dicts(value_dist),
        "total_matches": len(subs),
    }


# =============================================================================
# SYNC & HISTORY TOOLS
# =============================================================================


@mcp.tool(annotations={"readOnlyHint": True})
async def get_sync_status(ctx: Context = None) -> dict:
    """
    Get the current sync status and last sync information.

    Returns:
        Last sync times, status, and sync health information
    """
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        # Latest sync per resource type
        latest = await conn.fetch(
            """
            SELECT DISTINCT ON (resource_type)
                resource_type, status, started_at, completed_at, duration_ms,
                records_fetched, records_inserted, records_updated, records_errors
            FROM sync_history
            ORDER BY resource_type, started_at DESC
            """
        )

        # Check for any running syncs
        running = await conn.fetch(
            """
            SELECT resource_type, started_at,
                   EXTRACT(EPOCH FROM (NOW() - started_at)) as running_seconds
            FROM sync_history
            WHERE status = 'running'
            """
        )

        # Check data freshness
        devices_freshness = await conn.fetchrow(
            "SELECT MAX(synced_at) as last_sync, COUNT(*) as total FROM devices"
        )
        subs_freshness = await conn.fetchrow(
            "SELECT MAX(synced_at) as last_sync, COUNT(*) as total FROM subscriptions"
        )

    return {
        "latest_syncs": rows_to_dicts(latest),
        "running_syncs": rows_to_dicts(running),
        "devices": {
            "last_sync": devices_freshness["last_sync"] if devices_freshness else None,
            "total_records": devices_freshness["total"] if devices_freshness else 0,
        },
        "subscriptions": {
            "last_sync": subs_freshness["last_sync"] if subs_freshness else None,
            "total_records": subs_freshness["total"] if subs_freshness else 0,
        },
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_sync_history(
    resource_type: str | None = None, limit: int = 20, ctx: Context = None
) -> list[dict]:
    """
    Get historical sync operations.

    Args:
        resource_type: Filter by type (devices, subscriptions, all) - optional
        limit: Maximum records (default 20, max 100)

    Returns:
        List of sync operations with timing and record counts
    """
    pool = get_pool(ctx)
    limit = min(limit, 100)

    async with pool.acquire() as conn:
        if resource_type:
            rows = await conn.fetch(
                """
                SELECT id, resource_type, status, started_at, completed_at, duration_ms,
                       records_fetched, records_inserted, records_updated, records_errors,
                       error_message
                FROM sync_history
                WHERE resource_type = $1
                ORDER BY started_at DESC
                LIMIT $2
                """,
                resource_type,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, resource_type, status, started_at, completed_at, duration_ms,
                       records_fetched, records_inserted, records_updated, records_errors,
                       error_message
                FROM sync_history
                ORDER BY started_at DESC
                LIMIT $1
                """,
                limit,
            )

    return rows_to_dicts(rows)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_sync_metrics(days: int = 7, ctx: Context = None) -> dict:
    """
    Get sync performance metrics over a time period.

    Args:
        days: Number of days to analyze (default 7, max 90)

    Returns:
        Sync metrics including success rate, average duration, and trends
    """
    pool = get_pool(ctx)
    days = min(days, 90)

    async with pool.acquire() as conn:
        # Overall stats
        overall = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total_syncs,
                COUNT(*) FILTER (WHERE status = 'completed') as successful,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                ROUND(AVG(duration_ms) FILTER (WHERE status = 'completed'), 0) as avg_duration_ms,
                ROUND(AVG(records_fetched) FILTER (WHERE status = 'completed'), 0) as avg_records
            FROM sync_history
            WHERE started_at > NOW() - ($1 || ' days')::interval
            """,
            str(days),
        )

        # Daily breakdown
        daily = await conn.fetch(
            """
            SELECT
                DATE(started_at) as date,
                resource_type,
                COUNT(*) as sync_count,
                COUNT(*) FILTER (WHERE status = 'completed') as successful,
                ROUND(AVG(duration_ms) FILTER (WHERE status = 'completed'), 0) as avg_duration_ms
            FROM sync_history
            WHERE started_at > NOW() - ($1 || ' days')::interval
            GROUP BY DATE(started_at), resource_type
            ORDER BY date DESC, resource_type
            """,
            str(days),
        )

        # Recent errors
        errors = await conn.fetch(
            """
            SELECT started_at, resource_type, error_message
            FROM sync_history
            WHERE status = 'failed'
              AND started_at > NOW() - ($1 || ' days')::interval
            ORDER BY started_at DESC
            LIMIT 10
            """,
            str(days),
        )

    success_rate = 0
    if overall and overall["total_syncs"]:
        success_rate = round(overall["successful"] * 100.0 / overall["total_syncs"], 2)

    return {
        "period_days": days,
        "overall": dict(overall) if overall else {},
        "success_rate_pct": success_rate,
        "daily_breakdown": rows_to_dicts(daily),
        "recent_errors": rows_to_dicts(errors),
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def get_recently_updated(
    resource: str = "devices", hours: int = 24, limit: int = 50, ctx: Context = None
) -> list[dict]:
    """
    Get records that were recently updated or synced.

    Args:
        resource: Either "devices" or "subscriptions"
        hours: Look back period in hours (default 24, max 168)
        limit: Maximum results (default 50)

    Returns:
        Recently updated records with timestamps
    """
    pool = get_pool(ctx)
    hours = min(hours, 168)
    limit = min(limit, 200)

    async with pool.acquire() as conn:
        if resource == "subscriptions":
            rows = await conn.fetch(
                """
                SELECT key, subscription_type, tier, subscription_status,
                       updated_at, synced_at
                FROM subscriptions
                WHERE synced_at > NOW() - ($1 || ' hours')::interval
                ORDER BY synced_at DESC
                LIMIT $2
                """,
                str(hours),
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT serial_number, device_type, model, region, assigned_state,
                       updated_at, synced_at
                FROM devices
                WHERE synced_at > NOW() - ($1 || ' hours')::interval
                ORDER BY synced_at DESC
                LIMIT $2
                """,
                str(hours),
                limit,
            )

    return rows_to_dicts(rows)


# =============================================================================
# RESOURCES: Static Data Access
# =============================================================================


@mcp.resource("schema://devices", description="Devices table schema with column descriptions")
async def get_devices_schema(ctx: Context = None) -> str:
    """Returns the devices table schema information."""
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable,
                   col_description('devices'::regclass, ordinal_position) as description
            FROM information_schema.columns
            WHERE table_name = 'devices' AND table_schema = 'public'
            ORDER BY ordinal_position
            """
        )

    schema_info = "# Devices Table Schema\n\n"
    schema_info += "| Column | Type | Nullable | Description |\n"
    schema_info += "|--------|------|----------|-------------|\n"

    for row in rows:
        desc = row["description"] or ""
        schema_info += f"| {row['column_name']} | {row['data_type']} | {row['is_nullable']} | {desc} |\n"

    return schema_info


@mcp.resource("schema://subscriptions", description="Subscriptions table schema with column descriptions")
async def get_subscriptions_schema(ctx: Context = None) -> str:
    """Returns the subscriptions table schema information."""
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable,
                   col_description('subscriptions'::regclass, ordinal_position) as description
            FROM information_schema.columns
            WHERE table_name = 'subscriptions' AND table_schema = 'public'
            ORDER BY ordinal_position
            """
        )

    schema_info = "# Subscriptions Table Schema\n\n"
    schema_info += "| Column | Type | Nullable | Description |\n"
    schema_info += "|--------|------|----------|-------------|\n"

    for row in rows:
        desc = row["description"] or ""
        schema_info += f"| {row['column_name']} | {row['data_type']} | {row['is_nullable']} | {desc} |\n"

    return schema_info


@mcp.resource("schema://views", description="Available database views documentation")
async def get_views_schema(ctx: Context = None) -> str:
    """Returns documentation for available database views."""
    views_doc = """# Available Database Views

## active_devices
Non-archived devices with subscriptions and tags columns.
```sql
SELECT * FROM active_devices LIMIT 10;
```

## active_subscriptions
Subscriptions with status 'STARTED' (currently active).
```sql
SELECT * FROM active_subscriptions LIMIT 10;
```

## devices_expiring_soon
Devices with subscriptions expiring in the next 90 days.
```sql
SELECT * FROM devices_expiring_soon;
```

## subscriptions_expiring_soon
Subscriptions expiring in the next 90 days with days_remaining.
```sql
SELECT * FROM subscriptions_expiring_soon;
```

## devices_with_subscriptions
Devices joined with full subscription details.
```sql
SELECT * FROM devices_with_subscriptions WHERE serial_number = 'YOUR_SERIAL';
```

## device_summary
Device counts by type and region.
```sql
SELECT * FROM device_summary;
```

## subscription_summary
Subscription counts by type and status.
```sql
SELECT * FROM subscription_summary;
```
"""
    return views_doc


@mcp.resource("data://valid-values", description="Valid categorical values for filtering")
async def get_valid_values(ctx: Context = None) -> str:
    """Returns valid values for categorical columns."""
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM valid_column_values ORDER BY table_name, column_name, occurrence_count DESC")

    result = "# Valid Column Values\n\n"
    current_table = ""
    current_column = ""

    for row in rows:
        if row["table_name"] != current_table:
            current_table = row["table_name"]
            result += f"\n## {current_table}\n"
            current_column = ""

        if row["column_name"] != current_column:
            current_column = row["column_name"]
            result += f"\n### {current_column}\n"

        result += f"- `{row['valid_value']}` ({row['occurrence_count']} records)\n"

    return result


@mcp.resource("data://query-examples", description="Example SQL queries for common operations")
async def get_query_examples(ctx: Context = None) -> str:
    """Returns example SQL queries from the database."""
    pool = get_pool(ctx)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT category, description, sql_query FROM query_examples ORDER BY category, id"
        )

    result = "# Example SQL Queries\n\n"
    current_category = ""

    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            result += f"\n## {current_category.title()}\n\n"

        result += f"### {row['description']}\n"
        result += f"```sql\n{row['sql_query']}\n```\n\n"

    return result


# =============================================================================
# PROMPTS: Reusable Message Templates
# =============================================================================


@mcp.prompt
def analyze_device(serial_number: str) -> str:
    """
    Generate a prompt for analyzing a specific device.

    Args:
        serial_number: The device serial number to analyze
    """
    return f"""Please analyze the device with serial number: {serial_number}

Use the following tools to gather information:
1. get_device_by_serial - Get basic device information
2. get_device_subscriptions - Get subscription details
3. search_devices - Search for related devices if needed

Provide a summary including:
- Device type, model, and location
- Subscription status and expiration dates
- Any potential issues or recommendations"""


@mcp.prompt
def analyze_expiring(days: int = 90) -> str:
    """
    Generate a prompt for subscription renewal analysis.

    Args:
        days: Number of days to look ahead for expiring subscriptions
    """
    return f"""Please analyze subscriptions expiring within the next {days} days.

Use the following tools:
1. list_expiring_subscriptions(days={days}) - Get list of expiring subscriptions
2. get_subscription_summary - Get overall subscription status
3. get_device_subscriptions - Check affected devices if needed

Provide a report including:
- Total count of expiring subscriptions
- Breakdown by subscription type and tier
- Devices that will be affected
- Renewal priority recommendations"""


@mcp.prompt
def device_report(device_type: str) -> str:
    """
    Generate a prompt for device inventory report.

    Args:
        device_type: The device type to report on (SWITCH, IAP, GATEWAY, AP)
    """
    return f"""Please generate an inventory report for device type: {device_type}

Use the following tools:
1. list_devices(device_type="{device_type}") - Get all devices of this type
2. get_device_summary - Get summary statistics
3. run_query - Execute custom queries if needed

Include in the report:
- Total count and regional distribution
- Assignment status breakdown
- Subscription coverage
- Any anomalies or issues"""


@mcp.prompt
def subscription_utilization() -> str:
    """Generate a prompt for license utilization analysis."""
    return """Please analyze subscription license utilization.

Use the following tools:
1. get_subscription_summary - Get subscription statistics
2. run_query - Execute queries for utilization calculations
3. list_expiring_subscriptions - Check upcoming renewals

Calculate and report:
- Total licenses vs. available licenses by type
- Utilization percentage by subscription type
- Over/under-provisioned subscription types
- Recommendations for optimization"""


# =============================================================================
# SAMPLING TOOL: LLM-Assisted Query
# =============================================================================


@mcp.tool(annotations={"readOnlyHint": True})
async def ask_database(question: str, ctx: Context = None) -> dict:
    """
    Ask a natural language question about the inventory.

    Uses the LLM to generate an appropriate SQL query based on your question,
    then executes it and returns the results.

    Args:
        question: Natural language question about devices or subscriptions

    Returns:
        Query results or error information
    """
    # Get schema context for the LLM
    devices_schema = await get_devices_schema(ctx)
    subscriptions_schema = await get_subscriptions_schema(ctx)
    valid_values = await get_valid_values(ctx)
    examples = await get_query_examples(ctx)

    context = f"""Database Schema Information:

{devices_schema}

{subscriptions_schema}

{valid_values}

{examples}

Important tables and relationships:
- devices: Main device inventory table
- subscriptions: Subscription/license inventory
- device_subscriptions: Many-to-many link between devices and subscriptions
- device_tags: Key-value tags for devices
- subscription_tags: Key-value tags for subscriptions

Available views: active_devices, active_subscriptions, devices_expiring_soon, subscriptions_expiring_soon, devices_with_subscriptions, device_summary, subscription_summary

Available functions: search_devices(query, limit), get_devices_by_tag(key, value)
"""

    system_prompt = """You are a PostgreSQL expert helping to query an HPE GreenLake inventory database.

Rules:
1. Generate ONLY read-only SELECT queries
2. Never use INSERT, UPDATE, DELETE, DROP, or other modifying statements
3. Use appropriate JOINs when querying across tables
4. Use the available views when they match the request
5. Limit results to 100 rows unless specifically asked for more
6. Return ONLY the SQL query, no explanation

If the question cannot be answered with a SELECT query, explain why."""

    try:
        result = await ctx.sample(
            messages=f"Given this database schema:\n\n{context}\n\nGenerate a read-only SQL query to answer: {question}",
            system_prompt=system_prompt,
            max_tokens=500,
        )

        generated_sql = result.text.strip()

        # Clean up the SQL (remove markdown code blocks if present)
        if generated_sql.startswith("```"):
            lines = generated_sql.split("\n")
            generated_sql = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        # Validate the generated SQL
        if not validate_readonly_sql(generated_sql):
            return {
                "error": "Generated query is not read-only",
                "generated_sql": generated_sql,
            }

        # Execute the query
        pool = get_pool(ctx)
        async with pool.acquire() as conn:
            rows = await conn.fetch(generated_sql)

        return {
            "question": question,
            "generated_sql": generated_sql,
            "results": rows_to_dicts(rows),
            "row_count": len(rows),
        }

    except Exception as e:
        error_msg = str(e)
        if "sampling" in error_msg.lower() or "not supported" in error_msg.lower():
            return {
                "error": "Sampling is not supported by this MCP client. Please use direct query tools instead.",
                "suggestion": "Try using search_devices, list_devices, or run_query tools.",
            }
        return {"error": error_msg}


# =============================================================================
# Write Tools (Device Assignment)
# =============================================================================


@mcp.tool(annotations={"readOnlyHint": False})
async def apply_device_assignments(
    ctx: Context,
    assignments: list[dict[str, Any]],
    wait_for_completion: bool = True,
) -> dict[str, Any]:
    """Apply device assignments (subscriptions, applications, tags) to devices.

    This tool performs bulk assignment operations following a phased workflow:
    1. Process existing devices (have UUIDs)
    2. Add new devices (no UUIDs)
    3. Refresh DB to get new UUIDs
    4. Process newly added devices

    Args:
        ctx: FastMCP context
        assignments: List of device assignments with the following structure:
            - serial_number (str, required): Device serial number
            - mac_address (str, optional): Device MAC address
            - device_id (str, optional): Device UUID (if known)
            - device_type (str, optional): NETWORK, COMPUTE, or STORAGE
            - current_subscription_id (str, optional): Current subscription UUID
            - current_application_id (str, optional): Current application UUID
            - current_tags (dict, optional): Current tags
            - selected_subscription_id (str, optional): New subscription UUID to assign
            - selected_application_id (str, optional): New application UUID to assign
            - selected_region (str, optional): Region code (e.g., "us-west")
            - selected_tags (dict, optional): New tags to assign
            - keep_current_subscription (bool, optional): Keep current subscription
            - keep_current_application (bool, optional): Keep current application
            - keep_current_tags (bool, optional): Keep current tags
        wait_for_completion: Whether to wait for async operations to complete

    Returns:
        Dictionary with operation results:
            - success (bool): Overall success status
            - operations (list): List of operation results
            - devices_created (int): Number of devices created
            - applications_assigned (int): Number of application assignments
            - subscriptions_assigned (int): Number of subscription assignments
            - tags_updated (int): Number of tag updates
            - errors (int): Number of errors encountered

    Example:
        ```python
        result = await apply_device_assignments(
            ctx,
            assignments=[
                {
                    "serial_number": "SN123456",
                    "device_id": "550e8400-e29b-41d4-a716-446655440000",
                    "selected_subscription_id": "660e8400-e29b-41d4-a716-446655440000",
                    "selected_application_id": "770e8400-e29b-41d4-a716-446655440000",
                    "selected_tags": {"env": "production", "location": "us-west"}
                }
            ],
            wait_for_completion=True
        )
        ```
    """
    # Check if GLP client is initialized
    if _DEVICE_MANAGER is None:
        return {
            "success": False,
            "error": "GLP client not initialized. Required environment variables may be missing.",
            "operations": [],
            "devices_created": 0,
            "applications_assigned": 0,
            "subscriptions_assigned": 0,
            "tags_updated": 0,
            "errors": 1,
        }

    try:
        # Convert input dictionaries to DeviceAssignment entities
        device_assignments = []
        for a in assignments:
            # Parse UUIDs if provided as strings
            device_id = UUID(a["device_id"]) if a.get("device_id") else None
            current_sub_id = UUID(a["current_subscription_id"]) if a.get("current_subscription_id") else None
            current_app_id = UUID(a["current_application_id"]) if a.get("current_application_id") else None
            selected_sub_id = UUID(a["selected_subscription_id"]) if a.get("selected_subscription_id") else None
            selected_app_id = UUID(a["selected_application_id"]) if a.get("selected_application_id") else None

            assignment = DeviceAssignment(
                serial_number=a["serial_number"],
                mac_address=a.get("mac_address"),
                row_number=a.get("row_number", 0),
                device_id=device_id,
                device_type=a.get("device_type"),
                model=a.get("model"),
                region=a.get("region"),
                current_subscription_id=current_sub_id,
                current_subscription_key=a.get("current_subscription_key"),
                current_application_id=current_app_id,
                current_tags=a.get("current_tags", {}),
                selected_subscription_id=selected_sub_id,
                selected_application_id=selected_app_id,
                selected_region=a.get("selected_region"),
                selected_tags=a.get("selected_tags", {}),
                keep_current_subscription=a.get("keep_current_subscription", False),
                keep_current_application=a.get("keep_current_application", False),
                keep_current_tags=a.get("keep_current_tags", False),
            )
            device_assignments.append(assignment)

        # Create adapters
        device_manager = GLPDeviceManagerAdapter(_DEVICE_MANAGER)
        device_repo = PostgresDeviceRepository(_DB_POOL)
        sync_service = DeviceSyncerAdapter(
            _DEVICE_SYNCER,
            _SUBSCRIPTION_SYNCER,
            db_pool=_DB_POOL,
        )

        # Execute the use case
        use_case = ApplyAssignmentsUseCase(
            device_manager=device_manager,
            device_repository=device_repo,
            sync_service=sync_service,
        )

        result = await use_case.execute(
            assignments=device_assignments,
            wait_for_completion=wait_for_completion,
        )

        # Convert result to dictionary
        return {
            "success": result.success,
            "operations": [
                {
                    "success": op.success,
                    "operation_type": op.operation_type,
                    "device_ids": [str(d) for d in op.device_ids],
                    "device_serials": op.device_serials,
                    "error": op.error,
                    "operation_url": op.operation_url,
                }
                for op in result.operations
            ],
            "devices_created": result.devices_created,
            "applications_assigned": result.applications_assigned,
            "subscriptions_assigned": result.subscriptions_assigned,
            "tags_updated": result.tags_updated,
            "errors": result.errors,
            "total_duration_seconds": result.total_duration_seconds,
        }

    except Exception as e:
        logger.exception("Error applying device assignments")
        return {
            "success": False,
            "error": str(e),
            "operations": [],
            "devices_created": 0,
            "applications_assigned": 0,
            "subscriptions_assigned": 0,
            "tags_updated": 0,
            "errors": 1,
        }


@mcp.tool(annotations={"readOnlyHint": False})
async def add_devices(
    ctx: Context,
    devices: list[dict[str, Any]],
    wait_for_completion: bool = True,
) -> dict[str, Any]:
    """Add new devices to GreenLake Platform.

    This tool adds devices to the GreenLake workspace. Each device must have
    a serial number and meet device-type-specific requirements:
    - NETWORK devices require mac_address
    - COMPUTE/STORAGE devices require part_number

    Args:
        ctx: FastMCP context
        devices: List of devices to add with the following structure:
            - serial_number (str, required): Device serial number
            - mac_address (str, required for NETWORK): MAC address
            - part_number (str, required for COMPUTE/STORAGE): Part number
            - device_type (str, optional): NETWORK, COMPUTE, or STORAGE (default: NETWORK)
            - tags (dict, optional): Tags to assign to the device
            - location_id (str, optional): Location UUID
        wait_for_completion: Whether to wait for async operations to complete

    Returns:
        Dictionary with operation results:
            - success (bool): Overall success status
            - devices_added (int): Number of devices added successfully
            - devices_failed (int): Number of failed device additions
            - results (list): List of per-device results with:
                - serial_number (str): Device serial number
                - success (bool): Whether this device was added
                - device_id (str, optional): Device UUID if successful
                - error (str, optional): Error message if failed
                - operation_url (str, optional): URL for status tracking
            - errors (list): List of error messages

    Example:
        ```python
        result = await add_devices(
            ctx,
            devices=[
                {
                    "serial_number": "TEST123",
                    "mac_address": "00:11:22:33:44:55",
                    "device_type": "NETWORK",
                    "tags": {"env": "production"}
                },
                {
                    "serial_number": "COMPUTE001",
                    "part_number": "P12345",
                    "device_type": "COMPUTE"
                }
            ],
            wait_for_completion=True
        )
        ```
    """
    # Check if GLP client is initialized
    if _DEVICE_MANAGER is None:
        return {
            "success": False,
            "error": "GLP client not initialized. Required environment variables may be missing.",
            "devices_added": 0,
            "devices_failed": len(devices),
            "results": [],
            "errors": ["GLP client not initialized"],
        }

    try:
        from src.glp.api.device_manager import DeviceType

        results = []
        devices_added = 0
        devices_failed = 0
        errors = []

        for device in devices:
            serial_number = device.get("serial_number")
            if not serial_number:
                devices_failed += 1
                errors.append("Device missing serial_number")
                results.append({
                    "serial_number": "unknown",
                    "success": False,
                    "error": "serial_number is required",
                })
                continue

            try:
                # Get device type (default to NETWORK)
                device_type_str = device.get("device_type", "NETWORK").upper()
                try:
                    device_type = DeviceType(device_type_str)
                except ValueError:
                    raise ValueError(
                        f"Invalid device_type: {device_type_str}. "
                        f"Must be one of: NETWORK, COMPUTE, STORAGE"
                    )

                # Extract optional fields
                part_number = device.get("part_number")
                mac_address = device.get("mac_address")
                tags = device.get("tags", {})
                location_id = device.get("location_id")

                # Call the device manager
                operation = await _DEVICE_MANAGER.add_device(
                    serial_number=serial_number,
                    device_type=device_type,
                    part_number=part_number,
                    mac_address=mac_address,
                    tags=tags if tags else None,
                    location_id=location_id,
                    dry_run=False,
                )

                # Wait for completion if requested
                device_id = None
                if wait_for_completion and operation.operation_url:
                    try:
                        status = await _DEVICE_MANAGER.wait_for_completion(
                            operation.operation_url,
                            timeout=300,  # 5 minutes
                        )
                        if status.is_success and status.result:
                            # Extract device ID from result
                            device_id = status.result.get("id")
                    except Exception as wait_error:
                        logger.warning(
                            f"Failed to wait for completion of {serial_number}: {wait_error}"
                        )

                devices_added += 1
                results.append({
                    "serial_number": serial_number,
                    "success": True,
                    "device_id": device_id,
                    "operation_url": operation.operation_url,
                })

            except Exception as e:
                error_msg = str(e)
                devices_failed += 1
                errors.append(f"{serial_number}: {error_msg}")
                results.append({
                    "serial_number": serial_number,
                    "success": False,
                    "error": error_msg,
                })
                logger.error(f"Failed to add device {serial_number}: {e}")

        return {
            "success": devices_failed == 0,
            "devices_added": devices_added,
            "devices_failed": devices_failed,
            "results": results,
            "errors": errors,
        }

    except Exception as e:
        logger.exception("Error adding devices")
        return {
            "success": False,
            "error": str(e),
            "devices_added": 0,
            "devices_failed": len(devices),
            "results": [],
            "errors": [str(e)],
        }


@mcp.tool(annotations={"readOnlyHint": False})
async def archive_devices(
    ctx: Context,
    device_ids: list[str],
    wait_for_completion: bool = True,
    sync_after: bool = True,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Archive devices in GreenLake Platform.

    This tool archives devices in the GreenLake workspace. Archived devices
    are hidden from normal views but can be unarchived later.

    ⚠️ HIGH-RISK OPERATION: Requires confirmation before execution.

    Args:
        ctx: FastMCP context
        device_ids: List of device UUIDs to archive (as strings)
        wait_for_completion: Whether to wait for async operations to complete
        sync_after: Whether to sync the database after archiving
        confirmed: Set to True to bypass confirmation (after user confirmation)

    Returns:
        Dictionary with operation results:
            - status (str): "confirmation_required" or "success"
            - confirmation_message (str): Message to show user (if confirmation required)
            - operation_id (str): Operation ID for confirmation (if confirmation required)
            - risk_level (str): Risk level of the operation (if confirmation required)
            - success (bool): Overall success status (if executed)
            - action (str): The action performed (ARCHIVE)
            - devices_processed (int): Total number of devices processed (if executed)
            - devices_succeeded (int): Number of devices archived successfully (if executed)
            - devices_failed (int): Number of failed device archival (if executed)
            - total_duration_seconds (float): Total operation duration (if executed)
            - failed_device_ids (list[str]): List of failed device UUIDs (if executed)
            - failed_device_serials (list[str]): List of failed device serial numbers (if executed)
            - operations (list): List of operation results (if executed)

    Example:
        ```python
        # First call - returns confirmation request
        result = await archive_devices(
            ctx,
            device_ids=[
                "550e8400-e29b-41d4-a716-446655440000",
                "660e8400-e29b-41d4-a716-446655440001"
            ]
        )
        # Returns: {"status": "confirmation_required", "message": "...", "operation_id": "..."}

        # Second call - with confirmation
        result = await archive_devices(
            ctx,
            device_ids=[
                "550e8400-e29b-41d4-a716-446655440000",
                "660e8400-e29b-41d4-a716-446655440001"
            ],
            confirmed=True
        )
        # Executes the operation
        ```
    """
    global _PENDING_OPERATIONS

    # Assess risk level
    device_count = len(device_ids)
    risk_level = _assess_risk(OperationType.ARCHIVE_DEVICES, device_count)

    # Check if confirmation is required
    requires_confirmation = risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    if requires_confirmation and not confirmed:
        # Generate operation ID
        from uuid import uuid4
        operation_id = str(uuid4())

        # Store pending operation
        _PENDING_OPERATIONS[operation_id] = {
            "operation_type": OperationType.ARCHIVE_DEVICES,
            "device_ids": device_ids,
            "wait_for_completion": wait_for_completion,
            "sync_after": sync_after,
            "risk_level": risk_level,
        }

        # Return confirmation request
        return {
            "status": "confirmation_required",
            "confirmation_message": _get_confirmation_message(
                OperationType.ARCHIVE_DEVICES,
                device_count,
                risk_level,
            ),
            "operation_id": operation_id,
            "risk_level": risk_level.value,
            "device_count": device_count,
        }

    # Proceed with execution (confirmed or low/medium risk)
    # Check if GLP client is initialized
    if _DEVICE_MANAGER is None:
        return {
            "success": False,
            "error": "GLP client not initialized. Required environment variables may be missing.",
            "action": "ARCHIVE",
            "devices_processed": len(device_ids),
            "devices_succeeded": 0,
            "devices_failed": len(device_ids),
            "total_duration_seconds": 0.0,
            "failed_device_ids": device_ids,
            "failed_device_serials": [],
            "operations": [],
        }

    try:
        # Convert device_ids to DeviceAssignment entities
        device_assignments = []
        for i, device_id_str in enumerate(device_ids):
            try:
                device_id = UUID(device_id_str)
                assignment = DeviceAssignment(
                    serial_number=f"device_{i}",  # Placeholder, will be fetched
                    device_id=device_id,
                )
                device_assignments.append(assignment)
            except ValueError as e:
                logger.error(f"Invalid UUID format: {device_id_str}: {e}")
                return {
                    "success": False,
                    "error": f"Invalid UUID format: {device_id_str}",
                    "action": "ARCHIVE",
                    "devices_processed": len(device_ids),
                    "devices_succeeded": 0,
                    "devices_failed": len(device_ids),
                    "total_duration_seconds": 0.0,
                    "failed_device_ids": device_ids,
                    "failed_device_serials": [],
                    "operations": [],
                }

        # Create adapters
        device_manager = GLPDeviceManagerAdapter(_DEVICE_MANAGER)
        sync_service = DeviceSyncerAdapter(
            _DEVICE_SYNCER,
            _SUBSCRIPTION_SYNCER,
            db_pool=_DB_POOL,
        ) if sync_after else None

        # Execute the use case
        use_case = DeviceActionsUseCase(
            device_manager=device_manager,
            sync_service=sync_service,
        )

        result = await use_case.execute(
            action=WorkflowAction.ARCHIVE,
            devices=device_assignments,
            wait_for_completion=wait_for_completion,
            sync_after=sync_after,
        )

        # Convert result to dictionary
        return {
            "success": result.success,
            "action": result.action.value,
            "devices_processed": result.devices_processed,
            "devices_succeeded": result.devices_succeeded,
            "devices_failed": result.devices_failed,
            "total_duration_seconds": result.total_duration_seconds,
            "failed_device_ids": [str(d) for d in result.failed_device_ids],
            "failed_device_serials": result.failed_device_serials,
            "operations": [
                {
                    "success": op.success,
                    "operation_type": op.operation_type,
                    "device_ids": [str(d) for d in op.device_ids] if op.device_ids else [],
                    "device_serials": op.device_serials or [],
                    "error": op.error,
                    "operation_url": op.operation_url,
                }
                for op in result.operations
            ],
        }

    except Exception as e:
        logger.exception("Error archiving devices")
        return {
            "success": False,
            "error": str(e),
            "action": "ARCHIVE",
            "devices_processed": len(device_ids),
            "devices_succeeded": 0,
            "devices_failed": len(device_ids),
            "total_duration_seconds": 0.0,
            "failed_device_ids": device_ids,
            "failed_device_serials": [],
            "operations": [],
        }


@mcp.tool(annotations={"readOnlyHint": False})
async def unarchive_devices(
    ctx: Context,
    device_ids: list[str],
    wait_for_completion: bool = True,
    sync_after: bool = True,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Unarchive devices in GreenLake Platform.

    This tool unarchives (restores) devices in the GreenLake workspace.
    Unarchived devices will be visible in normal views again.

    Args:
        ctx: FastMCP context
        device_ids: List of device UUIDs to unarchive (as strings)
        wait_for_completion: Whether to wait for async operations to complete
        sync_after: Whether to sync the database after unarchiving
        confirmed: Set to True to bypass confirmation (after user confirmation)

    Returns:
        Dictionary with operation results:
            - status (str): "confirmation_required" or "success" (may require confirmation for bulk operations)
            - confirmation_message (str): Message to show user (if confirmation required)
            - operation_id (str): Operation ID for confirmation (if confirmation required)
            - risk_level (str): Risk level of the operation (if confirmation required)
            - success (bool): Overall success status (if executed)
            - action (str): The action performed (UNARCHIVE)
            - devices_processed (int): Total number of devices processed (if executed)
            - devices_succeeded (int): Number of devices unarchived successfully (if executed)
            - devices_failed (int): Number of failed device unarchival (if executed)
            - total_duration_seconds (float): Total operation duration (if executed)
            - failed_device_ids (list[str]): List of failed device UUIDs (if executed)
            - failed_device_serials (list[str]): List of failed device serial numbers (if executed)
            - operations (list): List of operation results (if executed)

    Example:
        ```python
        # First call - may return confirmation request for bulk operations (>5 devices)
        result = await unarchive_devices(
            ctx,
            device_ids=["550e8400-e29b-41d4-a716-446655440000", ...]
        )

        # If confirmation required, call again with confirmed=True
        result = await unarchive_devices(
            ctx,
            device_ids=["550e8400-e29b-41d4-a716-446655440000", ...],
            confirmed=True
        )
        ```
    """
    global _PENDING_OPERATIONS

    # Assess risk level
    device_count = len(device_ids)
    risk_level = _assess_risk(OperationType.UNARCHIVE_DEVICES, device_count)

    # Check if confirmation is required (for HIGH or CRITICAL risk)
    requires_confirmation = risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    if requires_confirmation and not confirmed:
        # Generate operation ID
        from uuid import uuid4
        operation_id = str(uuid4())

        # Store pending operation
        _PENDING_OPERATIONS[operation_id] = {
            "operation_type": OperationType.UNARCHIVE_DEVICES,
            "device_ids": device_ids,
            "wait_for_completion": wait_for_completion,
            "sync_after": sync_after,
            "risk_level": risk_level,
        }

        # Return confirmation request
        return {
            "status": "confirmation_required",
            "confirmation_message": _get_confirmation_message(
                OperationType.UNARCHIVE_DEVICES,
                device_count,
                risk_level,
            ),
            "operation_id": operation_id,
            "risk_level": risk_level.value,
            "device_count": device_count,
        }

    # Proceed with execution (confirmed or low/medium risk)
    # Check if GLP client is initialized
    if _DEVICE_MANAGER is None:
        return {
            "success": False,
            "error": "GLP client not initialized. Required environment variables may be missing.",
            "action": "UNARCHIVE",
            "devices_processed": len(device_ids),
            "devices_succeeded": 0,
            "devices_failed": len(device_ids),
            "total_duration_seconds": 0.0,
            "failed_device_ids": device_ids,
            "failed_device_serials": [],
            "operations": [],
        }

    try:
        # Convert device_ids to DeviceAssignment entities
        device_assignments = []
        for i, device_id_str in enumerate(device_ids):
            try:
                device_id = UUID(device_id_str)
                assignment = DeviceAssignment(
                    serial_number=f"device_{i}",  # Placeholder, will be fetched
                    device_id=device_id,
                )
                device_assignments.append(assignment)
            except ValueError as e:
                logger.error(f"Invalid UUID format: {device_id_str}: {e}")
                return {
                    "success": False,
                    "error": f"Invalid UUID format: {device_id_str}",
                    "action": "UNARCHIVE",
                    "devices_processed": len(device_ids),
                    "devices_succeeded": 0,
                    "devices_failed": len(device_ids),
                    "total_duration_seconds": 0.0,
                    "failed_device_ids": device_ids,
                    "failed_device_serials": [],
                    "operations": [],
                }

        # Create adapters
        device_manager = GLPDeviceManagerAdapter(_DEVICE_MANAGER)
        sync_service = DeviceSyncerAdapter(
            _DEVICE_SYNCER,
            _SUBSCRIPTION_SYNCER,
            db_pool=_DB_POOL,
        ) if sync_after else None

        # Execute the use case
        use_case = DeviceActionsUseCase(
            device_manager=device_manager,
            sync_service=sync_service,
        )

        result = await use_case.execute(
            action=WorkflowAction.UNARCHIVE,
            devices=device_assignments,
            wait_for_completion=wait_for_completion,
            sync_after=sync_after,
        )

        # Convert result to dictionary
        return {
            "success": result.success,
            "action": result.action.value,
            "devices_processed": result.devices_processed,
            "devices_succeeded": result.devices_succeeded,
            "devices_failed": result.devices_failed,
            "total_duration_seconds": result.total_duration_seconds,
            "failed_device_ids": [str(d) for d in result.failed_device_ids],
            "failed_device_serials": result.failed_device_serials,
            "operations": [
                {
                    "success": op.success,
                    "operation_type": op.operation_type,
                    "device_ids": [str(d) for d in op.device_ids] if op.device_ids else [],
                    "device_serials": op.device_serials or [],
                    "error": op.error,
                    "operation_url": op.operation_url,
                }
                for op in result.operations
            ],
        }

    except Exception as e:
        logger.exception("Error unarchiving devices")
        return {
            "success": False,
            "error": str(e),
            "action": "UNARCHIVE",
            "devices_processed": len(device_ids),
            "devices_succeeded": 0,
            "devices_failed": len(device_ids),
            "total_duration_seconds": 0.0,
            "failed_device_ids": device_ids,
            "failed_device_serials": [],
            "operations": [],
        }


@mcp.tool(annotations={"readOnlyHint": False})
async def update_device_tags(
    ctx: Context,
    device_ids: list[str],
    tags: dict[str, str | None],
    wait_for_completion: bool = True,
) -> dict[str, Any]:
    """Update tags on devices in GreenLake Platform.

    This tool adds, updates, or removes tags on devices. Tags are key-value pairs
    that can be used to organize and categorize devices. Set a tag value to None
    to remove that tag from the devices.

    Note: Maximum 25 devices per call due to GreenLake API limitations.

    Args:
        ctx: FastMCP context
        device_ids: List of device UUIDs to update (as strings, max 25)
        tags: Tag key-value pairs to set. Set value to None to remove a tag.
        wait_for_completion: Whether to wait for async operations to complete

    Returns:
        Dictionary with operation results:
            - success (bool): Overall success status
            - devices_processed (int): Number of devices processed
            - tags_updated (int): Number of tag keys updated
            - operation_url (str, optional): URL for status tracking
            - error (str, optional): Error message if failed

    Example:
        ```python
        # Add/update tags
        result = await update_device_tags(
            ctx,
            device_ids=[
                "550e8400-e29b-41d4-a716-446655440000",
                "660e8400-e29b-41d4-a716-446655440001"
            ],
            tags={
                "environment": "production",
                "location": "us-west",
                "owner": "network-team"
            },
            wait_for_completion=True
        )

        # Remove a tag by setting it to None
        result = await update_device_tags(
            ctx,
            device_ids=["550e8400-e29b-41d4-a716-446655440000"],
            tags={"temporary": None},  # Removes the "temporary" tag
            wait_for_completion=True
        )
        ```
    """
    # Check if GLP client is initialized
    if _DEVICE_MANAGER is None:
        return {
            "success": False,
            "error": "GLP client not initialized. Required environment variables may be missing.",
            "devices_processed": 0,
            "tags_updated": 0,
        }

    # Validate inputs
    if not device_ids:
        return {
            "success": False,
            "error": "device_ids list cannot be empty",
            "devices_processed": 0,
            "tags_updated": 0,
        }

    if len(device_ids) > 25:
        return {
            "success": False,
            "error": f"Maximum 25 devices per call. Got {len(device_ids)} devices. Please split into smaller batches.",
            "devices_processed": 0,
            "tags_updated": 0,
        }

    if not tags:
        return {
            "success": False,
            "error": "tags dictionary cannot be empty",
            "devices_processed": 0,
            "tags_updated": 0,
        }

    try:
        # Call the device manager
        operation = await _DEVICE_MANAGER.update_tags(
            device_ids=device_ids,
            tags=tags,
            dry_run=False,
        )

        # Wait for completion if requested
        if wait_for_completion and operation.operation_url:
            try:
                status = await _DEVICE_MANAGER.wait_for_completion(
                    operation.operation_url,
                    timeout=300,  # 5 minutes
                )
                if not status.is_success:
                    return {
                        "success": False,
                        "error": f"Operation failed: {status.error_message or 'Unknown error'}",
                        "devices_processed": len(device_ids),
                        "tags_updated": len(tags),
                        "operation_url": operation.operation_url,
                    }
            except Exception as wait_error:
                logger.warning(f"Failed to wait for completion: {wait_error}")
                return {
                    "success": False,
                    "error": f"Failed to wait for completion: {str(wait_error)}",
                    "devices_processed": len(device_ids),
                    "tags_updated": len(tags),
                    "operation_url": operation.operation_url,
                }

        return {
            "success": True,
            "devices_processed": len(device_ids),
            "tags_updated": len(tags),
            "operation_url": operation.operation_url,
        }

    except Exception as e:
        error_msg = str(e)
        logger.exception("Error updating device tags")
        return {
            "success": False,
            "error": error_msg,
            "devices_processed": 0,
            "tags_updated": 0,
        }


# =============================================================================
# Server Entry Point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GreenLake Inventory MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to for HTTP transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport in ("http", "streamable-http"):
        # Use streamable-http for better performance
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
        )
    else:
        mcp.run(transport="stdio")
