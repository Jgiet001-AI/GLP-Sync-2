#!/usr/bin/env python3
"""Generic HTTP Client for HPE GreenLake Platform APIs.

This module provides a reusable, composable HTTP client that handles the
common concerns of GreenLake API communication:

    - OAuth2 authentication via TokenManager
    - Automatic token refresh on 401 responses
    - Rate limit handling with exponential backoff on 429 responses
    - Offset-based pagination with configurable page sizes
    - Connection pooling via shared aiohttp session
    - Circuit breaker for resilience against API outages
    - Comprehensive error handling with typed exceptions

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
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import aiohttp

from .auth import TokenManager
from .exceptions import (
    APIError,
    CircuitOpenError,
    ConfigurationError,
    ConnectionError,
    GLPError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    TokenExpiredError,
    ValidationError,
)
from .resilience import CircuitBreaker

logger = logging.getLogger(__name__)

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
# Backward Compatibility Aliases
# ============================================

# These are now imported from exceptions.py but aliased here for compatibility
GLPClientError = GLPError


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
        enable_circuit_breaker: bool = True,
        circuit_failure_threshold: int = 5,
        circuit_timeout: float = 60.0,
    ):
        """Initialize the GLPClient.

        Args:
            token_manager: TokenManager instance for authentication
            base_url: API base URL. If not provided, reads from GLP_BASE_URL env var.
            enable_circuit_breaker: Enable circuit breaker for resilience
            circuit_failure_threshold: Failures before circuit opens
            circuit_timeout: Seconds before circuit attempts to close

        Raises:
            ConfigurationError: If base_url is not provided and GLP_BASE_URL is not set.
        """
        import os

        self.token_manager = token_manager
        self.base_url = (base_url or os.getenv("GLP_BASE_URL", "")).rstrip("/")

        if not self.base_url:
            raise ConfigurationError(
                "Base URL is required. Provide base_url parameter or set GLP_BASE_URL environment variable.",
                missing_keys=["GLP_BASE_URL"],
            )

        # Session is created in __aenter__, closed in __aexit__
        self._session: Optional[aiohttp.ClientSession] = None

        # Circuit breaker for resilience
        self._circuit_breaker: Optional[CircuitBreaker] = None
        if enable_circuit_breaker:
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=circuit_failure_threshold,
                timeout=circuit_timeout,
                name="glp_api",
            )

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
            ConnectionError: If connection to server fails
            TimeoutError: If request times out
        """
        if not self._session:
            raise RuntimeError(
                "GLPClient must be used as async context manager: "
                "async with GLPClient(...) as client:"
            )

        url = f"{self.base_url}{endpoint}"

        try:
            headers = await self._get_auth_headers()

            async with self._session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
            ) as response:
                # Handle specific error statuses with typed exceptions
                if response.status >= 400:
                    error_text = await response.text()
                    raise self._create_api_error(
                        status=response.status,
                        method=method,
                        endpoint=endpoint,
                        response_body=error_text,
                    )

                # Success - parse JSON response
                return await response.json()

        except aiohttp.ClientConnectionError as e:
            raise ConnectionError(
                f"Failed to connect to {self.base_url}",
                host=self.base_url,
                cause=e,
            )

        except asyncio.TimeoutError as e:
            raise TimeoutError(
                f"Request to {endpoint} timed out",
                timeout_seconds=60,
                cause=e,
            )

        except aiohttp.ClientError as e:
            raise NetworkError(
                f"Network error during {method} {endpoint}: {e}",
                cause=e,
            )

    def _create_api_error(
        self,
        status: int,
        method: str,
        endpoint: str,
        response_body: str,
    ) -> APIError:
        """Create appropriate APIError subclass based on status code."""
        if status == 401:
            return TokenExpiredError(
                "Access token expired or invalid",
                details={"endpoint": endpoint},
            )

        if status == 404:
            return NotFoundError(
                resource_type="Resource",
                resource_id=endpoint,
                endpoint=endpoint,
                response_body=response_body,
            )

        if status == 429:
            # Try to extract Retry-After header value from response
            retry_after = 60  # Default
            return RateLimitError(
                f"Rate limit exceeded for {endpoint}",
                retry_after=retry_after,
                endpoint=endpoint,
                response_body=response_body,
            )

        if status == 400 or status == 422:
            return ValidationError(
                f"Validation failed for {method} {endpoint}",
                status_code=status,
                endpoint=endpoint,
                response_body=response_body,
            )

        if status >= 500:
            return ServerError(
                f"Server error ({status}) for {method} {endpoint}",
                status_code=status,
                endpoint=endpoint,
                response_body=response_body,
            )

        # Generic API error for other status codes
        return APIError(
            f"{method} {endpoint} failed",
            status_code=status,
            endpoint=endpoint,
            method=method,
            response_body=response_body,
        )

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Make an HTTP request with automatic retry and circuit breaker.

        This method wraps _request() with resilience logic:
            - Circuit breaker: Fail fast if API is down
            - 401 Unauthorized: Invalidate token, refresh, retry
            - 429 Rate Limited: Wait for Retry-After header, retry
            - 5xx Server Errors: Exponential backoff retry
            - Network errors: Exponential backoff retry

        Args:
            method: HTTP method
            endpoint: API endpoint path
            params: Query parameters
            json_body: JSON request body
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            Parsed JSON response

        Raises:
            CircuitOpenError: If circuit breaker is open
            APIError: If request fails after all retries
            RateLimitError: If rate limited and retries exhausted
            NetworkError: If network error persists after retries
        """
        # Check circuit breaker first
        if self._circuit_breaker and self._circuit_breaker.is_open:
            # Check if we should attempt (timeout may have passed)
            if not self._circuit_breaker._should_attempt():
                raise CircuitOpenError(
                    "Circuit breaker is open for GLP API",
                    failure_count=self._circuit_breaker.failure_count,
                )

        last_error: Optional[Exception] = None
        backoff_delay = 1.0  # Initial backoff delay

        for attempt in range(1, max_retries + 1):
            try:
                result = await self._request(method, endpoint, params, json_body)

                # Success - reset circuit breaker
                if self._circuit_breaker:
                    await self._circuit_breaker._on_success()

                return result

            except TokenExpiredError:
                # Token expired - invalidate and retry (no backoff needed)
                logger.warning(f"Token expired, refreshing (attempt {attempt})")
                self.token_manager.invalidate()
                continue

            except RateLimitError as e:
                last_error = e
                # Rate limited - wait for specified time
                wait_time = e.retry_after
                logger.warning(
                    f"Rate limited, waiting {wait_time}s (attempt {attempt}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
                continue

            except ServerError as e:
                last_error = e
                # Server error - exponential backoff
                if attempt < max_retries:
                    logger.warning(
                        f"Server error {e.status_code}, retrying in {backoff_delay}s "
                        f"(attempt {attempt}/{max_retries})"
                    )
                    await asyncio.sleep(backoff_delay)
                    backoff_delay = min(backoff_delay * 2, 60.0)  # Cap at 60s
                    continue

                # Update circuit breaker on final failure
                if self._circuit_breaker:
                    await self._circuit_breaker._on_failure(e)
                raise

            except (NetworkError, ConnectionError, TimeoutError) as e:
                last_error = e
                # Network error - exponential backoff
                if attempt < max_retries:
                    logger.warning(
                        f"Network error: {e}. Retrying in {backoff_delay}s "
                        f"(attempt {attempt}/{max_retries})"
                    )
                    await asyncio.sleep(backoff_delay)
                    backoff_delay = min(backoff_delay * 2, 60.0)
                    continue

                # Update circuit breaker on final failure
                if self._circuit_breaker:
                    await self._circuit_breaker._on_failure(e)
                raise

            except (NotFoundError, ValidationError):
                # Non-retryable errors - fail immediately
                raise

            except APIError as e:
                # Other API errors - check if retryable
                if e.recoverable and attempt < max_retries:
                    last_error = e
                    logger.warning(
                        f"API error (recoverable): {e}. Retrying in {backoff_delay}s"
                    )
                    await asyncio.sleep(backoff_delay)
                    backoff_delay = min(backoff_delay * 2, 60.0)
                    continue

                # Update circuit breaker and re-raise
                if self._circuit_breaker:
                    await self._circuit_breaker._on_failure(e)
                raise

        # Exhausted retries
        if self._circuit_breaker and last_error:
            await self._circuit_breaker._on_failure(last_error)

        if last_error:
            raise last_error

        raise APIError(
            "Request failed after all retries",
            status_code=0,
            endpoint=endpoint,
            method=method,
        )

    @property
    def circuit_status(self) -> Optional[dict[str, Any]]:
        """Get circuit breaker status for monitoring."""
        if self._circuit_breaker:
            return self._circuit_breaker.get_status()
        return None

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
                logger.info(f"Paginating {endpoint}: {total:,} total items")

            # Yield this page's items
            if items:
                yield items

            # Progress tracking
            pages_fetched += 1
            fetched_count = offset + len(items)
            percent = (fetched_count / total * 100) if total > 0 else 100
            logger.debug(f"Progress: {fetched_count:,}/{total:,} ({percent:.1f}%)")

            # Check termination conditions
            if fetched_count >= total:
                break
            if len(items) < config.page_size:
                break
            if config.max_pages and pages_fetched >= config.max_pages:
                logger.info(f"Reached max_pages limit ({config.max_pages})")
                break

            # Prepare for next page
            offset += config.page_size

            # Rate limit delay
            if config.delay_between_pages > 0:
                await asyncio.sleep(config.delay_between_pages)

        logger.info(f"Pagination complete: {fetched_count:,} items in {pages_fetched} pages")

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
