"""FastAPI router for network clients endpoints.

Provides API endpoints for viewing and managing network clients
(WiFi/Wired devices connected to network equipment) organized by site.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .dependencies import get_db_pool, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients", tags=["Clients"])


# ========== Response Schemas ==========


class ClientItem(BaseModel):
    """Network client item."""
    id: int
    site_id: str
    site_name: Optional[str] = None
    mac: str
    name: Optional[str] = None
    health: Optional[str] = None
    status: Optional[str] = None
    status_reason: Optional[str] = None
    type: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    network: Optional[str] = None  # WiFi network name (SSID)
    vlan_id: Optional[str] = None
    port: Optional[str] = None
    role: Optional[str] = None
    connected_device_serial: Optional[str] = None
    connected_to: Optional[str] = None
    connected_since: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    tunnel: Optional[str] = None
    tunnel_id: Optional[int] = None
    key_management: Optional[str] = None
    authentication: Optional[str] = None
    updated_at: Optional[datetime] = None


class ClientListResponse(BaseModel):
    """Paginated client list response."""
    items: list[ClientItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class SiteStats(BaseModel):
    """Site with client statistics."""
    site_id: str
    site_name: Optional[str] = None
    client_count: int = 0
    connected_count: int = 0
    wired_count: int = 0
    wireless_count: int = 0
    good_health_count: int = 0
    fair_health_count: int = 0
    poor_health_count: int = 0
    device_count: int = 0
    last_synced_at: Optional[datetime] = None


class SiteListResponse(BaseModel):
    """Paginated site list response."""
    items: list[SiteStats]
    total: int
    page: int
    page_size: int
    total_pages: int


class ClientsSummary(BaseModel):
    """Summary statistics for all clients."""
    total_clients: int = 0
    connected: int = 0
    disconnected: int = 0
    failed: int = 0
    blocked: int = 0
    wired: int = 0
    wireless: int = 0
    health_good: int = 0
    health_fair: int = 0
    health_poor: int = 0
    health_unknown: int = 0
    total_sites: int = 0
    last_sync_at: Optional[datetime] = None


class SyncResponse(BaseModel):
    """Sync operation response."""
    status: str
    message: str
    started_at: Optional[datetime] = None
    clients: Optional[dict] = None
    firmware: Optional[dict] = None


# ========== Endpoints ==========


@router.get("/filtered", response_model=ClientListResponse)
async def get_filtered_clients(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=10, le=1000, description="Items per page"),
    client_type: Optional[str] = Query(default=None, alias="type", description="Filter by type (Wired,Wireless) - comma-delimited"),
    status: Optional[str] = Query(default=None, description="Filter by status - comma-delimited"),
    health: Optional[str] = Query(default=None, description="Filter by health - comma-delimited"),
    site_id: Optional[str] = Query(default=None, description="Filter by site ID - comma-delimited"),
    network: Optional[str] = Query(default=None, description="Filter by network/SSID - comma-delimited"),
    vlan: Optional[str] = Query(default=None, description="Filter by VLAN ID - comma-delimited"),
    role: Optional[str] = Query(default=None, description="Filter by role - comma-delimited"),
    tunnel: Optional[str] = Query(default=None, description="Filter by tunnel type - comma-delimited"),
    authentication: Optional[str] = Query(default=None, alias="auth", description="Filter by authentication - comma-delimited"),
    key_management: Optional[str] = Query(default=None, alias="key_mgmt", description="Filter by key management - comma-delimited"),
    connected_to: Optional[str] = Query(default=None, description="Filter by connected device - comma-delimited"),
    subnet: Optional[str] = Query(default=None, description="Filter by IP subnet (e.g., 172.18.188)"),
    search: Optional[str] = Query(default=None, description="Search by MAC, name, or IP"),
    sort_by: str = Query(default="last_seen_at", description="Sort field"),
    sort_order: str = Query(default="desc", description="Sort order (asc/desc)"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get filtered clients across all sites.

    Supports multi-value filters using comma-delimited strings.
    Filter logic: OR within category, AND across categories.
    Example: type=Wired,Wireless&health=Good returns (Wired OR Wireless) AND Good health
    """
    async with pool.acquire() as conn:
        # Build WHERE clause with multi-value support
        where_clauses = ["(c.status IS NULL OR c.status != 'REMOVED')"]
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

        # Parse comma-delimited filters into arrays
        if client_type:
            add_multi_filter(client_type, "c.type")

        if status:
            add_multi_filter(status, "c.status")

        if health:
            add_multi_filter(health, "c.health")

        if site_id:
            add_multi_filter(site_id, "c.site_id")

        if network:
            add_multi_filter(network, "c.network")

        if vlan:
            add_multi_filter(vlan, "c.vlan_id")

        if role:
            add_multi_filter(role, "c.role")

        if tunnel:
            add_multi_filter(tunnel, "c.tunnel")

        if authentication:
            add_multi_filter(authentication, "c.authentication")

        if key_management:
            add_multi_filter(key_management, "c.key_management")

        if connected_to:
            add_multi_filter(connected_to, "c.connected_to")

        # Subnet filter - partial match on IP
        if subnet:
            where_clauses.append(f"c.ipv4::text LIKE ${param_idx} || '%'")
            params.append(subnet)
            param_idx += 1

        if search:
            where_clauses.append(f"""
                (c.mac::text ILIKE '%' || ${param_idx} || '%'
                 OR c.name ILIKE '%' || ${param_idx} || '%'
                 OR c.ipv4::text LIKE '%' || ${param_idx} || '%')
            """)
            params.append(search)
            param_idx += 1

        where_sql = " AND ".join(where_clauses)

        # Validate sort column
        valid_sort_cols = {
            "mac", "name", "health", "status", "type",
            "ipv4", "connected_to", "last_seen_at", "updated_at", "site_name"
        }
        if sort_by not in valid_sort_cols:
            sort_by = "last_seen_at"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Count total
        count_sql = f"SELECT COUNT(*) FROM clients c WHERE {where_sql}"
        total = await conn.fetchval(count_sql, *params)

        if total == 0:
            return ClientListResponse(
                items=[], total=0, page=page,
                page_size=page_size, total_pages=0
            )

        # Calculate pagination
        offset = (page - 1) * page_size
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Fetch clients with site name
        query_sql = f"""
            SELECT
                c.id,
                c.site_id,
                s.site_name,
                c.mac::text AS mac,
                c.name,
                c.health,
                c.status,
                c.status_reason,
                c.type,
                c.ipv4::text AS ipv4,
                c.ipv6::text AS ipv6,
                c.network,
                c.vlan_id,
                c.port,
                c.role,
                c.connected_device_serial,
                c.connected_to,
                c.connected_since,
                c.last_seen_at,
                c.tunnel,
                c.tunnel_id,
                c.key_management,
                c.authentication,
                c.updated_at
            FROM clients c
            JOIN sites s ON c.site_id = s.site_id
            WHERE {where_sql}
            ORDER BY c.{sort_by} {sort_direction} NULLS LAST
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        rows = await conn.fetch(query_sql, *params)

        items = [
            ClientItem(
                id=row['id'],
                site_id=row['site_id'],
                site_name=row['site_name'],
                mac=row['mac'],
                name=row['name'],
                health=row['health'],
                status=row['status'],
                status_reason=row['status_reason'],
                type=row['type'],
                ipv4=row['ipv4'],
                ipv6=row['ipv6'],
                network=row['network'],
                vlan_id=row['vlan_id'],
                port=row['port'],
                role=row['role'],
                connected_device_serial=row['connected_device_serial'],
                connected_to=row['connected_to'],
                connected_since=row['connected_since'],
                last_seen_at=row['last_seen_at'],
                tunnel=row['tunnel'],
                tunnel_id=row['tunnel_id'],
                key_management=row['key_management'],
                authentication=row['authentication'],
                updated_at=row['updated_at'],
            )
            for row in rows
        ]

        return ClientListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class FilterOptionsResponse(BaseModel):
    """Available filter options for clients."""
    sites: list[dict] = []  # [{id, name}]
    networks: list[str] = []
    vlans: list[str] = []
    roles: list[str] = []
    tunnels: list[str] = []
    authentications: list[str] = []
    key_managements: list[str] = []
    connected_devices: list[str] = []
    subnets: list[str] = []


@router.get("/filter-options", response_model=FilterOptionsResponse)
async def get_filter_options(
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get available filter options for clients.

    Returns distinct values for each filterable field.
    """
    async with pool.acquire() as conn:
        # Get sites with names
        sites = await conn.fetch("""
            SELECT DISTINCT s.site_id, s.site_name
            FROM sites s
            JOIN clients c ON c.site_id = s.site_id
            WHERE c.status IS NULL OR c.status != 'REMOVED'
            ORDER BY s.site_name
        """)

        # Get distinct networks (SSIDs)
        networks = await conn.fetch("""
            SELECT DISTINCT network FROM clients
            WHERE network IS NOT NULL AND network != ''
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY network
            LIMIT 100
        """)

        # Get distinct VLANs
        vlans = await conn.fetch("""
            SELECT DISTINCT vlan_id FROM clients
            WHERE vlan_id IS NOT NULL AND vlan_id != ''
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY vlan_id
            LIMIT 100
        """)

        # Get distinct roles
        roles = await conn.fetch("""
            SELECT DISTINCT role FROM clients
            WHERE role IS NOT NULL AND role != ''
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY role
            LIMIT 100
        """)

        # Get distinct tunnels
        tunnels = await conn.fetch("""
            SELECT DISTINCT tunnel FROM clients
            WHERE tunnel IS NOT NULL AND tunnel != ''
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY tunnel
        """)

        # Get distinct authentications
        authentications = await conn.fetch("""
            SELECT DISTINCT authentication FROM clients
            WHERE authentication IS NOT NULL AND authentication != ''
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY authentication
            LIMIT 50
        """)

        # Get distinct key managements
        key_managements = await conn.fetch("""
            SELECT DISTINCT key_management FROM clients
            WHERE key_management IS NOT NULL AND key_management != ''
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY key_management
            LIMIT 50
        """)

        # Get distinct connected devices
        connected_devices = await conn.fetch("""
            SELECT DISTINCT connected_to FROM clients
            WHERE connected_to IS NOT NULL AND connected_to != ''
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY connected_to
            LIMIT 200
        """)

        # Get common subnets (first 3 octets)
        subnets = await conn.fetch("""
            SELECT DISTINCT
                regexp_replace(ipv4::text, '\\.[0-9]+/.*$', '') AS subnet
            FROM clients
            WHERE ipv4 IS NOT NULL
              AND (status IS NULL OR status != 'REMOVED')
            ORDER BY subnet
            LIMIT 100
        """)

        return FilterOptionsResponse(
            sites=[{"id": r["site_id"], "name": r["site_name"]} for r in sites],
            networks=[r["network"] for r in networks],
            vlans=[r["vlan_id"] for r in vlans],
            roles=[r["role"] for r in roles],
            tunnels=[r["tunnel"] for r in tunnels],
            authentications=[r["authentication"] for r in authentications],
            key_managements=[r["key_management"] for r in key_managements],
            connected_devices=[r["connected_to"] for r in connected_devices],
            subnets=[r["subnet"] for r in subnets if r["subnet"]],
        )


@router.get("/summary", response_model=ClientsSummary)
async def get_clients_summary(
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get summary statistics for all network clients.

    Returns aggregated counts by status, type, and health across all sites.
    """
    async with pool.acquire() as conn:
        # Check if clients_health_summary view exists, otherwise query directly
        try:
            summary = await conn.fetchrow("""
                SELECT * FROM clients_health_summary
            """)
        except Exception:
            # Fallback to direct query
            summary = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS total_clients,
                    COUNT(*) FILTER (WHERE status = 'Connected') AS connected,
                    COUNT(*) FILTER (WHERE status = 'Disconnected') AS disconnected,
                    COUNT(*) FILTER (WHERE status = 'Failed') AS failed,
                    COUNT(*) FILTER (WHERE status = 'Blocked') AS blocked,
                    COUNT(*) FILTER (WHERE type = 'Wired') AS wired,
                    COUNT(*) FILTER (WHERE type = 'Wireless') AS wireless,
                    COUNT(*) FILTER (WHERE health = 'Good') AS health_good,
                    COUNT(*) FILTER (WHERE health = 'Fair') AS health_fair,
                    COUNT(*) FILTER (WHERE health = 'Poor') AS health_poor,
                    COUNT(*) FILTER (WHERE health = 'Unknown' OR health IS NULL) AS health_unknown
                FROM clients
                WHERE status IS NULL OR status != 'REMOVED'
            """)

        # Get site count
        site_count = await conn.fetchval("SELECT COUNT(*) FROM sites")

        # Get last sync time
        last_sync = await conn.fetchval("""
            SELECT MAX(last_synced_at) FROM sites
        """)

        return ClientsSummary(
            total_clients=summary['total_clients'] or 0,
            connected=summary['connected'] or 0,
            disconnected=summary['disconnected'] or 0,
            failed=summary['failed'] or 0,
            blocked=summary['blocked'] or 0,
            wired=summary['wired'] or 0,
            wireless=summary['wireless'] or 0,
            health_good=summary['health_good'] or 0,
            health_fair=summary['health_fair'] or 0,
            health_poor=summary['health_poor'] or 0,
            health_unknown=summary['health_unknown'] or 0,
            total_sites=site_count or 0,
            last_sync_at=last_sync,
        )


@router.get("/sites", response_model=SiteListResponse)
async def list_sites(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=10, le=100, description="Items per page"),
    search: Optional[str] = Query(default=None, description="Search by site name"),
    sort_by: str = Query(default="client_count", description="Sort field"),
    sort_order: str = Query(default="desc", description="Sort order"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get paginated list of sites with client statistics.

    Returns sites sorted by client count (default) with aggregated stats.
    """
    async with pool.acquire() as conn:
        # Build WHERE clause
        where_clauses = ["1=1"]
        params = []
        param_idx = 1

        if search:
            where_clauses.append(f"site_name ILIKE '%' || ${param_idx} || '%'")
            params.append(search)
            param_idx += 1

        where_sql = " AND ".join(where_clauses)

        # Validate sort column
        valid_sort_cols = {
            "site_name", "client_count", "connected_count",
            "device_count", "last_synced_at"
        }
        if sort_by not in valid_sort_cols:
            sort_by = "client_count"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Count total sites
        count_sql = f"""
            SELECT COUNT(*) FROM sites_with_stats
            WHERE {where_sql}
        """
        total = await conn.fetchval(count_sql, *params)

        if total == 0:
            return SiteListResponse(
                items=[], total=0, page=page,
                page_size=page_size, total_pages=0
            )

        # Calculate pagination
        offset = (page - 1) * page_size
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Fetch sites with stats
        query_sql = f"""
            SELECT
                site_id,
                site_name,
                client_count,
                connected_count,
                wired_count,
                wireless_count,
                good_health_count,
                fair_health_count,
                poor_health_count,
                device_count,
                last_synced_at
            FROM sites_with_stats
            WHERE {where_sql}
            ORDER BY {sort_by} {sort_direction} NULLS LAST
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        rows = await conn.fetch(query_sql, *params)

        items = [
            SiteStats(
                site_id=row['site_id'],
                site_name=row['site_name'],
                client_count=row['client_count'] or 0,
                connected_count=row['connected_count'] or 0,
                wired_count=row['wired_count'] or 0,
                wireless_count=row['wireless_count'] or 0,
                good_health_count=row['good_health_count'] or 0,
                fair_health_count=row['fair_health_count'] or 0,
                poor_health_count=row['poor_health_count'] or 0,
                device_count=row['device_count'] or 0,
                last_synced_at=row['last_synced_at'],
            )
            for row in rows
        ]

        return SiteListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


@router.get("/sites/{site_id}", response_model=ClientListResponse)
async def get_site_clients(
    site_id: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=100, ge=10, le=500, description="Items per page"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    health: Optional[str] = Query(default=None, description="Filter by health"),
    client_type: Optional[str] = Query(default=None, alias="type", description="Filter by type (Wired/Wireless)"),
    search: Optional[str] = Query(default=None, description="Search by MAC or name"),
    sort_by: str = Query(default="last_seen_at", description="Sort field"),
    sort_order: str = Query(default="desc", description="Sort order"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Get paginated list of clients for a specific site.

    Returns clients with filtering and sorting options.
    """
    async with pool.acquire() as conn:
        # Verify site exists
        site = await conn.fetchrow(
            "SELECT site_id, site_name FROM sites WHERE site_id = $1",
            site_id
        )
        if not site:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Build WHERE clause
        where_clauses = [
            "c.site_id = $1",
            "(c.status IS NULL OR c.status != 'REMOVED')"
        ]
        params = [site_id]
        param_idx = 2

        if status:
            where_clauses.append(f"c.status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if health:
            where_clauses.append(f"c.health = ${param_idx}")
            params.append(health)
            param_idx += 1

        if client_type:
            where_clauses.append(f"c.type = ${param_idx}")
            params.append(client_type)
            param_idx += 1

        if search:
            where_clauses.append(f"""
                (c.mac::text ILIKE '%' || ${param_idx} || '%'
                 OR c.name ILIKE '%' || ${param_idx} || '%'
                 OR c.ipv4::text LIKE '%' || ${param_idx} || '%')
            """)
            params.append(search)
            param_idx += 1

        where_sql = " AND ".join(where_clauses)

        # Validate sort column
        valid_sort_cols = {
            "mac", "name", "health", "status", "type",
            "ipv4", "connected_to", "last_seen_at", "updated_at"
        }
        if sort_by not in valid_sort_cols:
            sort_by = "last_seen_at"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Count total
        count_sql = f"SELECT COUNT(*) FROM clients c WHERE {where_sql}"
        total = await conn.fetchval(count_sql, *params)

        if total == 0:
            return ClientListResponse(
                items=[], total=0, page=page,
                page_size=page_size, total_pages=0
            )

        # Calculate pagination
        offset = (page - 1) * page_size
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Fetch clients
        query_sql = f"""
            SELECT
                c.id,
                c.site_id,
                s.site_name,
                c.mac::text AS mac,
                c.name,
                c.health,
                c.status,
                c.status_reason,
                c.type,
                c.ipv4::text AS ipv4,
                c.ipv6::text AS ipv6,
                c.network,
                c.vlan_id,
                c.port,
                c.role,
                c.connected_device_serial,
                c.connected_to,
                c.connected_since,
                c.last_seen_at,
                c.tunnel,
                c.tunnel_id,
                c.key_management,
                c.authentication,
                c.updated_at
            FROM clients c
            JOIN sites s ON c.site_id = s.site_id
            WHERE {where_sql}
            ORDER BY c.{sort_by} {sort_direction} NULLS LAST
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        rows = await conn.fetch(query_sql, *params)

        items = [
            ClientItem(
                id=row['id'],
                site_id=row['site_id'],
                site_name=row['site_name'],
                mac=row['mac'],
                name=row['name'],
                health=row['health'],
                status=row['status'],
                status_reason=row['status_reason'],
                type=row['type'],
                ipv4=row['ipv4'],
                ipv6=row['ipv6'],
                network=row['network'],
                vlan_id=row['vlan_id'],
                port=row['port'],
                role=row['role'],
                connected_device_serial=row['connected_device_serial'],
                connected_to=row['connected_to'],
                connected_since=row['connected_since'],
                last_seen_at=row['last_seen_at'],
                tunnel=row['tunnel'],
                tunnel_id=row['tunnel_id'],
                key_management=row['key_management'],
                authentication=row['authentication'],
                updated_at=row['updated_at'],
            )
            for row in rows
        ]

        return ClientListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


@router.get("/search", response_model=ClientListResponse)
async def search_clients(
    q: str = Query(..., min_length=1, description="Search query (MAC, name, or IP)"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=10, le=100, description="Items per page"),
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Search clients across all sites by MAC, name, or IP address.

    Uses the search_clients database function for optimized searching.
    """
    async with pool.acquire() as conn:
        # Use the search function for efficient searching
        try:
            rows = await conn.fetch("""
                SELECT * FROM search_clients($1, $2)
            """, q, page_size * page)  # Fetch enough for pagination

            # Manual pagination on results
            total = len(rows)
            offset = (page - 1) * page_size
            total_pages = max(1, (total + page_size - 1) // page_size)

            paginated_rows = rows[offset:offset + page_size]

            items = [
                ClientItem(
                    id=row['id'],
                    site_id=row['site_id'],
                    site_name=row['site_name'],
                    mac=str(row['mac']) if row['mac'] else None,
                    name=row['name'],
                    health=row['health'],
                    status=row['status'],
                    type=row['type'],
                    ipv4=str(row['ipv4']) if row['ipv4'] else None,
                    connected_to=row['connected_to'],
                )
                for row in paginated_rows
            ]

            return ClientListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )

        except Exception as e:
            logger.warning(f"Search function failed, using fallback: {e}")
            # Fallback to direct query
            rows = await conn.fetch("""
                SELECT
                    c.id,
                    c.site_id,
                    s.site_name,
                    c.mac::text AS mac,
                    c.name,
                    c.health,
                    c.status,
                    c.type,
                    c.ipv4::text AS ipv4,
                    c.connected_to
                FROM clients c
                JOIN sites s ON c.site_id = s.site_id
                WHERE (c.status IS NULL OR c.status != 'REMOVED')
                  AND (
                      c.mac::text ILIKE '%' || $1 || '%'
                      OR c.name ILIKE '%' || $1 || '%'
                      OR c.ipv4::text LIKE '%' || $1 || '%'
                  )
                ORDER BY
                    CASE WHEN c.status = 'Connected' THEN 0 ELSE 1 END,
                    c.last_seen_at DESC NULLS LAST
                LIMIT $2 OFFSET $3
            """, q, page_size, (page - 1) * page_size)

            # Get total count
            total = await conn.fetchval("""
                SELECT COUNT(*) FROM clients c
                WHERE (c.status IS NULL OR c.status != 'REMOVED')
                  AND (
                      c.mac::text ILIKE '%' || $1 || '%'
                      OR c.name ILIKE '%' || $1 || '%'
                      OR c.ipv4::text LIKE '%' || $1 || '%'
                  )
            """, q)

            total_pages = max(1, (total + page_size - 1) // page_size)

            items = [
                ClientItem(
                    id=row['id'],
                    site_id=row['site_id'],
                    site_name=row['site_name'],
                    mac=row['mac'],
                    name=row['name'],
                    health=row['health'],
                    status=row['status'],
                    type=row['type'],
                    ipv4=row['ipv4'],
                    connected_to=row['connected_to'],
                )
                for row in rows
            ]

            return ClientListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )


@router.post("/sync", response_model=SyncResponse)
async def trigger_clients_sync(
    pool=Depends(get_db_pool),
    _auth: bool = Depends(verify_api_key),
):
    """Trigger a sync of clients and firmware from Aruba Central.

    This fetches fresh client and firmware data from the Aruba Central API
    and updates the local database.
    """
    try:
        from src.glp.api import (
            ArubaCentralClient,
            ArubaClientsSyncer,
            ArubaFirmwareSyncer,
            ArubaTokenManager,
        )

        started_at = datetime.now(timezone.utc)
        results = {"clients": None, "firmware": None}

        try:
            aruba_token_manager = ArubaTokenManager()

            async with ArubaCentralClient(aruba_token_manager) as client:
                # Sync clients
                logger.info("Starting clients sync...")
                clients_syncer = ArubaClientsSyncer(client=client, db_pool=pool)
                results["clients"] = await clients_syncer.sync()

                # Sync firmware
                logger.info("Starting firmware sync...")
                firmware_syncer = ArubaFirmwareSyncer(client=client, db_pool=pool)
                results["firmware"] = await firmware_syncer.sync()

            return SyncResponse(
                status="completed",
                message="Clients and firmware sync completed successfully",
                started_at=started_at,
                clients=results["clients"],
                firmware=results["firmware"],
            )

        except ValueError as e:
            logger.warning(f"Aruba Central sync skipped (missing credentials): {e}")
            return SyncResponse(
                status="skipped",
                message=str(e),
                started_at=started_at,
            )

    except Exception as e:
        logger.error(f"Clients sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


@router.get("/health")
async def health_check():
    """Health check endpoint for clients API."""
    return {"status": "healthy", "service": "clients"}
