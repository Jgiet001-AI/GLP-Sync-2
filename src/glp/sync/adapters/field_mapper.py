"""Field mapper adapter for transforming between API, domain, and DB formats.

This adapter implements IFieldMapper and encapsulates all field transformation
logic that was previously embedded in DeviceSyncer._prepare_device_records().
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from ..domain.entities import Device, DeviceSubscription, DeviceTag, Subscription, SubscriptionTag
from ..domain.ports import IFieldMapper, ISubscriptionFieldMapper


class DeviceFieldMapper(IFieldMapper):
    """Maps GreenLake device API responses to domain entities and DB records.

    This class handles:
    - API response parsing and field extraction
    - Nested object flattening (application, location, dedicatedPlatformWorkspace)
    - Timestamp parsing (ISO 8601 with Z suffix)
    - Type conversions (str -> UUID, etc.)
    - Subscription and tag extraction
    """

    def map_to_entity(self, raw: dict[str, Any]) -> Device:
        """Transform API response dictionary to Device entity.

        Args:
            raw: Raw device dictionary from GreenLake API

        Returns:
            Device domain entity with all fields populated
        """
        # Extract nested objects
        application = raw.get("application") or {}
        location = raw.get("location") or {}
        dedicated = raw.get("dedicatedPlatformWorkspace") or {}

        return Device(
            id=UUID(raw["id"]),
            mac_address=raw.get("macAddress"),
            serial_number=raw.get("serialNumber"),
            part_number=raw.get("partNumber"),
            device_type=raw.get("deviceType"),
            model=raw.get("model"),
            region=raw.get("region"),
            archived=raw.get("archived", False),
            device_name=raw.get("deviceName"),
            secondary_name=raw.get("secondaryName"),
            assigned_state=raw.get("assignedState"),
            resource_type=raw.get("type"),  # API uses "type", we use "resource_type"
            tenant_workspace_id=raw.get("tenantWorkspaceId"),
            application_id=application.get("id"),
            application_resource_uri=application.get("resourceUri"),
            dedicated_platform_id=dedicated.get("id"),
            location_id=location.get("id"),
            location_name=location.get("locationName"),
            location_city=location.get("city"),
            location_state=location.get("state"),
            location_country=location.get("country"),
            location_postal_code=location.get("postalCode"),
            location_street_address=location.get("streetAddress"),
            location_latitude=location.get("latitude"),
            location_longitude=location.get("longitude"),
            location_source=location.get("locationSource"),
            created_at=self._parse_timestamp(raw.get("createdAt")),
            updated_at=self._parse_timestamp(raw.get("updatedAt")),
            raw_data=raw,
        )

    def map_to_record(self, device: Device) -> tuple[Any, ...]:
        """Transform Device entity to database record tuple.

        The tuple ordering matches the INSERT statement in PostgresDeviceRepository:
        (id, mac_address, serial_number, part_number, device_type, model, region,
         archived, device_name, secondary_name, assigned_state, resource_type,
         tenant_workspace_id, application_id, application_resource_uri,
         dedicated_platform_id, location_id, location_name, location_city,
         location_state, location_country, location_postal_code,
         location_street_address, location_latitude, location_longitude,
         location_source, created_at, updated_at, raw_data)

        Args:
            device: Device domain entity

        Returns:
            Tuple of 29 values ready for database insertion
        """
        return (
            str(device.id),  # UUID as string for asyncpg
            device.mac_address,
            device.serial_number,
            device.part_number,
            device.device_type,
            device.model,
            device.region,
            device.archived,
            device.device_name,
            device.secondary_name,
            device.assigned_state,
            device.resource_type,
            device.tenant_workspace_id,
            device.application_id,
            device.application_resource_uri,
            device.dedicated_platform_id,
            device.location_id,
            device.location_name,
            device.location_city,
            device.location_state,
            device.location_country,
            device.location_postal_code,
            device.location_street_address,
            device.location_latitude,
            device.location_longitude,
            device.location_source,
            device.created_at,
            device.updated_at,
            json.dumps(device.raw_data),  # JSONB requires JSON string
        )

    def extract_subscriptions(
        self,
        device: Device,
        raw: dict[str, Any],
    ) -> list[DeviceSubscription]:
        """Extract subscription relationships from device data.

        The API returns subscriptions as a list under the "subscription" key
        (note: singular, even though it's a list).

        Args:
            device: Device entity (provides device_id)
            raw: Raw device dictionary from API

        Returns:
            List of DeviceSubscription entities
        """
        subscriptions = []
        raw_subs = raw.get("subscription") or []

        for sub in raw_subs:
            sub_id = sub.get("id")
            if sub_id:
                subscriptions.append(
                    DeviceSubscription(
                        device_id=device.id,
                        subscription_id=UUID(sub_id),
                        resource_uri=sub.get("resourceUri"),
                    )
                )

        return subscriptions

    def extract_tags(
        self,
        device: Device,
        raw: dict[str, Any],
    ) -> list[DeviceTag]:
        """Extract tags from device data.

        Tags are stored as a dictionary under the "tags" key.

        Args:
            device: Device entity (provides device_id)
            raw: Raw device dictionary from API

        Returns:
            List of DeviceTag entities
        """
        tags = []
        raw_tags = raw.get("tags") or {}

        for key, value in raw_tags.items():
            tags.append(
                DeviceTag(
                    device_id=device.id,
                    tag_key=key,
                    tag_value=str(value) if value is not None else "",
                )
            )

        return tags

    @staticmethod
    def _parse_timestamp(iso_string: str | None) -> datetime | None:
        """Parse ISO 8601 timestamp string to datetime.

        Handles the 'Z' suffix that Python's fromisoformat doesn't like
        before Python 3.11.

        Args:
            iso_string: ISO 8601 formatted timestamp string (may end with 'Z')

        Returns:
            datetime object or None if input is None/empty
        """
        if not iso_string:
            return None
        # Replace 'Z' with '+00:00' for Python < 3.11 compatibility
        return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))


class SubscriptionFieldMapper(ISubscriptionFieldMapper):
    """Maps GreenLake subscription API responses to domain entities and DB records.

    This class handles:
    - API response parsing and field extraction
    - Timestamp parsing (ISO 8601 with Z suffix)
    - Type conversions (str -> UUID, str -> int, etc.)
    - Tag extraction
    """

    def map_to_entity(self, raw: dict[str, Any]) -> Subscription:
        """Transform API response dictionary to Subscription entity.

        Args:
            raw: Raw subscription dictionary from GreenLake API

        Returns:
            Subscription domain entity with all fields populated
        """
        return Subscription(
            id=UUID(raw["id"]),
            key=raw.get("key"),
            resource_type=raw.get("type"),  # API uses "type", we use "resource_type"
            subscription_type=raw.get("subscriptionType"),
            subscription_status=raw.get("subscriptionStatus"),
            quantity=int(raw.get("quantity", 0)) if raw.get("quantity") else None,
            available_quantity=int(raw.get("availableQuantity", 0)) if raw.get("availableQuantity") else None,
            sku=raw.get("sku"),
            sku_description=raw.get("skuDescription"),
            start_time=self._parse_timestamp(raw.get("startTime")),
            end_time=self._parse_timestamp(raw.get("endTime")),
            tier=raw.get("tier"),
            tier_description=raw.get("tierDescription"),
            product_type=raw.get("productType"),
            is_eval=raw.get("isEval", False),
            contract=raw.get("contract"),
            quote=raw.get("quote"),
            po=raw.get("po"),
            reseller_po=raw.get("resellerPo"),
            created_at=self._parse_timestamp(raw.get("createdAt")),
            updated_at=self._parse_timestamp(raw.get("updatedAt")),
            raw_data=raw,
        )

    def map_to_record(self, subscription: Subscription) -> tuple[Any, ...]:
        """Transform Subscription entity to database record tuple.

        The tuple ordering matches the INSERT statement in PostgresSubscriptionRepository:
        (id, key, resource_type, subscription_type, subscription_status,
         quantity, available_quantity, sku, sku_description,
         start_time, end_time, tier, tier_description,
         product_type, is_eval, contract, quote, po, reseller_po,
         created_at, updated_at, raw_data)

        Args:
            subscription: Subscription domain entity

        Returns:
            Tuple of 22 values ready for database insertion
        """
        return (
            str(subscription.id),  # UUID as string for asyncpg
            subscription.key,
            subscription.resource_type,
            subscription.subscription_type,
            subscription.subscription_status,
            subscription.quantity,
            subscription.available_quantity,
            subscription.sku,
            subscription.sku_description,
            subscription.start_time,
            subscription.end_time,
            subscription.tier,
            subscription.tier_description,
            subscription.product_type,
            subscription.is_eval,
            subscription.contract,
            subscription.quote,
            subscription.po,
            subscription.reseller_po,
            subscription.created_at,
            subscription.updated_at,
            json.dumps(subscription.raw_data),  # JSONB requires JSON string
        )

    def extract_tags(
        self,
        subscription: Subscription,
        raw: dict[str, Any],
    ) -> list[SubscriptionTag]:
        """Extract tags from subscription data.

        Tags are stored as a dictionary under the "tags" key.

        Args:
            subscription: Subscription entity (provides subscription_id)
            raw: Raw subscription dictionary from API

        Returns:
            List of SubscriptionTag entities
        """
        tags = []
        raw_tags = raw.get("tags") or {}

        for key, value in raw_tags.items():
            tags.append(
                SubscriptionTag(
                    subscription_id=subscription.id,
                    tag_key=key,
                    tag_value=str(value) if value is not None else "",
                )
            )

        return tags

    @staticmethod
    def _parse_timestamp(iso_string: str | None) -> datetime | None:
        """Parse ISO 8601 timestamp string to datetime.

        Args:
            iso_string: ISO 8601 formatted timestamp string (may end with 'Z')

        Returns:
            datetime object or None if input is None/empty
        """
        if not iso_string:
            return None
        return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
