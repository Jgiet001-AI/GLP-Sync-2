#!/usr/bin/env python3
"""HTTP Client for Aruba Central APIs.

This module provides a reusable, composable HTTP client that handles the
common concerns of Aruba Central API communication:

    - OAuth2 authentication via ArubaTokenManager
    - Automatic token refresh on 401 responses
    - Rate limit handling with backoff (X-RateLimit headers)
    - Cursor-based pagination (uses 'next' token)
    - Connection pooling via shared aiohttp session
    - Circuit breaker for resilience against API outages
    - Comprehensive error handling with typed exceptions

Design Philosophy:
    This client knows HOW to talk to Aruba Central, but not WHAT to fetch.
    It has no knowledge of devices, sites, or any specific resource.
    That knowledge belongs in the Syncer classes that compose this client.

Key Differences from GLPClient:
    - Cursor-based pagination (next token) instead of offset-based
    - Maximum page size of 100 (vs 2000 for GreenLake)
    - Region-specific base URLs
    - Rate limit headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset

Usage:
    async with ArubaCentralClient(token_manager) as client:
        # Single request
        data = await client.get("/network-monitoring/v1alpha1/device-inventory")

        # Paginated fetch (memory efficient)
        async for page in client.paginate("/network-monitoring/v1alpha1/device-inventory"):
            for item in page:
                process(item)

Author: HPE GreenLake Team
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import aiohttp

from .aruba_auth import ArubaTokenManager
from .exceptions import (
    APIError,
    CircuitOpenError,
    ConfigurationError,
    ConnectionError,
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
class ArubaPaginationConfig:
    """Configuration for Aruba Central paginated API requests.

    Attributes:
        page_size: Number of items per request (max 100 for Aruba Central)
        delay_between_pages: Seconds to wait between requests (rate limiting)
        max_pages: Safety limit to prevent infinite loops (None = no limit)
    """
    page_size: int = 100  # Aruba Central API maximum
    delay_between_pages: float = 0.5
    max_pages: Optional[int] = None


# Pre-configured settings for known Aruba APIs
ARUBA_DEVICES_PAGINATION = ArubaPaginationConfig(
    page_size=100,  # API maximum
    delay_between_pages=0.5,
    max_pages=None,
)


@dataclass
class RateLimitInfo:
    """Rate limit information from Aruba Central API headers.

    Attributes:
        limit: Maximum requests allowed per hour
        remaining: Requests remaining in current window
        reset_at: When the rate limit window resets (timezone-aware UTC)
    """
    limit: int
    remaining: int
    reset_at: Optional[datetime] = None

    @property
    def is_near_limit(self) -> bool:
        """Check if we're approaching the rate limit (< 10% remaining)."""
        return self.remaining < (self.limit * 0.1)

    @property
    def seconds_until_reset(self) -> float:
        """Seconds until rate limit resets (0 if unknown or past)."""
        if not self.reset_at:
            return 0
        # Use timezone-aware now for comparison
        from datetime import timezone
        now = datetime.now(timezone.utc)
        # Ensure reset_at is also timezone-aware
        reset_at = self.reset_at
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        delta = reset_at - now
        return max(0, delta.total_seconds())


# ============================================
# The Client
# ============================================

class ArubaCentralClient:
    """Async HTTP client for Aruba Central APIs.

    This client is designed to be used as an async context manager to ensure
    proper session lifecycle management:

        async with ArubaCentralClient(token_manager) as client:
            data = await client.get("/some/endpoint")

    The client handles:
        - Bearer token authentication (via ArubaTokenManager)
        - Automatic token refresh on 401 responses
        - Rate limit backoff on 429 responses (reads X-RateLimit headers)
        - Connection pooling via shared aiohttp session
        - Circuit breaker for resilience

    Attributes:
        token_manager: ArubaTokenManager instance for OAuth2 authentication
        base_url: Base URL for API requests (region-specific)
    """

    def __init__(
        self,
        token_manager: ArubaTokenManager,
        base_url: Optional[str] = None,
        enable_circuit_breaker: bool = True,
        circuit_failure_threshold: int = 5,
        circuit_timeout: float = 60.0,
    ):
        """Initialize the ArubaCentralClient.

        Args:
            token_manager: ArubaTokenManager instance for authentication
            base_url: API base URL (region-specific, e.g., us1.api.central.arubanetworks.com).
                      If not provided, reads from ARUBA_BASE_URL env var.
            enable_circuit_breaker: Enable circuit breaker for resilience
            circuit_failure_threshold: Failures before circuit opens
            circuit_timeout: Seconds before circuit attempts to close

        Raises:
            ConfigurationError: If base_url is not provided and ARUBA_BASE_URL is not set.
        """
        import os

        self.token_manager = token_manager
        self.base_url = (base_url or os.getenv("ARUBA_BASE_URL", "")).rstrip("/")

        if not self.base_url:
            raise ConfigurationError(
                "Aruba Central base URL is required. "
                "Provide base_url parameter or set ARUBA_BASE_URL environment variable. "
                "Example: https://us1.api.central.arubanetworks.com",
                missing_keys=["ARUBA_BASE_URL"],
            )

        # Session is created in __aenter__, closed in __aexit__
        self._session: Optional[aiohttp.ClientSession] = None

        # Track rate limit info from last response
        self._last_rate_limit: Optional[RateLimitInfo] = None

        # Circuit breaker for resilience
        self._circuit_breaker: Optional[CircuitBreaker] = None
        if enable_circuit_breaker:
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=circuit_failure_threshold,
                timeout=circuit_timeout,
                name="aruba_central_api",
            )

    # ----------------------------------------
    # Context Manager Protocol
    # ----------------------------------------

    async def __aenter__(self) -> "ArubaCentralClient":
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
    # Rate Limit Handling
    # ----------------------------------------

    def _extract_rate_limit_info(self, headers: dict) -> Optional[RateLimitInfo]:
        """Extract rate limit info from response headers.

        Aruba Central uses headers:
            - X-RateLimit-Limit: requests per hour
            - X-RateLimit-Remaining: requests left in window
            - X-RateLimit-Reset: datetime when window resets (ISO or epoch)
        """
        from datetime import timezone

        try:
            limit = int(headers.get("X-RateLimit-Limit", 0))
            remaining = int(headers.get("X-RateLimit-Remaining", 0))
            reset_str = headers.get("X-RateLimit-Reset")

            reset_at = None
            if reset_str:
                # Try ISO format first (with timezone)
                try:
                    reset_at = datetime.fromisoformat(reset_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

                # Try epoch timestamp if ISO failed
                if reset_at is None:
                    try:
                        epoch = float(reset_str)
                        reset_at = datetime.fromtimestamp(epoch, tz=timezone.utc)
                    except (ValueError, OSError):
                        pass

            if limit > 0:
                return RateLimitInfo(
                    limit=limit,
                    remaining=remaining,
                    reset_at=reset_at,
                )
        except (ValueError, TypeError):
            pass

        return None

    async def _handle_rate_limit(self, rate_info: Optional[RateLimitInfo]) -> None:
        """Handle rate limiting by waiting if near limit."""
        if not rate_info:
            return

        self._last_rate_limit = rate_info

        if rate_info.is_near_limit:
            wait_time = min(rate_info.seconds_until_reset, 60)  # Cap at 60s
            if wait_time > 0:
                logger.warning(
                    f"Aruba Central rate limit near ({rate_info.remaining}/{rate_info.limit}). "
                    f"Waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)

    # ----------------------------------------
    # Low-Level Request Methods
    # ----------------------------------------

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with current token."""
        token = await self.token_manager.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
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
            endpoint: API endpoint path (e.g., "/network-monitoring/v1alpha1/device-inventory")
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
                "ArubaCentralClient must be used as async context manager: "
                "async with ArubaCentralClient(...) as client:"
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
                # Extract rate limit info from headers
                rate_info = self._extract_rate_limit_info(dict(response.headers))
                if rate_info:
                    self._last_rate_limit = rate_info

                # Handle specific error statuses with typed exceptions
                if response.status >= 400:
                    error_text = await response.text()
                    raise self._create_api_error(
                        status=response.status,
                        method=method,
                        endpoint=endpoint,
                        response_body=error_text,
                        rate_info=rate_info,
                    )

                # Success - parse JSON response
                return await response.json()

        except aiohttp.ClientConnectionError as e:
            raise ConnectionError(
                f"Failed to connect to Aruba Central at {self.base_url}",
                host=self.base_url,
                cause=e,
            )

        except asyncio.TimeoutError as e:
            raise TimeoutError(
                f"Aruba Central request to {endpoint} timed out",
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
        rate_info: Optional[RateLimitInfo] = None,
    ) -> APIError:
        """Create appropriate APIError subclass based on status code."""
        if status == 401:
            return TokenExpiredError(
                "Aruba Central access token expired or invalid",
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
            # Use rate limit info if available
            retry_after = 60  # Default
            if rate_info:
                retry_after = int(rate_info.seconds_until_reset) or 60

            return RateLimitError(
                f"Aruba Central rate limit exceeded for {endpoint}",
                retry_after=retry_after,
                endpoint=endpoint,
                response_body=response_body,
            )

        if status == 400 or status == 422:
            return ValidationError(
                f"Aruba Central validation failed for {method} {endpoint}",
                status_code=status,
                endpoint=endpoint,
                response_body=response_body,
            )

        if status >= 500:
            return ServerError(
                f"Aruba Central server error ({status}) for {method} {endpoint}",
                status_code=status,
                endpoint=endpoint,
                response_body=response_body,
            )

        # Generic API error for other status codes
        return APIError(
            f"Aruba Central {method} {endpoint} failed",
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
            - 429 Rate Limited: Wait for Retry-After, retry
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
            if not self._circuit_breaker._should_attempt():
                raise CircuitOpenError(
                    "Circuit breaker is open for Aruba Central API",
                    failure_count=self._circuit_breaker.failure_count,
                )

        last_error: Optional[Exception] = None
        backoff_delay = 1.0  # Initial backoff delay

        for attempt in range(1, max_retries + 1):
            try:
                # Check rate limit before request
                await self._handle_rate_limit(self._last_rate_limit)

                result = await self._request(method, endpoint, params, json_body)

                # Success - reset circuit breaker
                if self._circuit_breaker:
                    await self._circuit_breaker._on_success()

                return result

            except TokenExpiredError:
                # Token expired - invalidate and retry (no backoff needed)
                logger.warning(f"Aruba Central token expired, refreshing (attempt {attempt})")
                self.token_manager.invalidate()
                continue

            except RateLimitError as e:
                last_error = e
                # Rate limited - wait for specified time
                wait_time = e.retry_after
                logger.warning(
                    f"Aruba Central rate limited, waiting {wait_time}s "
                    f"(attempt {attempt}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
                continue

            except ServerError as e:
                last_error = e
                # Server error - exponential backoff
                if attempt < max_retries:
                    logger.warning(
                        f"Aruba Central server error {e.status_code}, "
                        f"retrying in {backoff_delay}s (attempt {attempt}/{max_retries})"
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
                        f"Aruba Central network error: {e}. "
                        f"Retrying in {backoff_delay}s (attempt {attempt}/{max_retries})"
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
                        f"Aruba Central API error (recoverable): {e}. "
                        f"Retrying in {backoff_delay}s"
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
            "Aruba Central request failed after all retries",
            status_code=0,
            endpoint=endpoint,
            method=method,
        )

    @property
    def rate_limit_info(self) -> Optional[RateLimitInfo]:
        """Get the last known rate limit info."""
        return self._last_rate_limit

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
            endpoint: API endpoint path
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
        return await self._request_with_retry(
            "POST", endpoint, params=params, json_body=json_body
        )

    # ----------------------------------------
    # Pagination Methods (Cursor-based)
    # ----------------------------------------

    async def paginate(
        self,
        endpoint: str,
        config: Optional[ArubaPaginationConfig] = None,
        params: Optional[dict] = None,
    ) -> AsyncIterator[list[dict]]:
        """Iterate through cursor-paginated API responses.

        This is a memory-efficient way to process large datasets. Instead of
        loading all items into memory, it yields one page at a time.

        Aruba Central uses cursor-based pagination with a 'next' token.

        Args:
            endpoint: API endpoint path
            config: Pagination configuration (page size, delay, etc.)
            params: Additional query parameters (e.g., filters)

        Yields:
            List of items from each page

        Example:
            async for page in client.paginate("/network-monitoring/v1alpha1/device-inventory"):
                for device in page:
                    print(device["serialNumber"])
        """
        config = config or ArubaPaginationConfig()
        params = dict(params or {})  # Copy to avoid mutating caller's dict

        # Set page size
        params["limit"] = config.page_size

        pages_fetched = 0
        total_items = 0
        total = None
        next_cursor: Optional[str] = None

        while True:
            # Add cursor for subsequent pages
            if next_cursor:
                params["next"] = next_cursor
            elif "next" in params:
                # Remove 'next' param for first page
                del params["next"]

            # Fetch page
            data = await self.get(endpoint, params=params)

            # Extract items - Aruba Central uses 'items' key
            items = data.get("items", [])

            # First page: log total count if available
            if total is None:
                total = data.get("total")
                if total:
                    logger.info(f"Paginating Aruba Central {endpoint}: {total:,} total items")

            # Yield this page's items
            if items:
                yield items
                total_items += len(items)

            # Progress tracking
            pages_fetched += 1
            if total and total > 0:
                percent = (total_items / total * 100)
                logger.debug(f"Aruba Central progress: {total_items:,}/{total:,} ({percent:.1f}%)")

            # Get cursor for next page
            next_cursor = data.get("next")

            # Termination conditions
            # 1. No next cursor means we're done
            if not next_cursor:
                break

            # 2. Max pages limit reached
            if config.max_pages and pages_fetched >= config.max_pages:
                logger.info(f"Reached max_pages limit ({config.max_pages})")
                break

            # Rate limit delay between pages
            if config.delay_between_pages > 0:
                await asyncio.sleep(config.delay_between_pages)

        logger.info(
            f"Aruba Central pagination complete: {total_items:,} items in {pages_fetched} pages"
        )

    async def fetch_all(
        self,
        endpoint: str,
        config: Optional[ArubaPaginationConfig] = None,
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
        """Quick demo of ArubaCentralClient usage."""
        from .aruba_auth import ArubaTokenManager

        token_manager = ArubaTokenManager()

        async with ArubaCentralClient(token_manager) as client:
            # Example: Fetch first page of devices
            data = await client.get(
                "/network-monitoring/v1alpha1/device-inventory",
                params={"limit": 10}
            )
            print(f"Fetched {len(data.get('items', []))} devices")
            print(f"Rate limit info: {client.rate_limit_info}")

            # Example: Paginate through devices
            count = 0
            async for page in client.paginate(
                "/network-monitoring/v1alpha1/device-inventory",
                config=ARUBA_DEVICES_PAGINATION,
            ):
                count += len(page)
            print(f"Total devices: {count}")

    asyncio.run(demo())
