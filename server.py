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
import os
import re
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from dotenv import load_dotenv
from fastmcp import Context, FastMCP

load_dotenv()

# =============================================================================
# Database Connection Pool (Lifespan)
# =============================================================================


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize and cleanup database connection pool."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=5,
        command_timeout=60,
    )
    try:
        yield {"db_pool": pool}
    finally:
        await pool.close()


# =============================================================================
# FastMCP Server
# =============================================================================

mcp = FastMCP(
    name="GreenLake Inventory",
    instructions=(
        "This server provides read-only access to HPE GreenLake device and "
        "subscription inventory. Use the tools to search devices, list subscriptions, "
        "and analyze inventory data. All operations are read-only."
    ),
    lifespan=lifespan,
)


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
# Server Entry Point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GreenLake Inventory MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="http", port=args.port)
    else:
        mcp.run(transport="stdio")
