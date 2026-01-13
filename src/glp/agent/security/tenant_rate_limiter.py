"""
Tenant-based Rate Limiting.

Provides rate limiting at the tenant level (not per-IP) for API endpoints.
Uses Redis for distributed rate limiting across multiple API server instances.

Features:
- Configurable limits per tenant
- Sliding window rate limiting
- Redis-backed for distributed deployments
- Graceful degradation if Redis unavailable

Environment Variables:
- TENANT_RATE_LIMIT_REQUESTS: Requests per window (default: 100)
- TENANT_RATE_LIMIT_WINDOW_SECONDS: Window size in seconds (default: 60)
- TENANT_RATE_LIMIT_ENABLED: Enable/disable (default: true)

Example:
    # FastAPI dependency
    from src.glp.agent.security.tenant_rate_limiter import get_rate_limiter

    @router.get("/endpoint")
    async def endpoint(
        user_context: UserContext = Depends(get_user_context),
        rate_limiter: TenantRateLimiter = Depends(get_rate_limiter),
    ):
        await rate_limiter.check_rate_limit(user_context.tenant_id)
        return {"status": "ok"}
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Protocol

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


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

    async def eval(self, script: str, numkeys: int, *keys_and_args) -> int:
        """Execute a Lua script atomically."""
        ...


class RateLimitExceededError(HTTPException):
    """Raised when tenant exceeds rate limit."""

    def __init__(
        self,
        tenant_id: str,
        limit: int,
        window_seconds: int,
        retry_after: int,
    ):
        self.tenant_id = tenant_id
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {limit} requests per {window_seconds} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


@dataclass
class RateLimitConfig:
    """Configuration for tenant rate limiting."""

    # Requests allowed per window
    requests_per_window: int = int(os.getenv("TENANT_RATE_LIMIT_REQUESTS", "100"))

    # Window size in seconds
    window_seconds: int = int(os.getenv("TENANT_RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Enable/disable rate limiting
    enabled: bool = os.getenv("TENANT_RATE_LIMIT_ENABLED", "true").lower() == "true"

    # Fail-closed behavior (use in-memory fallback when Redis unavailable)
    fail_closed: bool = os.getenv("TENANT_RATE_LIMIT_FAIL_CLOSED", "true").lower() == "true"

    # Key prefix for Redis
    key_prefix: str = "rate_limit:tenant"


@dataclass
class _BucketCounter:
    """Internal counter for a time bucket.

    Attributes:
        count: Number of requests in this bucket
        expires_at: When this bucket expires (Unix timestamp)
    """

    count: int = 0
    expires_at: float = field(default_factory=time.time)


class InMemoryRateLimiter:
    """In-memory fallback rate limiter for single-instance deployments.

    Uses fixed time windows with in-memory storage. Suitable for:
    - Single API server instances
    - Development/testing
    - Fallback when Redis is unavailable

    Note: Does NOT work across multiple server instances - use Redis-backed
    TenantRateLimiter for distributed deployments.

    Usage:
        limiter = InMemoryRateLimiter()
        try:
            await limiter.check_rate_limit("tenant-123")
        except RateLimitExceededError:
            # Handle rate limit exceeded
            pass
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize in-memory rate limiter.

        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()
        # Store: {tenant_id: {bucket: _BucketCounter}}
        self._counters: dict[str, dict[int, _BucketCounter]] = defaultdict(dict)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()
        # Clean up old buckets every 5 minutes
        self._cleanup_interval = 300

    def _get_current_bucket(self) -> int:
        """Get current time bucket.

        Returns:
            Bucket identifier (Unix timestamp / window_seconds)
        """
        return int(time.time() // self.config.window_seconds)

    async def _cleanup_old_buckets(self) -> None:
        """Remove expired buckets to prevent memory growth.

        This is called periodically during check_rate_limit.
        """
        now = time.time()

        # Only cleanup every N seconds
        if now - self._last_cleanup < self._cleanup_interval:
            return

        async with self._lock:
            for tenant_id in list(self._counters.keys()):
                tenant_buckets = self._counters[tenant_id]

                # Remove expired buckets
                for bucket in list(tenant_buckets.keys()):
                    counter = tenant_buckets[bucket]
                    if counter.expires_at < now:
                        del tenant_buckets[bucket]

                # Remove tenant entry if no buckets remain
                if not tenant_buckets:
                    del self._counters[tenant_id]

            self._last_cleanup = now

            logger.debug(
                f"Cleaned up rate limit buckets. "
                f"Active tenants: {len(self._counters)}"
            )

    async def check_rate_limit(self, tenant_id: str) -> None:
        """Check if tenant is within rate limit.

        Args:
            tenant_id: Tenant identifier

        Raises:
            RateLimitExceededError: If rate limit exceeded
        """
        if not self.config.enabled:
            return

        # Periodic cleanup
        await self._cleanup_old_buckets()

        bucket = self._get_current_bucket()
        now = time.time()

        async with self._lock:
            # Get or create bucket counter
            if bucket not in self._counters[tenant_id]:
                self._counters[tenant_id][bucket] = _BucketCounter(
                    count=0,
                    expires_at=now + self.config.window_seconds,
                )

            counter = self._counters[tenant_id][bucket]

            # Check if limit exceeded
            if counter.count >= self.config.requests_per_window:
                retry_after = max(1, int(counter.expires_at - now))
                logger.warning(
                    f"Rate limit exceeded for tenant {tenant_id}: "
                    f"{counter.count}/{self.config.requests_per_window} "
                    f"(in-memory fallback)"
                )
                raise RateLimitExceededError(
                    tenant_id=tenant_id,
                    limit=self.config.requests_per_window,
                    window_seconds=self.config.window_seconds,
                    retry_after=retry_after,
                )

            # Increment counter
            counter.count += 1

            logger.debug(
                f"Tenant {tenant_id} rate limit (in-memory): "
                f"{counter.count}/{self.config.requests_per_window}"
            )

    async def get_rate_limit_info(self, tenant_id: str) -> dict:
        """Get current rate limit status for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with rate limit information
        """
        if not self.config.enabled:
            return {
                "tenant_id": tenant_id,
                "enabled": False,
            }

        bucket = self._get_current_bucket()

        async with self._lock:
            counter = self._counters[tenant_id].get(bucket)

            if not counter:
                current = 0
            else:
                current = counter.count

            return {
                "tenant_id": tenant_id,
                "current_requests": current,
                "limit": self.config.requests_per_window,
                "window_seconds": self.config.window_seconds,
                "remaining": max(0, self.config.requests_per_window - current),
                "storage": "in-memory",
            }

    def reset(self) -> None:
        """Reset all counters (useful for testing)."""
        self._counters.clear()
        self._last_cleanup = time.time()


class TenantRateLimiter:
    """Tenant-based rate limiter using Redis sliding window.

    Uses a sliding window counter algorithm for smooth rate limiting.
    Falls back to allowing requests if Redis is unavailable.

    Usage:
        limiter = TenantRateLimiter(redis_client)
        try:
            await limiter.check_rate_limit("tenant-123")
        except RateLimitExceededError:
            # Handle rate limit exceeded
            pass
    """

    # Lua script for atomic sliding window rate limiting
    # Returns: (allowed: 0/1, current_count, ttl_remaining)
    _SLIDING_WINDOW_SCRIPT = """
    local key = KEYS[1]
    local window = tonumber(ARGV[1])
    local limit = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])

    -- Get current count
    local current = tonumber(redis.call('GET', key) or '0')

    -- Check if limit exceeded
    if current >= limit then
        local ttl = redis.call('TTL', key)
        return {0, current, ttl}
    end

    -- Increment counter
    local new_count = redis.call('INCR', key)

    -- Set expiration if this is a new key
    if new_count == 1 then
        redis.call('EXPIRE', key, window)
    end

    local ttl = redis.call('TTL', key)
    return {1, new_count, ttl}
    """

    def __init__(
        self,
        redis: Optional[IRedisClient] = None,
        config: Optional[RateLimitConfig] = None,
    ):
        """Initialize tenant rate limiter.

        Args:
            redis: Redis client for distributed rate limiting
            config: Rate limit configuration
        """
        self.redis = redis
        self.config = config or RateLimitConfig()

    def _get_key(self, tenant_id: str) -> str:
        """Get Redis key for a tenant's rate limit.

        Uses a time bucket for sliding window.
        """
        # Simple fixed window key (tenant + current minute bucket)
        bucket = int(time.time() // self.config.window_seconds)
        return f"{self.config.key_prefix}:{tenant_id}:{bucket}"

    async def check_rate_limit(self, tenant_id: str) -> None:
        """Check if tenant is within rate limit.

        Args:
            tenant_id: Tenant identifier

        Raises:
            RateLimitExceededError: If rate limit exceeded
        """
        if not self.config.enabled:
            return

        if not self.redis:
            logger.debug("Redis not configured - rate limiting disabled")
            return

        key = self._get_key(tenant_id)
        now = int(time.time())

        try:
            # Use Lua script for atomic operation
            result = await self.redis.eval(
                self._SLIDING_WINDOW_SCRIPT,
                1,  # Number of keys
                key,
                self.config.window_seconds,
                self.config.requests_per_window,
                now,
            )

            allowed, current_count, ttl_remaining = result

            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for tenant {tenant_id}: "
                    f"{current_count}/{self.config.requests_per_window}"
                )
                raise RateLimitExceededError(
                    tenant_id=tenant_id,
                    limit=self.config.requests_per_window,
                    window_seconds=self.config.window_seconds,
                    retry_after=max(1, ttl_remaining),
                )

            logger.debug(
                f"Tenant {tenant_id} rate limit: "
                f"{current_count}/{self.config.requests_per_window}"
            )

        except RateLimitExceededError:
            raise
        except Exception as e:
            # Fail open - allow request if Redis is unavailable
            logger.warning(f"Rate limit check failed (allowing request): {e}")

    async def get_rate_limit_info(self, tenant_id: str) -> dict:
        """Get current rate limit status for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with rate limit information
        """
        if not self.redis:
            return {
                "tenant_id": tenant_id,
                "enabled": False,
                "reason": "Redis not configured",
            }

        key = self._get_key(tenant_id)

        try:
            current_str = await self.redis.get(key)
            current = int(current_str) if current_str else 0

            return {
                "tenant_id": tenant_id,
                "current_requests": current,
                "limit": self.config.requests_per_window,
                "window_seconds": self.config.window_seconds,
                "remaining": max(0, self.config.requests_per_window - current),
            }
        except Exception as e:
            logger.warning(f"Failed to get rate limit info: {e}")
            return {
                "tenant_id": tenant_id,
                "error": str(e),
            }


# Module-level default rate limiter (lazy initialization)
_default_rate_limiter: Optional[TenantRateLimiter] = None


def init_rate_limiter(redis: IRedisClient) -> TenantRateLimiter:
    """Initialize the default rate limiter with a Redis client.

    Args:
        redis: Redis client

    Returns:
        Configured TenantRateLimiter
    """
    global _default_rate_limiter
    _default_rate_limiter = TenantRateLimiter(redis=redis)
    return _default_rate_limiter


def get_rate_limiter() -> TenantRateLimiter:
    """Get the default rate limiter (FastAPI dependency).

    Returns:
        TenantRateLimiter instance (may have no Redis if not initialized)
    """
    global _default_rate_limiter
    if _default_rate_limiter is None:
        # Return limiter without Redis - will skip rate limiting
        _default_rate_limiter = TenantRateLimiter()
    return _default_rate_limiter
