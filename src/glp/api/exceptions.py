#!/usr/bin/env python3
"""Comprehensive Exception Hierarchy for HPE GreenLake Platform API.

This module provides a structured exception hierarchy for handling errors
across the GLP client, including authentication, API, database, and network errors.

Design Principles:
    - All exceptions inherit from GLPError base class
    - Exceptions preserve context (original error, timestamps, details)
    - Exceptions are categorized by recoverability
    - Each exception includes actionable information

Exception Hierarchy:
    GLPError (base)
    ├── ConfigurationError (unrecoverable - fix config)
    ├── AuthenticationError (may be recoverable - refresh token)
    │   ├── TokenFetchError
    │   ├── TokenExpiredError
    │   └── InvalidCredentialsError
    ├── APIError (may be recoverable - retry)
    │   ├── RateLimitError
    │   ├── NotFoundError
    │   ├── ValidationError
    │   └── ServerError
    ├── NetworkError (recoverable - retry)
    │   ├── ConnectionError
    │   ├── TimeoutError
    │   └── DNSError
    ├── DatabaseError (may be recoverable)
    │   ├── ConnectionPoolError
    │   ├── TransactionError
    │   └── IntegrityError
    └── SyncError (operation failed)
        ├── PartialSyncError
        └── CircuitOpenError

Author: HPE GreenLake Team
"""
from datetime import datetime
from typing import Any, Optional

# ============================================
# Base Exception
# ============================================

class GLPError(Exception):
    """Base exception for all GLP-related errors.

    All exceptions in this module inherit from GLPError, making it easy
    to catch all GLP-specific errors with a single except clause.

    Attributes:
        message: Human-readable error description
        code: Machine-readable error code (e.g., "AUTH_TOKEN_EXPIRED")
        details: Additional context as a dictionary
        timestamp: When the error occurred
        cause: The original exception that caused this error
        recoverable: Whether this error might be recoverable with retry
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        recoverable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__.upper()
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        self.cause = cause
        self.recoverable = recoverable

        # Chain the original exception if provided
        if cause:
            self.__cause__ = cause

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.insert(0, f"[{self.code}]")
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            parts.append(f"({detail_str})")
        return " ".join(parts)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"code={self.code!r}, "
            f"details={self.details!r}, "
            f"recoverable={self.recoverable})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "recoverable": self.recoverable,
            "cause": str(self.cause) if self.cause else None,
        }


# ============================================
# Configuration Errors (Unrecoverable)
# ============================================

class ConfigurationError(GLPError):
    """Raised when configuration is missing or invalid.

    These errors require fixing configuration before retry.
    """

    def __init__(
        self,
        message: str,
        missing_keys: Optional[list[str]] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if missing_keys:
            details["missing_keys"] = missing_keys
        super().__init__(
            message,
            code="CONFIGURATION_ERROR",
            details=details,
            recoverable=False,
            **kwargs,
        )


# ============================================
# Authentication Errors
# ============================================

class AuthenticationError(GLPError):
    """Base class for authentication-related errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("recoverable", True)
        super().__init__(message, **kwargs)


class TokenFetchError(AuthenticationError):
    """Raised when token cannot be fetched from OAuth server."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        attempts: int = 1,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if status_code:
            details["status_code"] = status_code
        details["attempts"] = attempts
        super().__init__(
            message,
            code="TOKEN_FETCH_ERROR",
            details=details,
            **kwargs,
        )


class TokenExpiredError(AuthenticationError):
    """Raised when token has expired and refresh failed."""

    def __init__(self, message: str = "Access token has expired", **kwargs):
        super().__init__(message, code="TOKEN_EXPIRED", **kwargs)


class InvalidCredentialsError(AuthenticationError):
    """Raised when OAuth credentials are invalid."""

    def __init__(
        self,
        message: str = "Invalid client credentials",
        **kwargs,
    ):
        super().__init__(
            message,
            code="INVALID_CREDENTIALS",
            recoverable=False,  # Can't recover without new credentials
            **kwargs,
        )


# ============================================
# API Errors
# ============================================

class APIError(GLPError):
    """Base class for API response errors.

    Attributes:
        status_code: HTTP status code
        endpoint: API endpoint that was called
        response_body: Raw response body (may be truncated)
    """

    def __init__(
        self,
        message: str,
        status_code: int,
        endpoint: Optional[str] = None,
        response_body: Optional[str] = None,
        method: str = "GET",
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        details["status_code"] = status_code
        if endpoint:
            details["endpoint"] = endpoint
        if method:
            details["method"] = method
        if response_body:
            # Truncate large response bodies
            details["response_body"] = response_body[:500] if len(response_body) > 500 else response_body

        # Determine recoverability based on status code (can be overridden via kwargs)
        kwargs.setdefault("recoverable", status_code in (429, 500, 502, 503, 504))

        # Allow subclasses to override the error code
        kwargs.setdefault("code", f"API_ERROR_{status_code}")

        super().__init__(
            message,
            details=details,
            **kwargs,
        )
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_body = response_body
        self.method = method


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded (HTTP 429).

    Attributes:
        retry_after: Seconds to wait before retrying (from Retry-After header)
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs,
    ):
        kwargs.setdefault("status_code", 429)
        details = kwargs.pop("details", {})
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            message,
            code="RATE_LIMIT_EXCEEDED",
            details=details,
            **kwargs,
        )
        self.retry_after = retry_after or 60


class NotFoundError(APIError):
    """Raised when requested resource is not found (HTTP 404)."""

    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        **kwargs,
    ):
        message = f"{resource_type} not found"
        if resource_id:
            message = f"{resource_type} '{resource_id}' not found"

        kwargs.setdefault("status_code", 404)
        details = kwargs.pop("details", {})
        details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message,
            code="NOT_FOUND",
            details=details,
            recoverable=False,
            **kwargs,
        )


class ValidationError(APIError):
    """Raised when API validation fails (HTTP 400/422)."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        **kwargs,
    ):
        kwargs.setdefault("status_code", 400)
        details = kwargs.pop("details", {})
        if field:
            details["field"] = field

        super().__init__(
            message,
            code="VALIDATION_ERROR",
            details=details,
            recoverable=False,
            **kwargs,
        )


class ServerError(APIError):
    """Raised when server returns 5xx error."""

    def __init__(
        self,
        message: str = "Server error",
        **kwargs,
    ):
        kwargs.setdefault("status_code", 500)
        super().__init__(
            message,
            code="SERVER_ERROR",
            recoverable=True,  # Server errors are usually transient
            **kwargs,
        )


# ============================================
# Network Errors (Usually Recoverable)
# ============================================

class NetworkError(GLPError):
    """Base class for network-related errors.

    These errors are typically transient and recoverable with retry.
    """

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("recoverable", True)
        super().__init__(message, **kwargs)


class ConnectionError(NetworkError):
    """Raised when connection to server fails."""

    def __init__(
        self,
        message: str = "Failed to connect to server",
        host: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if host:
            details["host"] = host
        super().__init__(
            message,
            code="CONNECTION_ERROR",
            details=details,
            **kwargs,
        )


class TimeoutError(NetworkError):
    """Raised when request times out."""

    def __init__(
        self,
        message: str = "Request timed out",
        timeout_seconds: Optional[float] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(
            message,
            code="TIMEOUT_ERROR",
            details=details,
            **kwargs,
        )


class DNSError(NetworkError):
    """Raised when DNS resolution fails."""

    def __init__(
        self,
        message: str = "DNS resolution failed",
        hostname: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if hostname:
            details["hostname"] = hostname
        super().__init__(
            message,
            code="DNS_ERROR",
            details=details,
            **kwargs,
        )


# ============================================
# Database Errors
# ============================================

class DatabaseError(GLPError):
    """Base class for database-related errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("recoverable", True)
        super().__init__(message, **kwargs)


class ConnectionPoolError(DatabaseError):
    """Raised when database connection pool is exhausted or unavailable."""

    def __init__(
        self,
        message: str = "Database connection pool error",
        **kwargs,
    ):
        super().__init__(message, code="CONNECTION_POOL_ERROR", **kwargs)


class TransactionError(DatabaseError):
    """Raised when database transaction fails."""

    def __init__(
        self,
        message: str = "Database transaction failed",
        operation: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if operation:
            details["operation"] = operation
        super().__init__(
            message,
            code="TRANSACTION_ERROR",
            details=details,
            **kwargs,
        )


class IntegrityError(DatabaseError):
    """Raised when database integrity constraint is violated."""

    def __init__(
        self,
        message: str = "Database integrity error",
        constraint: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if constraint:
            details["constraint"] = constraint
        super().__init__(
            message,
            code="INTEGRITY_ERROR",
            details=details,
            recoverable=False,  # Usually need to fix data
            **kwargs,
        )


# ============================================
# Sync Errors
# ============================================

class SyncError(GLPError):
    """Base class for synchronization errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message, **kwargs)


class PartialSyncError(SyncError):
    """Raised when sync partially completes with some failures.

    Attributes:
        succeeded: Number of items successfully synced
        failed: Number of items that failed
        errors: List of individual errors
    """

    def __init__(
        self,
        message: str,
        succeeded: int = 0,
        failed: int = 0,
        errors: Optional[list[Exception]] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        details["succeeded"] = succeeded
        details["failed"] = failed
        if errors:
            details["error_count"] = len(errors)
            # Store first few error messages
            details["sample_errors"] = [str(e)[:100] for e in errors[:5]]

        super().__init__(
            message,
            code="PARTIAL_SYNC_ERROR",
            details=details,
            recoverable=True,  # Can retry failed items
            **kwargs,
        )
        self.succeeded = succeeded
        self.failed = failed
        self.errors = errors or []


class CircuitOpenError(SyncError):
    """Raised when circuit breaker is open and requests are being rejected.

    Attributes:
        reset_at: When the circuit breaker will attempt to close
    """

    def __init__(
        self,
        message: str = "Circuit breaker is open, requests rejected",
        reset_at: Optional[datetime] = None,
        failure_count: int = 0,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if reset_at:
            details["reset_at"] = reset_at.isoformat()
        details["failure_count"] = failure_count

        super().__init__(
            message,
            code="CIRCUIT_OPEN",
            details=details,
            recoverable=True,  # Will auto-recover when circuit closes
            **kwargs,
        )
        self.reset_at = reset_at
        self.failure_count = failure_count


class AsyncOperationError(SyncError):
    """Raised when an async API operation fails.

    Attributes:
        operation_url: URL of the failed operation
        operation_status: Final status of the operation
    """

    def __init__(
        self,
        message: str = "Async operation failed",
        operation_url: Optional[str] = None,
        operation_status: Optional[str] = None,
        **kwargs,
    ):
        details = kwargs.pop("details", {})
        if operation_url:
            details["operation_url"] = operation_url
        if operation_status:
            details["operation_status"] = operation_status

        super().__init__(
            message,
            code="ASYNC_OPERATION_FAILED",
            details=details,
            recoverable=False,
            **kwargs,
        )
        self.operation_url = operation_url
        self.operation_status = operation_status


class DeviceLimitError(GLPError):
    """Raised when device count exceeds API limits.

    Attributes:
        device_count: Number of devices provided
        max_devices: Maximum allowed devices
    """

    def __init__(
        self,
        device_count: int,
        max_devices: int = 25,
        **kwargs,
    ):
        message = f"Device count ({device_count}) exceeds maximum ({max_devices})"
        details = kwargs.pop("details", {})
        details["device_count"] = device_count
        details["max_devices"] = max_devices

        super().__init__(
            message,
            code="DEVICE_LIMIT_EXCEEDED",
            details=details,
            recoverable=False,
            **kwargs,
        )
        self.device_count = device_count
        self.max_devices = max_devices


# ============================================
# Error Aggregation
# ============================================

class ErrorCollector:
    """Collect multiple errors for batch operations.

    Useful when processing multiple items where you want to
    continue on failure and report all errors at the end.

    Example:
        collector = ErrorCollector()
        for item in items:
            try:
                process(item)
            except Exception as e:
                collector.add(e, context={"item_id": item.id})

        if collector.has_errors():
            raise collector.to_exception()
    """

    def __init__(self, max_errors: int = 100):
        self.errors: list[tuple[Exception, dict[str, Any]]] = []
        self.max_errors = max_errors

    def add(self, error: Exception, context: Optional[dict[str, Any]] = None):
        """Add an error with optional context."""
        if len(self.errors) < self.max_errors:
            self.errors.append((error, context or {}))

    def has_errors(self) -> bool:
        """Check if any errors were collected."""
        return len(self.errors) > 0

    def count(self) -> int:
        """Get number of errors collected."""
        return len(self.errors)

    def get_errors(self) -> list[tuple[Exception, dict[str, Any]]]:
        """Get all collected errors with their contexts."""
        return list(self.errors)

    def to_exception(self) -> PartialSyncError:
        """Convert collected errors to a PartialSyncError."""
        if not self.errors:
            raise ValueError("No errors to convert")

        return PartialSyncError(
            message=f"{len(self.errors)} error(s) occurred during operation",
            failed=len(self.errors),
            errors=[e for e, _ in self.errors],
        )

    def clear(self):
        """Clear all collected errors."""
        self.errors.clear()


# ============================================
# Exports
# ============================================

__all__ = [
    # Base
    "GLPError",
    # Configuration
    "ConfigurationError",
    # Authentication
    "AuthenticationError",
    "TokenFetchError",
    "TokenExpiredError",
    "InvalidCredentialsError",
    # API
    "APIError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
    "ServerError",
    # Network
    "NetworkError",
    "ConnectionError",
    "TimeoutError",
    "DNSError",
    # Database
    "DatabaseError",
    "ConnectionPoolError",
    "TransactionError",
    "IntegrityError",
    # Sync
    "SyncError",
    "PartialSyncError",
    "CircuitOpenError",
    "AsyncOperationError",
    # Device Management
    "DeviceLimitError",
    # Utilities
    "ErrorCollector",
]
