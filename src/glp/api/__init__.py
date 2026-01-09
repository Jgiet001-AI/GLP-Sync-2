"""GreenLake API modules.

This package provides the core API client and resource-specific syncers
for interacting with the HPE GreenLake Platform.

Classes:
    GLPClient: Generic HTTP client with pagination and retry logic
    TokenManager: OAuth2 token management with caching
    DeviceSyncer: Device inventory synchronization

Exceptions:
    TokenError: Token acquisition failures
    APIError: API request failures
    GLPClientError: Base exception for client errors
"""
from .auth import TokenError, TokenManager, get_token
from .client import (
    DEVICES_PAGINATION,
    SUBSCRIPTIONS_PAGINATION,
    APIError,
    GLPClient,
    GLPClientError,
    PaginationConfig,
    RateLimitError,
)
from .devices import DeviceSyncer
from .subscriptions import SubscriptionSyncer

__all__ = [
    # Auth
    "TokenManager",
    "TokenError",
    "get_token",
    # Client
    "GLPClient",
    "GLPClientError",
    "APIError",
    "RateLimitError",
    "PaginationConfig",
    "DEVICES_PAGINATION",
    "SUBSCRIPTIONS_PAGINATION",
    # Syncers
    "DeviceSyncer",
    "SubscriptionSyncer",
]
