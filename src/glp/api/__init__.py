"""GreenLake API modules.

This package provides the core API client and resource-specific syncers
for interacting with the HPE GreenLake Platform and Aruba Central.

Classes:
    GLPClient: Generic HTTP client with pagination, retry, and circuit breaker
    TokenManager: OAuth2 token management with caching (GreenLake)
    DeviceSyncer: Device inventory synchronization (read operations)
    DeviceManager: Device management operations (write operations)
    SubscriptionSyncer: Subscription synchronization

    ArubaCentralClient: HTTP client for Aruba Central APIs (cursor-based pagination)
    ArubaTokenManager: OAuth2 token management for Aruba Central
    ArubaCentralSyncer: Aruba Central device synchronization

Exceptions:
    GLPError: Base exception for all GLP errors
    ConfigurationError: Missing or invalid configuration
    AuthenticationError: Authentication failures
    TokenFetchError: Token acquisition failures
    APIError: API request failures
    RateLimitError: Rate limit exceeded
    NetworkError: Network connectivity issues
    DatabaseError: Database operation failures
    SyncError: Synchronization failures
    DeviceLimitError: Device count exceeds API limits
    AsyncOperationError: Async operation failed

Resilience:
    CircuitBreaker: Prevent cascading failures
    retry: Decorator for retry with exponential backoff
"""
from .auth import TokenError, TokenManager, get_token
from .aruba_auth import ArubaTokenManager, get_aruba_token
from .aruba_client import (
    ARUBA_DEVICES_PAGINATION,
    ArubaCentralClient,
    ArubaPaginationConfig,
    RateLimitInfo,
)
from .aruba_clients import ArubaClientsSyncer
from .aruba_devices import ArubaCentralSyncer
from .aruba_firmware import ArubaFirmwareSyncer
from .client import (
    DEVICES_PAGINATION,
    SUBSCRIPTIONS_PAGINATION,
    AsyncOperationResult,
    GLPClient,
    GLPClientError,
    PaginationConfig,
)
from .database import (
    BatchExecutor,
    batch_transaction,
    check_database_health,
    close_pool,
    create_pool,
    database_connection,
    database_transaction,
)
from .device_manager import DeviceManager, DeviceType, OperationStatus
from .devices import DeviceSyncer
from .exceptions import (
    APIError,
    AsyncOperationError,
    AuthenticationError,
    CircuitOpenError,
    ConfigurationError,
    ConnectionError,
    ConnectionPoolError,
    DatabaseError,
    DeviceLimitError,
    DNSError,
    ErrorCollector,
    GLPError,
    IntegrityError,
    InvalidCredentialsError,
    NetworkError,
    NotFoundError,
    PartialSyncError,
    RateLimitError,
    ServerError,
    SyncError,
    TimeoutError,
    TokenExpiredError,
    TokenFetchError,
    TransactionError,
    ValidationError,
)
from .resilience import (
    DEFAULT_RETRYABLE_EXCEPTIONS,
    CircuitBreaker,
    CircuitState,
    retry,
    retry_async,
    try_or_default,
    with_fallback,
    with_timeout,
)
from .subscriptions import SubscriptionSyncer

__all__ = [
    # Auth - GreenLake
    "TokenManager",
    "TokenError",
    "TokenFetchError",
    "TokenExpiredError",
    "InvalidCredentialsError",
    "get_token",
    # Auth - Aruba Central
    "ArubaTokenManager",
    "get_aruba_token",
    # Client - GreenLake
    "GLPClient",
    "GLPClientError",
    "PaginationConfig",
    "AsyncOperationResult",
    "DEVICES_PAGINATION",
    "SUBSCRIPTIONS_PAGINATION",
    # Client - Aruba Central
    "ArubaCentralClient",
    "ArubaPaginationConfig",
    "RateLimitInfo",
    "ARUBA_DEVICES_PAGINATION",
    # Exceptions - Base
    "GLPError",
    "ConfigurationError",
    # Exceptions - Auth
    "AuthenticationError",
    # Exceptions - API
    "APIError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
    "ServerError",
    # Exceptions - Network
    "NetworkError",
    "ConnectionError",
    "TimeoutError",
    "DNSError",
    # Exceptions - Database
    "DatabaseError",
    "ConnectionPoolError",
    "TransactionError",
    "IntegrityError",
    # Exceptions - Sync
    "SyncError",
    "PartialSyncError",
    "CircuitOpenError",
    "AsyncOperationError",
    # Exceptions - Device Management
    "DeviceLimitError",
    # Error utilities
    "ErrorCollector",
    # Resilience
    "CircuitBreaker",
    "CircuitState",
    "retry",
    "retry_async",
    "with_fallback",
    "with_timeout",
    "try_or_default",
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    # Database utilities
    "database_transaction",
    "database_connection",
    "batch_transaction",
    "BatchExecutor",
    "create_pool",
    "close_pool",
    "check_database_health",
    # Syncers - GreenLake (read operations)
    "DeviceSyncer",
    "SubscriptionSyncer",
    # Syncers - Aruba Central
    "ArubaCentralSyncer",
    "ArubaClientsSyncer",
    "ArubaFirmwareSyncer",
    # Device Management (write operations)
    "DeviceManager",
    "DeviceType",
    "OperationStatus",
]
