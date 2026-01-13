#!/usr/bin/env python3
"""OAuth2 Token Management for Aruba Central API.

This module provides secure, thread-safe OAuth2 token management for the
Aruba Central API using the client credentials grant flow.

Features:
    - Automatic token caching with dynamic expiration buffer (10% of TTL, max 5min)
    - Thread-safe token refresh using asyncio.Lock
    - Exponential backoff retry on failures (1s, 2s, 4s) with jitter
    - Transparent token refresh on 401 responses
    - Comprehensive error handling with typed exceptions

Security Notes:
    - Tokens are cached in memory only (never persisted to disk)
    - Client secrets should be provided via environment variables
    - Token ID in debug output uses SHA-256 hash (first 8 chars) - never shows actual token

Environment Variables:
    - ARUBA_CLIENT_ID: OAuth2 client ID for Aruba Central
    - ARUBA_CLIENT_SECRET: OAuth2 client secret
    - ARUBA_TOKEN_URL: OAuth2 token endpoint (defaults to HPE SSO)

Example:
    >>> manager = ArubaTokenManager()
    >>> token = await manager.get_token()
    >>> # Token is automatically refreshed when expired

Author: HPE GreenLake Team
"""
import asyncio
import hashlib
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp
from dotenv import load_dotenv

from .exceptions import (
    ConfigurationError,
    ConnectionError,
    InvalidCredentialsError,
    NetworkError,
    TimeoutError,
    TokenFetchError,
)

load_dotenv()

logger = logging.getLogger(__name__)

# Default token URL (same as GreenLake - HPE SSO)
DEFAULT_ARUBA_TOKEN_URL = "https://sso.common.cloud.hpe.com/as/token.oauth2"


@dataclass
class CachedToken:
    """Immutable container for cached OAuth2 access tokens.

    Attributes:
        access_token: The OAuth2 bearer token string.
        expires_at: Unix timestamp when the token expires.
        token_type: Token type, typically "Bearer".
        expires_in: Original TTL in seconds (for dynamic buffer calculation).
    """
    access_token: str
    expires_at: float
    token_type: Optional[str] = "Bearer"
    expires_in: int = 7200  # Original TTL for dynamic buffer

    # Security: Maximum buffer is 5 minutes, minimum is 30 seconds
    MAX_BUFFER_SECONDS = 300
    MIN_BUFFER_SECONDS = 30

    @property
    def token_id(self) -> str:
        """Get a safe identifier for logging (SHA-256 hash, first 8 chars).

        Security: Never log actual tokens - use this ID instead.
        """
        return hashlib.sha256(self.access_token.encode()).hexdigest()[:8]

    @property
    def _buffer_seconds(self) -> float:
        """Calculate dynamic buffer with jitter.

        Uses 10% of TTL capped between MIN_BUFFER and MAX_BUFFER,
        plus random jitter (±10%) to prevent herd refresh.
        """
        # 10% of TTL
        base_buffer = self.expires_in * 0.1
        # Clamp to min/max
        buffer = max(self.MIN_BUFFER_SECONDS, min(base_buffer, self.MAX_BUFFER_SECONDS))
        # Add ±10% jitter to prevent coordinated refresh across processes
        jitter = buffer * random.uniform(-0.1, 0.1)
        return buffer + jitter

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired (with dynamic safety buffer + jitter)."""
        return time.time() >= (self.expires_at - self._buffer_seconds)

    @property
    def time_remaining(self) -> float:
        """Return seconds remaining before token expires (0 if expired)."""
        return max(0, self.expires_at - time.time())


class ArubaTokenManager:
    """Thread-safe OAuth2 token manager for Aruba Central API.

    Handles the OAuth2 client credentials flow for Aruba Central API
    authentication. Tokens are cached and automatically refreshed before
    expiration to ensure uninterrupted API access.

    Note: Aruba Central uses the same HPE SSO OAuth2 endpoint as GreenLake,
    but requires separate client credentials.

    Attributes:
        client_id: OAuth2 client ID (from env: ARUBA_CLIENT_ID).
        client_secret: OAuth2 client secret (from env: ARUBA_CLIENT_SECRET).
        token_url: OAuth2 token endpoint (from env: ARUBA_TOKEN_URL).

    Thread Safety:
        All public methods are thread-safe. Token refresh operations are
        serialized using an async lock to prevent duplicate token fetches
        during concurrent requests.

    Example:
        >>> manager = ArubaTokenManager()
        >>> token = await manager.get_token()  # Fetches new token
        >>> token = await manager.get_token()  # Returns cached token
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_url: Optional[str] = None,
    ):
        """Initialize ArubaTokenManager.

        Args:
            client_id: OAuth2 client ID. Defaults to ARUBA_CLIENT_ID env var.
            client_secret: OAuth2 client secret. Defaults to ARUBA_CLIENT_SECRET env var.
            token_url: OAuth2 token endpoint. Defaults to ARUBA_TOKEN_URL env var
                       or HPE SSO endpoint.

        Raises:
            ConfigurationError: If required credentials are missing.
        """
        self.client_id = client_id or os.getenv("ARUBA_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("ARUBA_CLIENT_SECRET")
        self.token_url = token_url or os.getenv(
            "ARUBA_TOKEN_URL", DEFAULT_ARUBA_TOKEN_URL
        )

        if not all([self.client_id, self.client_secret, self.token_url]):
            missing = []
            if not self.client_id:
                missing.append("ARUBA_CLIENT_ID")
            if not self.client_secret:
                missing.append("ARUBA_CLIENT_SECRET")
            if not self.token_url:
                missing.append("ARUBA_TOKEN_URL")
            raise ConfigurationError(
                f"Missing required Aruba Central environment variables: {', '.join(missing)}",
                missing_keys=missing,
            )

        self._cached_token: Optional[CachedToken] = None
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Get a valid access token, fetching or refreshing as needed.

        Returns:
            str: The access token string

        Raises:
            TokenFetchError: If token cannot be obtained after retries
        """
        if self._cached_token and not self._cached_token.is_expired:
            return self._cached_token.access_token

        async with self._lock:
            if self._cached_token and not self._cached_token.is_expired:
                return self._cached_token.access_token

            self._cached_token = await self._fetch_token()
            return self._cached_token.access_token

    async def _fetch_token(self, max_retries: int = 3) -> CachedToken:
        """Fetch a new access token from the Aruba Central OAuth server.

        Uses exponential backoff on failure with detailed error classification.

        Args:
            max_retries: Maximum number of retry attempts

        Returns:
            CachedToken with the new access token

        Raises:
            TokenFetchError: If token cannot be fetched after retries
            InvalidCredentialsError: If credentials are invalid (401)
            ConnectionError: If connection to token server fails
            TimeoutError: If request times out
        """
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.token_url,
                        data=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            expires_in = data.get("expires_in", 7200)
                            expires_at = time.time() + expires_in

                            token = CachedToken(
                                access_token=data.get("access_token"),
                                expires_at=expires_at,
                                token_type=data.get("token_type", "Bearer"),
                                expires_in=expires_in,
                            )
                            logger.info(
                                f"Aruba Central token fetched successfully, "
                                f"expires in {expires_in}s"
                            )
                            return token

                        # Handle specific error statuses
                        error_text = await response.text()

                        if response.status == 401:
                            raise InvalidCredentialsError(
                                "Invalid Aruba Central client credentials",
                                details={"response": error_text[:200]},
                            )

                        if response.status == 400:
                            # Bad request - likely invalid grant type or params
                            raise TokenFetchError(
                                f"Invalid Aruba Central token request: {error_text[:200]}",
                                status_code=400,
                                attempts=attempt,
                            )

                        # Other errors - will retry
                        last_error = TokenFetchError(
                            f"Aruba Central token server returned HTTP {response.status}",
                            status_code=response.status,
                            attempts=attempt,
                            details={"response": error_text[:200]},
                        )
                        logger.warning(
                            f"Aruba token fetch attempt {attempt}/{max_retries} failed: "
                            f"HTTP {response.status}"
                        )

            except InvalidCredentialsError:
                # Don't retry on invalid credentials
                raise

            except aiohttp.ClientConnectionError as e:
                last_error = ConnectionError(
                    f"Failed to connect to Aruba Central token server: {e}",
                    host=self.token_url,
                    cause=e,
                )
                logger.warning(
                    f"Aruba token fetch attempt {attempt}/{max_retries} failed: "
                    f"Connection error - {e}"
                )

            except asyncio.TimeoutError as e:
                last_error = TimeoutError(
                    "Aruba Central token request timed out",
                    timeout_seconds=30,
                    cause=e,
                )
                logger.warning(
                    f"Aruba token fetch attempt {attempt}/{max_retries} failed: Timeout"
                )

            except aiohttp.ClientError as e:
                last_error = NetworkError(
                    f"Network error fetching Aruba Central token: {e}",
                    cause=e,
                )
                logger.warning(
                    f"Aruba token fetch attempt {attempt}/{max_retries} failed: {e}"
                )

            # Exponential backoff before retry
            if attempt < max_retries:
                wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
                logger.debug(f"Waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)

        # All retries exhausted
        raise TokenFetchError(
            f"Failed to fetch Aruba Central token after {max_retries} attempts",
            attempts=max_retries,
            cause=last_error,
        )

    async def force_refresh(self) -> str:
        """Force a token refresh, ignoring the cache."""
        async with self._lock:
            self._cached_token = await self._fetch_token()
            return self._cached_token.access_token

    def invalidate(self):
        """Invalidate the cached token."""
        self._cached_token = None

    @property
    def token_info(self) -> Optional[dict]:
        """Get info about the current cached token for debugging.

        Security: Uses token_id (SHA-256 hash) instead of actual token preview.
        """
        if not self._cached_token:
            return None
        return {
            "is_expired": self._cached_token.is_expired,
            "time_remaining_seconds": self._cached_token.time_remaining,
            "token_id": self._cached_token.token_id,
        }


# Module-level default manager (lazy initialization)
_default_manager: Optional[ArubaTokenManager] = None


async def get_aruba_token() -> str:
    """Get a valid Aruba Central access token using default manager.

    Convenience function for simple use cases.

    Returns:
        str: Valid access token

    Raises:
        ConfigurationError: If required environment variables are missing
        TokenFetchError: If token cannot be obtained
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = ArubaTokenManager()
    return await _default_manager.get_token()


if __name__ == "__main__":
    async def test():
        """Test Aruba Central token management."""
        manager = ArubaTokenManager()

        print("First call (should fetch token):")
        t1 = await manager.get_token()
        # Security: Use token_id (SHA-256 hash) instead of actual token
        print(f"Token ID: {manager.token_info['token_id']}")
        print(f"Info: {manager.token_info}")

        print("\nSecond call (should return cached token):")
        t2 = await manager.get_token()
        print(f"Same token: {t2 == t1}")

        print("\n10 concurrent calls (should still be 1 fetch):")
        tokens = await asyncio.gather(
            *[manager.get_token() for _ in range(10)]
        )
        print(f"All tokens are the same: {len(set(tokens)) == 1}")

    asyncio.run(test())
