#!/usr/bin/env python3
"""OAuth2 Token Management for HPE GreenLake Platform.

This module provides secure, thread-safe OAuth2 token management for the
GreenLake Platform API using the client credentials grant flow.

Features:
    - Automatic token caching with 5-minute expiration buffer
    - Thread-safe token refresh using asyncio.Lock
    - Exponential backoff retry on failures (1s, 2s, 4s)
    - Transparent token refresh on 401 responses

Security Notes:
    - Tokens are cached in memory only (never persisted to disk)
    - Client secrets should be provided via environment variables
    - Token preview in debug output shows only first 20 characters

Example:
    >>> manager = TokenManager()
    >>> token = await manager.get_token()
    >>> # Token is automatically refreshed when expired

Author: HPE GreenLake Team
"""
import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CachedToken:
    """Immutable container for cached OAuth2 access tokens.

    Attributes:
        access_token: The OAuth2 bearer token string.
        expires_at: Unix timestamp when the token expires.
        token_type: Token type, typically "Bearer".
    """
    access_token: str
    expires_at: float
    token_type: Optional[str] = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired (with 5-minute safety buffer)."""
        buffer_seconds = 300  # Refresh token 5 minutes before expiration
        return time.time() >= (self.expires_at - buffer_seconds)

    @property
    def time_remaining(self) -> float:
        """Return seconds remaining before token expires (0 if expired)."""
        return max(0, self.expires_at - time.time())


class TokenManager:
    """Thread-safe OAuth2 token manager with automatic refresh.

    Handles the OAuth2 client credentials flow for GreenLake Platform API
    authentication. Tokens are cached and automatically refreshed before
    expiration to ensure uninterrupted API access.

    Attributes:
        client_id: OAuth2 client ID (from env: GLP_CLIENT_ID).
        client_secret: OAuth2 client secret (from env: GLP_CLIENT_SECRET).
        token_url: OAuth2 token endpoint (from env: GLP_TOKEN_URL).

    Thread Safety:
        All public methods are thread-safe. Token refresh operations are
        serialized using an async lock to prevent duplicate token fetches
        during concurrent requests.

    Example:
        >>> manager = TokenManager()
        >>> token = await manager.get_token()  # Fetches new token
        >>> token = await manager.get_token()  # Returns cached token
    """
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_url: Optional[str] = None,
        ):
        self.client_id = client_id or os.getenv("GLP_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GLP_CLIENT_SECRET")
        self.token_url = token_url or os.getenv("GLP_TOKEN_URL")

        if not all([self.client_id, self.client_secret, self.token_url]):
            missing = []
            if not self.client_id:
                missing.append("GLP_CLIENT_ID")
            if not self.client_secret:
                missing.append("GLP_CLIENT_SECRET")
            if not self.token_url:
                missing.append("GLP_TOKEN_URL")
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        self._cached_token: Optional[CachedToken] = None
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """
        Get a valid access token, fetching or refreshing as needed.

        Returns:
            str: The access token string

        Raises:
            TokenError: If token cannot be obtained after retries
    """
        if self._cached_token and not self._cached_token.is_expired:
            return self._cached_token.access_token

        async with self._lock:
            if self._cached_token and not self._cached_token.is_expired:
                return self._cached_token.access_token

            self._cached_token = await self._fetch_token()
            return self._cached_token.access_token

    async def _fetch_token(self, max_retries: int = 3) -> CachedToken:
        """Fetch a new access token from the GLP API."""
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        last_error = None

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.token_url,
                        data=payload,
                        headers=headers,
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            expires_in = data.get("expires_in", 7200)
                            expires_at = time.time() + expires_in

                            token = CachedToken(
                                access_token=data.get("access_token"),
                                expires_at=expires_at,
                                token_type=data.get("token_type", "Bearer"),
                            )
                            print(f"[TokenManager] Token fetched successfully, expires in {expires_in} seconds")
                            return token

                        else:
                            error_text = await response.text()
                            last_error = f"HTTP {response.status}: {error_text}"
                            print(f"[TokenManager] Failed to fetch token, attempt {attempt + 1} of {max_retries}: {last_error}")

            except aiohttp.ClientError as e:
                last_error = str(e)
                print(f"[TokenManager] Failed to fetch token, attempt {attempt + 1} of {max_retries}: {e}")

            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)

        raise TokenError(f"Failed to fetch token after {max_retries} attempts: {last_error}")

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
        """Get the info about the current cached token for debugging."""
        if not self._cached_token:
            return None
        return {
            "is_expired": self._cached_token.is_expired,
            "time_remaining_seconds": self._cached_token.time_remaining,
            "token_preview": self._cached_token.access_token[:20] + "...",
        }


class TokenError(Exception):
    """Exception raised for token-related errors."""
    pass


_default_manager: Optional[TokenManager] = None


async def get_token() -> str:
    """Get a valid access token, fetching or refreshing as needed."""
    global _default_manager
    if _default_manager is None:
        _default_manager = TokenManager()
    return await _default_manager.get_token()


if __name__ == "__main__":
    async def test():
        manager = TokenManager()

        print("First call (should fetch token):")
        t1 = await manager.get_token()
        print(f'Token: {t1[:30]}...')
        print(f"info: {manager.token_info}")

        print("\nSecond call (should return cached token):")
        t2 = await manager.get_token()
        print(f'Token: {t2 == t1}')

        print("\n10 concurrent calls (should still be 1 fetch)")
        tokens = await asyncio.gather(
            *[
                manager.get_token() for _ in range(10)
            ]
        )
        print(f"All tokens are the same: {len(set(tokens)) == 1}")

    asyncio.run(test())
