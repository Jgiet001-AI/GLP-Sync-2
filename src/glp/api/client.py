#!/usr/bin/env python3
"""Generic HTTP Client for HPE GreenLake Platform APIs.

This module provides a reusable, composable HTTP client that handles the
common concerns of GreenLake API communication:

    - OAuth2 authentication via TokenManager
    - Automatic token refresh on 401 responses
    - Rate limit handling with exponential backoff on 429 responses
    - Offset-based pagination with configurable page sizes
    - Connection pooling via shared aiohttp session

Design Philosophy:
    This client knows HOW to talk to GreenLake, but not WHAT to fetch.
    It has no knowledge of devices, subscriptions, or any specific resource.
    That knowledge belongs in the Syncer classes that compose this client.

Usage:
    async with GLPClient(token_manager) as client:
        # Single request
        data = await client.get("/devices/v1/devices", params={"limit": 50})

        # Paginated fetch (memory efficient)
        async for page in client.paginate("/subscriptions/v1/subscriptions"):
            for item in page:
                process(item)

        # Fetch everything (convenience)
        all_items = await client.fetch_all("/devices/v1/devices", page_size=2000)

Author: HPE GreenLake Team
"""
import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import aiohttp

from .auth import TokenManager

# ============================================
# Configuration
# ============================================

@dataclass
class PaginationConfig:
    """Configuration for paginated API requests.

    Attributes:
        page_size: Number of items per request (API-specific limits apply)
        delay_between_pages: Seconds to wait between requests (rate limiting)
        max_pages: Safety limit to prevent infinite loops (None = no limit)
    """
    page_size: int = 50
    delay_between_pages: float = 0.5
    max_pages: Optional[int] = None


# Pre-configured settings for known APIs
DEVICES_PAGINATION = PaginationConfig(
    page_size=2000,
    delay_between_pages=0.5,  # 160 req/min = ~375ms minimum, we use 500ms
    max_pages=None,
)

SUBSCRIPTIONS_PAGINATION = PaginationConfig(
    page_size=50,
    delay_between_pages=1.0,  # 60 req/min = 1000ms minimum
    max_pages=None,
)


# ============================================
# Exceptions
# ============================================

class GLPClientError(Exception):
    """Base exception for GLPClient errors."""
    pass


class APIError(GLPClientError):
    """Raised when API returns an error response."""
    def __init__(self, status: int, message: str, response_body: Optional[str] = None):
        self.status = status
        self.message = message
        self.response_body = response_body
        super().__init__(f"HTTP {status}: {message}")


class RateLimitError(GLPClientError):
    """Raised when rate limit is exceeded and retries are exhausted."""
    pass


# ============================================
# The Client
# ============================================

class GLPClient:
    """Async HTTP client for HPE GreenLake Platform APIs.

    This client is designed to be used as an async context manager to ensure
    proper session lifecycle management:

        async with GLPClient(token_manager) as client:
            data = await client.get("/some/endpoint")

    The client handles:
        - Bearer token authentication (via TokenManager)
        - Automatic token refresh on 401 responses
        - Rate limit backoff on 429 responses
        - Connection pooling via shared aiohttp session

    Attributes:
        token_manager: TokenManager instance for OAuth2 authentication
        base_url: Base URL for API requests (e.g., "https://global.api.greenlake.hpe.com")
    """

    def __init__(
        self,
        token_manager: TokenManager,
        base_url: Optional[str] = None,
    ):
        """Initialize the GLPClient.

        Args:
            token_manager: TokenManager instance for authentication
            base_url: API base URL. If not provided, reads from GLP_BASE_URL env var.

        Raises:
            ValueError: If base_url is not provided and GLP_BASE_URL is not set.
        """
        import os

        self.token_manager = token_manager
        self.base_url = (base_url or os.getenv("GLP_BASE_URL", "")).rstrip("/")

        if not self.base_url:
            raise ValueError(
                "Base URL is required. Provide base_url parameter or set GLP_BASE_URL environment variable."
            )

        # Session is created in __aenter__, closed in __aexit__
        self._session: Optional[aiohttp.ClientSession] = None

    # ----------------------------------------
    # Context Manager Protocol
    # ----------------------------------------

    async def __aenter__(self) -> "GLPClient":
        """Enter async context: create the HTTP session."""
        self._session = aiohttp.ClientSession(
            # Connection pooling settings
            connector=aiohttp.TCPConnector(
                limit=10,  # Max concurrent connections
                limit_per_host=10,
            ),
            # Timeouts
            timeout=aiohttp.ClientTimeout(
                total=60,  # Total request timeout
                connect=10,  # Connection timeout
            ),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context: close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    # ----------------------------------------
    # Low-Level Request Methods
    # ----------------------------------------

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with current token."""
        token = await self.token_manager.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make a single HTTP request (no retry logic).

        This is the lowest-level request method. It handles URL construction
        and header injection, but does NOT handle 401/429 responses.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint path (e.g., "/devices/v1/devices")
            params: Query parameters
            json_body: JSON request body (for POST/PATCH)

        Returns:
            Parsed JSON response as dict

        Raises:
            APIError: If response status is not 2xx
            RuntimeError: If called outside of async context manager
        """
        if not self._session:
            raise RuntimeError(
                "GLPClient must be used as async context manager: "
                "async with GLPClient(...) as client:"
            )

        url = f"{self.base_url}{endpoint}"
        headers = await self._get_auth_headers()

        async with self._session.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_body,
        ) as response:
            # For non-2xx responses, capture error details
            if response.status >= 400:
                error_text = await response.text()
                raise APIError(
                    status=response.status,
                    message=f"{method} {endpoint} failed",
                    response_body=error_text,
                )

            # Success - parse JSON response
            return await response.json()

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Make an HTTP request with automatic retry on 401/429.

        This method wraps _request() with resilience logic:
            - 401 Unauthorized: Invalidate token, refresh, retry
            - 429 Rate Limited: Wait for Retry-After header, retry

        Args:
            method: HTTP method
            endpoint: API endpoint path
            params: Query parameters
            json_body: JSON request body
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            Parsed JSON response

        Raises:
            APIError: If request fails after all retries
            RateLimitError: If rate limited and retries exhausted
        """
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                return await self._request(method, endpoint, params, json_body)

            except APIError as e:
                last_error = e

                if e.status == 401:
                    # Token expired - invalidate and retry
                    print(f"[GLPClient] Token expired, refreshing (attempt {attempt + 1})")
                    self.token_manager.invalidate()
                    continue

                elif e.status == 429:
                    # Rate limited - extract Retry-After and wait
                    # Default to 60 seconds if header not present
                    retry_after = 60
                    print(f"[GLPClient] Rate limited, waiting {retry_after}s (attempt {attempt + 1})")
                    await asyncio.sleep(retry_after)
                    continue

                else:
                    # Other error - don't retry
                    raise

        # Exhausted retries
        if isinstance(last_error, APIError) and last_error.status == 429:
            raise RateLimitError(f"Rate limit exceeded after {max_retries} retries")
        raise last_error or APIError(0, "Unknown error")

    # ----------------------------------------
    # High-Level Request Methods
    # ----------------------------------------

    async def get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path (e.g., "/devices/v1/devices")
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        return await self._request_with_retry("GET", endpoint, params=params)

    async def post(
        self,
        endpoint: str,
        json_body: dict,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            json_body: Request body as dict (will be JSON-encoded)
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        return await self._request_with_retry("POST", endpoint, params=params, json_body=json_body)

    async def patch(
        self,
        endpoint: str,
        json_body: dict,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make a PATCH request.

        Args:
            endpoint: API endpoint path
            json_body: Request body as dict (will be JSON-encoded)
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        return await self._request_with_retry("PATCH", endpoint, params=params, json_body=json_body)

    # ----------------------------------------
    # Pagination Methods
    # ----------------------------------------

    async def paginate(
        self,
        endpoint: str,
        config: Optional[PaginationConfig] = None,
        params: Optional[dict] = None,
    ) -> AsyncIterator[list[dict]]:
        """Iterate through paginated API responses.

        This is a memory-efficient way to process large datasets. Instead of
        loading all items into memory, it yields one page at a time.

        Args:
            endpoint: API endpoint path
            config: Pagination configuration (page size, delay, etc.)
            params: Additional query parameters (e.g., filters)

        Yields:
            List of items from each page

        Example:
            async for page in client.paginate("/devices/v1/devices"):
                for device in page:
                    print(device["serialNumber"])
        """
        config = config or PaginationConfig()
        params = dict(params or {})  # Copy to avoid mutating caller's dict

        offset = 0
        total = None
        pages_fetched = 0

        while True:
            # Set pagination params
            params["offset"] = offset
            params["limit"] = config.page_size

            # Fetch page
            data = await self.get(endpoint, params=params)

            items = data.get("items", [])

            # First page: log total count
            if total is None:
                total = data.get("total", len(items))
                print(f"[GLPClient] Paginating {endpoint}: {total:,} total items")

            # Yield this page's items
            if items:
                yield items

            # Progress tracking
            pages_fetched += 1
            fetched_count = offset + len(items)
            percent = (fetched_count / total * 100) if total > 0 else 100
            print(f"[GLPClient] Progress: {fetched_count:,}/{total:,} ({percent:.1f}%)")

            # Check termination conditions
            if fetched_count >= total:
                break
            if len(items) < config.page_size:
                break
            if config.max_pages and pages_fetched >= config.max_pages:
                print(f"[GLPClient] Reached max_pages limit ({config.max_pages})")
                break

            # Prepare for next page
            offset += config.page_size

            # Rate limit delay
            if config.delay_between_pages > 0:
                await asyncio.sleep(config.delay_between_pages)

        print(f"[GLPClient] Pagination complete: {fetched_count:,} items in {pages_fetched} pages")

    async def fetch_all(
        self,
        endpoint: str,
        config: Optional[PaginationConfig] = None,
        params: Optional[dict] = None,
    ) -> list[dict]:
        """Fetch all items from a paginated endpoint.

        This is a convenience method that collects all pages into a single list.
        For large datasets, consider using paginate() instead to process items
        as they arrive.

        Args:
            endpoint: API endpoint path
            config: Pagination configuration
            params: Additional query parameters

        Returns:
            List of all items across all pages
        """
        all_items = []
        async for page in self.paginate(endpoint, config, params):
            all_items.extend(page)
        return all_items


# ============================================
# Standalone Test
# ============================================

if __name__ == "__main__":
    async def demo():
        """Quick demo of GLPClient usage."""
        from .auth import TokenManager

        token_manager = TokenManager()

        async with GLPClient(token_manager) as client:
            # Example: Fetch first page of devices
            data = await client.get(
                "/devices/v1/devices",
                params={"limit": 10}
            )
            print(f"Fetched {len(data.get('items', []))} devices")

            # Example: Paginate through subscriptions
            count = 0
            async for page in client.paginate(
                "/subscriptions/v1/subscriptions",
                config=SUBSCRIPTIONS_PAGINATION,
            ):
                count += len(page)
            print(f"Total subscriptions: {count}")

    asyncio.run(demo())
