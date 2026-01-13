"""
Write Executor for REST API Mutations.

Handles write operations through the REST API with:
- Audit logging
- User confirmation for dangerous operations
- Rate limiting awareness
- Transaction-like semantics (where possible)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

from ..domain.entities import ToolCall, ToolDefinition, UserContext
from ..domain.ports import IAuditLog, IToolExecutor

logger = logging.getLogger(__name__)


class DeviceLimitExceededError(ValueError):
    """Raised when device array exceeds the maximum allowed limit.

    This error should be mapped to HTTP 400 Bad Request.
    """

    def __init__(self, count: int, limit: int, operation: str):
        self.count = count
        self.limit = limit
        self.operation = operation
        super().__init__(
            f"Operation '{operation}' exceeds maximum device limit. "
            f"Got {count} devices, maximum is {limit}. "
            f"Please split into smaller batches of {limit} or fewer."
        )


class WriteOperationType(str, Enum):
    """Types of write operations."""

    ADD_DEVICE = "add_device"
    UPDATE_TAGS = "update_tags"
    BULK_UPDATE_TAGS = "bulk_update_tags"
    ASSIGN_APPLICATION = "assign_application"
    UNASSIGN_APPLICATION = "unassign_application"
    ARCHIVE_DEVICES = "archive_devices"
    UNARCHIVE_DEVICES = "unarchive_devices"
    ASSIGN_SUBSCRIPTION = "assign_subscription"
    UNASSIGN_SUBSCRIPTION = "unassign_subscription"


class RiskLevel(str, Enum):
    """Risk level of operations for confirmation requirements."""

    LOW = "low"  # No confirmation needed
    MEDIUM = "medium"  # Confirmation recommended
    HIGH = "high"  # Confirmation required
    CRITICAL = "critical"  # Multi-step confirmation required


@dataclass
class WriteOperation:
    """Represents a write operation for execution.

    Attributes:
        id: Unique operation ID
        operation_type: Type of operation
        arguments: Operation arguments
        risk_level: Assessed risk level
        requires_confirmation: Whether user confirmation is required
        confirmation_message: Message to show for confirmation
        confirmed: Whether user has confirmed
        executed: Whether operation was executed
        result: Operation result
        error: Error if failed
        created_at: When operation was created
        executed_at: When operation was executed
    """

    id: UUID = field(default_factory=uuid4)
    operation_type: WriteOperationType = WriteOperationType.UPDATE_TAGS
    arguments: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    confirmation_message: Optional[str] = None
    confirmed: bool = False
    executed: bool = False
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    executed_at: Optional[datetime] = None


class IDeviceManager(Protocol):
    """Protocol for device manager write operations."""

    async def add_device(
        self,
        serial_number: str,
        device_type: Any,
        *,
        part_number: Optional[str] = None,
        mac_address: Optional[str] = None,
        tags: Optional[dict[str, str]] = None,
        location_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> Any: ...

    async def update_tags(
        self,
        device_ids: list[str],
        tags: dict[str, Optional[str]],
        *,
        dry_run: bool = False,
    ) -> Any: ...

    async def update_tags_batch(
        self,
        device_ids: list[str],
        tags: dict[str, Optional[str]],
        *,
        dry_run: bool = False,
    ) -> Any: ...

    async def assign_application(
        self,
        device_ids: list[str],
        application_id: str,
        *,
        region: Optional[str] = None,
        tenant_workspace_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> Any: ...

    async def unassign_application(
        self,
        device_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> Any: ...

    async def archive_devices(
        self,
        device_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> Any: ...

    async def unarchive_devices(
        self,
        device_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> Any: ...

    async def assign_subscriptions(
        self,
        device_ids: list[str],
        subscription_key: str,
        *,
        dry_run: bool = False,
    ) -> Any: ...

    async def unassign_subscriptions(
        self,
        device_ids: list[str],
        subscription_key: str,
        *,
        dry_run: bool = False,
    ) -> Any: ...


class TenantQuotaExceededError(ValueError):
    """Raised when tenant exceeds daily operation quota.

    This error should be mapped to HTTP 429 Too Many Requests.
    """

    def __init__(self, tenant_id: str, current: int, limit: int, reset_at: str):
        self.tenant_id = tenant_id
        self.current = current
        self.limit = limit
        self.reset_at = reset_at
        super().__init__(
            f"Daily operation quota exceeded for tenant. "
            f"Used {current}/{limit} operations. Resets at {reset_at}."
        )


class IRedisClient(Protocol):
    """Protocol for Redis client (for dependency injection)."""

    async def get(self, key: str) -> Optional[str]:
        """Get a key value."""
        ...

    async def setex(self, key: str, ttl: int, value: str) -> None:
        """Set a key with expiration."""
        ...

    async def incrby(self, key: str, amount: int) -> int:
        """Increment a key by amount."""
        ...

    async def expire(self, key: str, ttl: int) -> None:
        """Set expiration on a key."""
        ...


@dataclass
class TenantQuota:
    """Tracks per-tenant operation quotas.

    Supports both in-memory and Redis-backed storage for persistence
    across restarts.
    """

    tenant_id: str
    daily_limit: int
    operations_today: int = 0
    devices_today: int = 0
    reset_date: str = ""  # YYYY-MM-DD

    def check_and_increment(self, device_count: int = 1) -> None:
        """Check quota and increment counters (in-memory).

        Args:
            device_count: Number of devices in this operation

        Raises:
            TenantQuotaExceededError: If quota exceeded
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Reset if new day
        if self.reset_date != today:
            self.operations_today = 0
            self.devices_today = 0
            self.reset_date = today

        if self.operations_today >= self.daily_limit:
            raise TenantQuotaExceededError(
                tenant_id=self.tenant_id,
                current=self.operations_today,
                limit=self.daily_limit,
                reset_at=f"{today} 00:00:00 UTC (next day)",
            )

        self.operations_today += 1
        self.devices_today += device_count


class RedisQuotaStore:
    """Redis-backed quota storage for persistence across restarts.

    Keys are structured as:
    - quota:{tenant_id}:ops:{date} - operations count
    - quota:{tenant_id}:devices:{date} - devices count

    Keys automatically expire at end of day (UTC).
    """

    KEY_PREFIX = "quota"

    def __init__(self, redis: IRedisClient, default_limit: int = 100):
        """Initialize Redis quota store.

        Args:
            redis: Redis client
            default_limit: Default daily operation limit
        """
        self.redis = redis
        self.default_limit = default_limit

    def _get_keys(self, tenant_id: str) -> tuple[str, str]:
        """Get Redis keys for a tenant's daily quota.

        Returns:
            Tuple of (operations_key, devices_key)
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        ops_key = f"{self.KEY_PREFIX}:{tenant_id}:ops:{today}"
        devices_key = f"{self.KEY_PREFIX}:{tenant_id}:devices:{today}"
        return ops_key, devices_key

    def _seconds_until_midnight(self) -> int:
        """Calculate seconds until midnight UTC."""
        now = datetime.utcnow()
        midnight = datetime(now.year, now.month, now.day) + timedelta(days=1)
        return int((midnight - now).total_seconds())

    async def check_and_increment(
        self,
        tenant_id: str,
        device_count: int = 1,
        daily_limit: Optional[int] = None,
    ) -> tuple[int, int]:
        """Check quota and increment atomically using Redis.

        Args:
            tenant_id: Tenant identifier
            device_count: Number of devices in this operation
            daily_limit: Override default daily limit

        Returns:
            Tuple of (new_ops_count, new_devices_count)

        Raises:
            TenantQuotaExceededError: If quota exceeded
        """
        limit = daily_limit or self.default_limit
        ops_key, devices_key = self._get_keys(tenant_id)
        ttl = self._seconds_until_midnight()

        # Get current count first to check limit
        current_str = await self.redis.get(ops_key)
        current = int(current_str) if current_str else 0

        if current >= limit:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            raise TenantQuotaExceededError(
                tenant_id=tenant_id,
                current=current,
                limit=limit,
                reset_at=f"{today} 00:00:00 UTC (next day)",
            )

        # Increment atomically
        new_ops = await self.redis.incrby(ops_key, 1)
        new_devices = await self.redis.incrby(devices_key, device_count)

        # Set expiration (idempotent if already set)
        await self.redis.expire(ops_key, ttl)
        await self.redis.expire(devices_key, ttl)

        logger.debug(
            f"Tenant {tenant_id} quota: {new_ops}/{limit} ops, "
            f"{new_devices} devices today (Redis)"
        )

        return new_ops, new_devices

    async def get_quota_info(self, tenant_id: str) -> dict:
        """Get current quota usage for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with quota information
        """
        ops_key, devices_key = self._get_keys(tenant_id)

        ops_str = await self.redis.get(ops_key)
        devices_str = await self.redis.get(devices_key)

        return {
            "tenant_id": tenant_id,
            "operations_today": int(ops_str) if ops_str else 0,
            "devices_today": int(devices_str) if devices_str else 0,
            "daily_limit": self.default_limit,
            "reset_at": datetime.utcnow().strftime("%Y-%m-%d") + " 00:00:00 UTC (next day)",
        }


class WriteExecutor(IToolExecutor):
    """Executor for write operations through REST API.

    Provides:
    - Audit logging for all operations
    - Risk assessment and confirmation requirements
    - Tiered device limits based on risk level
    - Per-tenant daily quotas
    - Dry-run validation before execution
    - Rate limit awareness
    - Operation tracking

    Usage:
        executor = WriteExecutor(device_manager, audit_log)

        # Check if operation needs confirmation
        operation = executor.prepare_operation(
            WriteOperationType.ARCHIVE_DEVICES,
            {"device_ids": ["uuid1", "uuid2"]},
        )

        if operation.requires_confirmation:
            # Get user confirmation
            confirmed = await get_user_confirmation(operation.confirmation_message)
            operation.confirmed = confirmed

        # Execute
        result = await executor.execute_operation(operation, user_context)

    Architecture:
        - Wraps DeviceManager for actual API calls
        - Logs all operations to audit log
        - Assesses risk based on operation type and scope
        - Enforces tiered device limits per risk level
        - Tracks per-tenant quotas to prevent abuse
        - Supports dry-run for validation
    """

    # Tiered device limits by risk level (more restrictive for higher risk)
    # These can be overridden via environment variables
    DEVICE_LIMITS_BY_RISK = {
        RiskLevel.LOW: int(os.getenv("MAX_DEVICES_LOW_RISK", "50")),
        RiskLevel.MEDIUM: int(os.getenv("MAX_DEVICES_MEDIUM_RISK", "25")),
        RiskLevel.HIGH: int(os.getenv("MAX_DEVICES_HIGH_RISK", "10")),
        RiskLevel.CRITICAL: int(os.getenv("MAX_DEVICES_CRITICAL_RISK", "5")),
    }

    # Legacy: fallback for old env var (uses MEDIUM risk limit)
    MAX_DEVICES_PER_OPERATION = int(os.getenv("MAX_DEVICES_PER_OPERATION", "25"))

    # Per-tenant daily quota (configurable)
    DEFAULT_DAILY_QUOTA = int(os.getenv("TENANT_DAILY_QUOTA", "100"))

    # Risk assessment configuration
    RISK_THRESHOLDS = {
        WriteOperationType.ADD_DEVICE: RiskLevel.LOW,
        WriteOperationType.UPDATE_TAGS: RiskLevel.LOW,
        WriteOperationType.ASSIGN_APPLICATION: RiskLevel.MEDIUM,
        WriteOperationType.UNASSIGN_APPLICATION: RiskLevel.MEDIUM,
        WriteOperationType.ARCHIVE_DEVICES: RiskLevel.HIGH,
        WriteOperationType.UNARCHIVE_DEVICES: RiskLevel.MEDIUM,
        WriteOperationType.ASSIGN_SUBSCRIPTION: RiskLevel.MEDIUM,
        WriteOperationType.UNASSIGN_SUBSCRIPTION: RiskLevel.HIGH,
    }

    # Device count thresholds for elevated risk
    BULK_THRESHOLD = 5  # > 5 devices elevates risk
    MASS_THRESHOLD = 20  # > 20 devices requires critical confirmation

    def __init__(
        self,
        device_manager: IDeviceManager,
        audit_log: Optional[IAuditLog] = None,
        daily_quota: Optional[int] = None,
        redis_quota_store: Optional[RedisQuotaStore] = None,
    ):
        """Initialize the write executor.

        Args:
            device_manager: Device manager for API calls
            audit_log: Audit log for operation tracking
            daily_quota: Override default daily quota per tenant
            redis_quota_store: Optional Redis-backed quota store for persistence.
                If provided, quotas persist across restarts. If None, uses
                in-memory quota tracking (lost on restart).
        """
        self.device_manager = device_manager
        self.audit_log = audit_log
        self.daily_quota = daily_quota or self.DEFAULT_DAILY_QUOTA
        self._pending_operations: dict[UUID, WriteOperation] = {}
        self._tenant_quotas: dict[str, TenantQuota] = {}  # Per-tenant quota tracking (in-memory)
        self._redis_quota_store = redis_quota_store  # Optional Redis persistence

    def _get_tenant_quota(self, tenant_id: str) -> TenantQuota:
        """Get or create quota tracker for a tenant (in-memory fallback).

        Args:
            tenant_id: Tenant identifier

        Returns:
            TenantQuota tracker for the tenant
        """
        if tenant_id not in self._tenant_quotas:
            self._tenant_quotas[tenant_id] = TenantQuota(
                tenant_id=tenant_id,
                daily_limit=self.daily_quota,
            )
        return self._tenant_quotas[tenant_id]

    def _validate_device_ids(
        self,
        device_ids: list[str],
        operation_name: str,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
    ) -> list[str]:
        """Validate and deduplicate device IDs array.

        Uses tiered limits based on operation risk level:
        - LOW risk: up to 50 devices
        - MEDIUM risk: up to 25 devices
        - HIGH risk: up to 10 devices
        - CRITICAL risk: up to 5 devices

        Args:
            device_ids: List of device UUIDs
            operation_name: Name of the operation (for error messages)
            risk_level: Risk level of the operation (affects limit)

        Returns:
            Deduplicated list of device IDs

        Raises:
            DeviceLimitExceededError: If count exceeds limit for risk level
        """
        if not device_ids:
            return []

        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for device_id in device_ids:
            if device_id not in seen:
                seen.add(device_id)
                unique_ids.append(device_id)

        # Get tiered limit based on risk level
        limit = self.DEVICE_LIMITS_BY_RISK.get(risk_level, self.MAX_DEVICES_PER_OPERATION)

        # Check limit after deduplication
        if len(unique_ids) > limit:
            logger.warning(
                f"Device limit exceeded for {operation_name} (risk={risk_level.value}): "
                f"{len(unique_ids)} > {limit}"
            )
            raise DeviceLimitExceededError(
                count=len(unique_ids),
                limit=limit,
                operation=operation_name,
            )

        return unique_ids

    async def _check_tenant_quota(self, tenant_id: str, device_count: int) -> None:
        """Check and update tenant quota.

        Uses Redis-backed storage if configured, otherwise falls back to
        in-memory tracking.

        Args:
            tenant_id: Tenant identifier
            device_count: Number of devices in the operation

        Raises:
            TenantQuotaExceededError: If daily quota exceeded
        """
        # Use Redis if available for persistence across restarts
        if self._redis_quota_store:
            await self._redis_quota_store.check_and_increment(
                tenant_id=tenant_id,
                device_count=device_count,
                daily_limit=self.daily_quota,
            )
            return

        # Fall back to in-memory tracking
        quota = self._get_tenant_quota(tenant_id)
        quota.check_and_increment(device_count)
        logger.debug(
            f"Tenant {tenant_id} quota: {quota.operations_today}/{quota.daily_limit} ops, "
            f"{quota.devices_today} devices today (in-memory)"
        )

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions for write operations.

        Returns:
            List of tool definitions for LLM
        """
        return [
            ToolDefinition(
                name="add_device",
                description="Add a new device to the GreenLake workspace",
                parameters={
                    "type": "object",
                    "properties": {
                        "serial_number": {
                            "type": "string",
                            "description": "Device serial number",
                        },
                        "device_type": {
                            "type": "string",
                            "enum": ["COMPUTE", "NETWORK", "STORAGE"],
                            "description": "Type of device",
                        },
                        "part_number": {
                            "type": "string",
                            "description": "Part number (required for COMPUTE/STORAGE)",
                        },
                        "mac_address": {
                            "type": "string",
                            "description": "MAC address (required for NETWORK)",
                        },
                        "tags": {
                            "type": "object",
                            "description": "Optional tags as key-value pairs",
                        },
                    },
                    "required": ["serial_number", "device_type"],
                },
                is_read_only=False,
                requires_confirmation=False,
            ),
            ToolDefinition(
                name="update_device_tags",
                description="Add, update, or remove tags on devices. Set tag value to null to remove.",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of device UUIDs (max 50 for low-risk operations)",
                        },
                        "tags": {
                            "type": "object",
                            "description": "Tags to add/update (set value to null to remove)",
                        },
                    },
                    "required": ["device_ids", "tags"],
                },
                is_read_only=False,
                requires_confirmation=False,
            ),
            ToolDefinition(
                name="assign_application",
                description="Assign an application (region) to devices",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of device UUIDs (max 25 for medium-risk operations)",
                        },
                        "application_id": {
                            "type": "string",
                            "description": "UUID of the application to assign",
                        },
                        "region": {
                            "type": "string",
                            "description": "Optional region name",
                        },
                    },
                    "required": ["device_ids", "application_id"],
                },
                is_read_only=False,
                requires_confirmation=True,
            ),
            ToolDefinition(
                name="unassign_application",
                description="Remove application assignment from devices",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of device UUIDs (max 25 for medium-risk operations)",
                        },
                    },
                    "required": ["device_ids"],
                },
                is_read_only=False,
                requires_confirmation=True,
            ),
            ToolDefinition(
                name="archive_devices",
                description="Archive devices (soft delete). Archived devices can be restored.",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of device UUIDs (max 10 for high-risk operations)",
                        },
                    },
                    "required": ["device_ids"],
                },
                is_read_only=False,
                requires_confirmation=True,
            ),
            ToolDefinition(
                name="unarchive_devices",
                description="Restore archived devices",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of device UUIDs (max 25 for medium-risk operations)",
                        },
                    },
                    "required": ["device_ids"],
                },
                is_read_only=False,
                requires_confirmation=True,
            ),
            ToolDefinition(
                name="assign_subscription",
                description="Assign a subscription to devices",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of device UUIDs (max 25 for medium-risk operations)",
                        },
                        "subscription_key": {
                            "type": "string",
                            "description": "Subscription key to assign",
                        },
                    },
                    "required": ["device_ids", "subscription_key"],
                },
                is_read_only=False,
                requires_confirmation=True,
            ),
            ToolDefinition(
                name="unassign_subscription",
                description="Remove subscription from devices. This may affect device functionality.",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of device UUIDs (max 10 for high-risk operations)",
                        },
                        "subscription_key": {
                            "type": "string",
                            "description": "Subscription key to remove",
                        },
                    },
                    "required": ["device_ids", "subscription_key"],
                },
                is_read_only=False,
                requires_confirmation=True,
            ),
        ]

    def _assess_risk(
        self,
        operation_type: WriteOperationType,
        arguments: dict[str, Any],
    ) -> RiskLevel:
        """Assess the risk level of an operation.

        Args:
            operation_type: Type of operation
            arguments: Operation arguments

        Returns:
            Assessed risk level
        """
        base_risk = self.RISK_THRESHOLDS.get(operation_type, RiskLevel.MEDIUM)

        # Elevate risk based on number of devices affected
        device_ids = arguments.get("device_ids", [])
        device_count = len(device_ids) if isinstance(device_ids, list) else 0

        if device_count > self.MASS_THRESHOLD:
            return RiskLevel.CRITICAL
        elif device_count > self.BULK_THRESHOLD:
            # Elevate by one level
            if base_risk == RiskLevel.LOW:
                return RiskLevel.MEDIUM
            elif base_risk == RiskLevel.MEDIUM:
                return RiskLevel.HIGH

        return base_risk

    def _get_confirmation_message(
        self,
        operation_type: WriteOperationType,
        arguments: dict[str, Any],
        risk_level: RiskLevel,
    ) -> str:
        """Generate a confirmation message for the user.

        Args:
            operation_type: Type of operation
            arguments: Operation arguments
            risk_level: Assessed risk level

        Returns:
            Confirmation message
        """
        device_count = len(arguments.get("device_ids", []))

        # Build tag change summary for BULK_UPDATE_TAGS
        tag_summary = ""
        if operation_type == WriteOperationType.BULK_UPDATE_TAGS:
            tags = arguments.get("tags", {})
            additions = []
            removals = []

            for key, value in tags.items():
                if value is None:
                    removals.append(key)
                else:
                    additions.append(f"{key}={value}")

            parts = []
            if additions:
                parts.append(f"add/update: {', '.join(additions)}")
            if removals:
                parts.append(f"remove: {', '.join(removals)}")

            tag_summary = f" ({'; '.join(parts)})" if parts else ""

        messages = {
            WriteOperationType.ARCHIVE_DEVICES: (
                f"Are you sure you want to archive {device_count} device(s)? "
                "Archived devices will no longer receive updates."
            ),
            WriteOperationType.UNASSIGN_APPLICATION: (
                f"Are you sure you want to remove the application from {device_count} device(s)? "
                "This may affect device management capabilities."
            ),
            WriteOperationType.UNASSIGN_SUBSCRIPTION: (
                f"Are you sure you want to remove the subscription from {device_count} device(s)? "
                "This may affect device functionality and support."
            ),
            WriteOperationType.ASSIGN_APPLICATION: (
                f"Assign application to {device_count} device(s)?"
            ),
            WriteOperationType.ASSIGN_SUBSCRIPTION: (
                f"Assign subscription to {device_count} device(s)?"
            ),
            WriteOperationType.BULK_UPDATE_TAGS: (
                f"Update tags on {device_count} device(s){tag_summary}?"
            ),
        }

        base_message = messages.get(
            operation_type,
            f"Execute {operation_type.value} on {device_count} device(s)?",
        )

        if risk_level == RiskLevel.CRITICAL:
            return f"WARNING: High-risk operation affecting {device_count} devices. {base_message}"

        return base_message

    def prepare_operation(
        self,
        operation_type: WriteOperationType,
        arguments: dict[str, Any],
    ) -> WriteOperation:
        """Prepare a write operation for execution.

        Assesses risk and determines if confirmation is needed.
        Uses tiered device limits based on assessed risk level.

        Args:
            operation_type: Type of operation
            arguments: Operation arguments

        Returns:
            WriteOperation ready for execution (may require confirmation)

        Raises:
            DeviceLimitExceededError: If device_ids exceeds limit for risk level
        """
        # First assess risk to determine device limit
        risk_level = self._assess_risk(operation_type, arguments)

        # Validate and deduplicate device_ids with tiered limits
        if "device_ids" in arguments and isinstance(arguments["device_ids"], list):
            arguments["device_ids"] = self._validate_device_ids(
                arguments["device_ids"],
                operation_type.value,
                risk_level=risk_level,  # Use tiered limits
            )

        requires_confirmation = risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        confirmation_message = None

        if requires_confirmation:
            confirmation_message = self._get_confirmation_message(
                operation_type, arguments, risk_level
            )

        operation = WriteOperation(
            operation_type=operation_type,
            arguments=arguments,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            confirmation_message=confirmation_message,
        )

        # Store for tracking
        self._pending_operations[operation.id] = operation

        logger.info(
            f"Prepared operation {operation.id}: {operation_type.value} "
            f"(risk: {risk_level.value}, confirmation: {requires_confirmation})"
        )

        return operation

    async def execute_operation(
        self,
        operation: WriteOperation,
        context: UserContext,
    ) -> WriteOperation:
        """Execute a prepared write operation.

        Args:
            operation: The operation to execute
            context: User context for audit

        Returns:
            Updated operation with result or error

        Raises:
            ValueError: If confirmation required but not given
            TenantQuotaExceededError: If daily quota exceeded
        """
        if operation.requires_confirmation and not operation.confirmed:
            raise ValueError(
                f"Operation {operation.id} requires confirmation before execution"
            )

        if operation.executed:
            logger.warning(f"Operation {operation.id} already executed")
            return operation

        # Check tenant quota before execution
        device_count = len(operation.arguments.get("device_ids", [])) or 1
        await self._check_tenant_quota(context.tenant_id, device_count)

        # Log operation start
        if self.audit_log:
            await self.audit_log.log(
                event_type="write_operation_start",
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                details={
                    "operation_id": str(operation.id),
                    "operation_type": operation.operation_type.value,
                    "arguments": operation.arguments,
                    "risk_level": operation.risk_level.value,
                },
            )

        try:
            result = await self._execute(operation)
            operation.result = result
            operation.executed = True
            operation.executed_at = datetime.utcnow()

            # Log success
            if self.audit_log:
                await self.audit_log.log(
                    event_type="write_operation_success",
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    details={
                        "operation_id": str(operation.id),
                        "operation_type": operation.operation_type.value,
                        "result": str(result)[:500],  # Truncate for logging
                    },
                )

            logger.info(f"Operation {operation.id} completed successfully")

        except Exception as e:
            operation.error = str(e)
            operation.executed = True
            operation.executed_at = datetime.utcnow()

            # Log failure
            if self.audit_log:
                await self.audit_log.log(
                    event_type="write_operation_failed",
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    details={
                        "operation_id": str(operation.id),
                        "operation_type": operation.operation_type.value,
                        "error": str(e),
                    },
                )

            logger.error(f"Operation {operation.id} failed: {e}")

        return operation

    async def _execute(self, operation: WriteOperation) -> Any:
        """Execute the actual API call.

        Args:
            operation: Operation to execute

        Returns:
            API result
        """
        op_type = operation.operation_type
        args = operation.arguments

        if op_type == WriteOperationType.ADD_DEVICE:
            return await self.device_manager.add_device(
                serial_number=args["serial_number"],
                device_type=args["device_type"],
                part_number=args.get("part_number"),
                mac_address=args.get("mac_address"),
                tags=args.get("tags"),
                location_id=args.get("location_id"),
            )

        elif op_type == WriteOperationType.UPDATE_TAGS:
            return await self.device_manager.update_tags(
                device_ids=args["device_ids"],
                tags=args["tags"],
            )

        elif op_type == WriteOperationType.BULK_UPDATE_TAGS:
            return await self.device_manager.update_tags_batch(
                device_ids=args["device_ids"],
                tags=args["tags"],
            )

        elif op_type == WriteOperationType.ASSIGN_APPLICATION:
            return await self.device_manager.assign_application(
                device_ids=args["device_ids"],
                application_id=args["application_id"],
                region=args.get("region"),
                tenant_workspace_id=args.get("tenant_workspace_id"),
            )

        elif op_type == WriteOperationType.UNASSIGN_APPLICATION:
            return await self.device_manager.unassign_application(
                device_ids=args["device_ids"],
            )

        elif op_type == WriteOperationType.ARCHIVE_DEVICES:
            return await self.device_manager.archive_devices(
                device_ids=args["device_ids"],
            )

        elif op_type == WriteOperationType.UNARCHIVE_DEVICES:
            return await self.device_manager.unarchive_devices(
                device_ids=args["device_ids"],
            )

        elif op_type == WriteOperationType.ASSIGN_SUBSCRIPTION:
            return await self.device_manager.assign_subscriptions(
                device_ids=args["device_ids"],
                subscription_key=args["subscription_key"],
            )

        elif op_type == WriteOperationType.UNASSIGN_SUBSCRIPTION:
            return await self.device_manager.unassign_subscriptions(
                device_ids=args["device_ids"],
                subscription_key=args["subscription_key"],
            )

        else:
            raise ValueError(f"Unknown operation type: {op_type}")

    async def execute_tool_call(
        self,
        tool_call: ToolCall,
        context: UserContext,
    ) -> ToolCall:
        """Execute a tool call from the LLM.

        Maps tool names to operation types and executes.

        Args:
            tool_call: Tool call from LLM
            context: User context

        Returns:
            ToolCall with result populated
        """
        # Map tool names to operation types
        tool_to_operation = {
            "add_device": WriteOperationType.ADD_DEVICE,
            "update_device_tags": WriteOperationType.UPDATE_TAGS,
            "assign_application": WriteOperationType.ASSIGN_APPLICATION,
            "unassign_application": WriteOperationType.UNASSIGN_APPLICATION,
            "archive_devices": WriteOperationType.ARCHIVE_DEVICES,
            "unarchive_devices": WriteOperationType.UNARCHIVE_DEVICES,
            "assign_subscription": WriteOperationType.ASSIGN_SUBSCRIPTION,
            "unassign_subscription": WriteOperationType.UNASSIGN_SUBSCRIPTION,
        }

        operation_type = tool_to_operation.get(tool_call.name)

        if not operation_type:
            tool_call.result = {
                "error": f"Unknown write tool: {tool_call.name}",
                "recoverable": False,
            }
            return tool_call

        # Prepare and check if confirmation needed
        operation = self.prepare_operation(operation_type, tool_call.arguments)

        if operation.requires_confirmation:
            # Return confirmation required - caller handles UI
            tool_call.result = {
                "status": "confirmation_required",
                "operation_id": str(operation.id),
                "message": operation.confirmation_message,
                "risk_level": operation.risk_level.value,
            }
            return tool_call

        # Execute immediately if no confirmation needed
        operation = await self.execute_operation(operation, context)

        if operation.error:
            tool_call.result = {
                "error": operation.error,
                "recoverable": True,
            }
        else:
            tool_call.result = {
                "status": "success",
                "operation_id": str(operation.id),
                "result": operation.result,
            }

        return tool_call

    def get_pending_operation(self, operation_id: UUID) -> Optional[WriteOperation]:
        """Get a pending operation by ID.

        Args:
            operation_id: Operation UUID

        Returns:
            Operation if found
        """
        return self._pending_operations.get(operation_id)

    async def confirm_operation(
        self,
        operation_id: UUID,
        context: UserContext,
    ) -> WriteOperation:
        """Confirm and execute a pending operation.

        Args:
            operation_id: Operation UUID
            context: User context

        Returns:
            Executed operation

        Raises:
            ValueError: If operation not found
        """
        operation = self._pending_operations.get(operation_id)

        if not operation:
            raise ValueError(f"Operation not found: {operation_id}")

        operation.confirmed = True
        return await self.execute_operation(operation, context)

    async def cancel_operation(self, operation_id: UUID) -> bool:
        """Cancel a pending operation.

        Args:
            operation_id: Operation UUID

        Returns:
            True if cancelled, False if not found
        """
        if operation_id in self._pending_operations:
            del self._pending_operations[operation_id]
            logger.info(f"Cancelled operation {operation_id}")
            return True
        return False
