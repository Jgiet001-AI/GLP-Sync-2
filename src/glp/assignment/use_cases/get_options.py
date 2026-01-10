"""Get Options use case.

This use case retrieves available options for device assignments:
- Subscriptions (filtered by device type)
- Regions (mapped to application IDs)
- Existing tags
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..domain.entities import RegionMapping, SubscriptionOption
from ..domain.ports import IDeviceRepository, ISubscriptionRepository

logger = logging.getLogger(__name__)


@dataclass
class OptionsResult:
    """Result of GetOptionsUseCase."""

    subscriptions: list[SubscriptionOption] = field(default_factory=list)
    regions: list[RegionMapping] = field(default_factory=list)
    existing_tags: list[tuple[str, str]] = field(default_factory=list)


class GetOptionsUseCase:
    """Get available options for device assignments.

    This use case:
    1. Retrieves available subscriptions (optionally filtered by device type)
    2. Retrieves region mappings (application_id -> region name)
    3. Retrieves existing tags for autocomplete
    """

    def __init__(
        self,
        subscription_repo: ISubscriptionRepository,
        device_repo: IDeviceRepository,
    ):
        """Initialize the use case.

        Args:
            subscription_repo: Repository for subscription data
            device_repo: Repository for device/tag data
        """
        self.subscriptions = subscription_repo
        self.devices = device_repo

    async def execute(
        self,
        device_type: Optional[str] = None,
    ) -> OptionsResult:
        """Execute the use case.

        Args:
            device_type: Optional device type to filter subscriptions

        Returns:
            OptionsResult with available subscriptions, regions, and tags
        """
        logger.info(f"Getting options for device_type={device_type or 'all'}")

        # 1. Get available subscriptions
        all_subscriptions = await self.subscriptions.get_available_subscriptions(
            device_type=device_type
        )

        # Filter to only show subscriptions with available quantity
        available_subs = [s for s in all_subscriptions if s.available_quantity > 0]

        logger.info(
            f"Found {len(available_subs)} subscriptions with available capacity "
            f"(out of {len(all_subscriptions)} total)"
        )

        # 2. Get region mappings
        regions = await self.subscriptions.get_region_mappings()
        logger.info(f"Found {len(regions)} region mappings")

        # 3. Get existing tags for autocomplete
        existing_tags = await self.devices.get_all_tags()
        logger.info(f"Found {len(existing_tags)} unique tag key-value pairs")

        return OptionsResult(
            subscriptions=available_subs,
            regions=regions,
            existing_tags=existing_tags,
        )

    async def get_subscriptions_for_device_type(
        self,
        device_type: str,
    ) -> list[SubscriptionOption]:
        """Get subscriptions compatible with a specific device type.

        Args:
            device_type: Device type (NETWORK, COMPUTE, STORAGE)

        Returns:
            List of compatible subscriptions with available quantity
        """
        all_subs = await self.subscriptions.get_available_subscriptions()

        compatible = [
            s
            for s in all_subs
            if s.is_compatible_with(device_type) and s.available_quantity > 0
        ]

        logger.info(
            f"Found {len(compatible)} compatible subscriptions for {device_type}"
        )

        return compatible
