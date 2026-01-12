"""GLP API adapter for fetching devices from GreenLake Platform.

This adapter implements IDeviceAPI and wraps the existing GLPClient
to provide device-specific API operations.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..domain.ports import IDeviceAPI, ISubscriptionAPI

if TYPE_CHECKING:
    from ...api.client import GLPClient, PaginationConfig


class GLPDeviceAPI(IDeviceAPI):
    """GreenLake Platform API adapter for device operations.

    Wraps GLPClient to provide device-specific fetch operations.
    Uses DEVICES_PAGINATION config for optimal page sizes and rate limiting.
    """

    # API endpoint for devices
    ENDPOINT = "/devices/v1/devices"

    def __init__(
        self,
        client: "GLPClient",
        pagination_config: "PaginationConfig | None" = None,
    ):
        """Initialize the API adapter.

        Args:
            client: Configured GLPClient instance
            pagination_config: Optional pagination config override.
                             Defaults to DEVICES_PAGINATION if not provided.
        """
        self.client = client
        self._pagination_config = pagination_config

    @property
    def pagination_config(self) -> "PaginationConfig":
        """Get pagination config, importing default if needed."""
        if self._pagination_config is None:
            from ...api.client import DEVICES_PAGINATION
            self._pagination_config = DEVICES_PAGINATION
        return self._pagination_config

    async def fetch_all(self) -> list[dict[str, Any]]:
        """Fetch all devices from GreenLake API.

        Uses DEVICES_PAGINATION config:
        - page_size: 2000 (API maximum)
        - delay: 0.5s between pages (respects 160 req/min limit)

        Returns:
            List of device dictionaries from the API
        """
        return await self.client.fetch_all(
            self.ENDPOINT,
            config=self.pagination_config,
        )

    async def fetch_paginated(self) -> AsyncIterator[list[dict[str, Any]]]:
        """Fetch devices page by page (memory efficient).

        Use this for very large datasets where you want to process
        devices as they arrive rather than loading all into memory.

        Yields:
            Lists of device dictionaries, one page at a time
        """
        async for page in self.client.paginate(
            self.ENDPOINT,
            config=self.pagination_config,
        ):
            yield page


class GLPSubscriptionAPI(ISubscriptionAPI):
    """GreenLake Platform API adapter for subscription operations.

    Wraps GLPClient to provide subscription-specific fetch operations.
    Uses SUBSCRIPTIONS_PAGINATION config for optimal page sizes and rate limiting.
    Supports OData-style filtering for expiry and status queries.
    """

    # API endpoint for subscriptions
    ENDPOINT = "/subscriptions/v1/subscriptions"

    def __init__(
        self,
        client: "GLPClient",
        pagination_config: "PaginationConfig | None" = None,
    ):
        """Initialize the API adapter.

        Args:
            client: Configured GLPClient instance
            pagination_config: Optional pagination config override.
                             Defaults to SUBSCRIPTIONS_PAGINATION if not provided.
        """
        self.client = client
        self._pagination_config = pagination_config

    @property
    def pagination_config(self) -> "PaginationConfig":
        """Get pagination config, importing default if needed."""
        if self._pagination_config is None:
            from ...api.client import SUBSCRIPTIONS_PAGINATION
            self._pagination_config = SUBSCRIPTIONS_PAGINATION
        return self._pagination_config

    async def fetch_all(self) -> list[dict[str, Any]]:
        """Fetch all subscriptions from GreenLake API.

        Uses SUBSCRIPTIONS_PAGINATION config:
        - page_size: 50 (API maximum)
        - delay: 1.0s between pages (respects 60 req/min limit)

        Returns:
            List of subscription dictionaries from the API
        """
        return await self.client.fetch_all(
            self.ENDPOINT,
            config=self.pagination_config,
        )

    async def fetch_paginated(self) -> AsyncIterator[list[dict[str, Any]]]:
        """Fetch subscriptions page by page (memory efficient).

        Use this for very large datasets where you want to process
        subscriptions as they arrive rather than loading all into memory.

        Yields:
            Lists of subscription dictionaries, one page at a time
        """
        async for page in self.client.paginate(
            self.ENDPOINT,
            config=self.pagination_config,
        ):
            yield page

    async def fetch_expiring_soon(self, days: int) -> list[dict[str, Any]]:
        """Fetch subscriptions expiring within N days.

        Uses the API's OData filter capability to only fetch relevant
        subscriptions, rather than fetching everything and filtering locally.

        Args:
            days: Number of days to look ahead

        Returns:
            List of subscriptions expiring within the specified window
        """
        from datetime import datetime, timedelta

        # Calculate the cutoff date
        cutoff = datetime.utcnow() + timedelta(days=days)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT00:00:00.000Z")
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT00:00:00.000Z")

        # Build OData filter:
        # - Subscription is active (STARTED)
        # - End time is in the future (not already expired)
        # - End time is before our cutoff
        filter_expr = (
            f"subscriptionStatus eq 'STARTED' "
            f"and endTime gt '{now_iso}' "
            f"and endTime lt '{cutoff_iso}'"
        )

        return await self.client.fetch_all(
            self.ENDPOINT,
            config=self.pagination_config,
            params={"filter": filter_expr, "sort": "endTime asc"},
        )

    async def fetch_by_status(self, status: str) -> list[dict[str, Any]]:
        """Fetch subscriptions by status.

        Args:
            status: Subscription status (e.g., STARTED, ENDED, SUSPENDED)

        Returns:
            List of subscriptions with the specified status
        """
        filter_expr = f"subscriptionStatus eq '{status}'"

        return await self.client.fetch_all(
            self.ENDPOINT,
            config=self.pagination_config,
            params={"filter": filter_expr},
        )
