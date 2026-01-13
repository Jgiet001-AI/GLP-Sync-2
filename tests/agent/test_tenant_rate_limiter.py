"""
Tests for tenant-based rate limiting with Redis failure scenarios.

Tests cover:
    - InMemoryRateLimiter: basic operations, concurrency, cleanup
    - TenantRateLimiter: Redis success, fail-closed, fail-open behaviors
    - Fail-closed behavior: Falls back to in-memory when Redis unavailable
    - Fail-open behavior: Allows requests when Redis unavailable (legacy mode)
    - Concurrent request handling in both normal and fallback modes

These tests verify the rate limiter works correctly under various
failure scenarios and enforces limits as expected.
"""
import asyncio
import time
from typing import Optional

import pytest

from src.glp.agent.security.tenant_rate_limiter import (
    InMemoryRateLimiter,
    RateLimitConfig,
    RateLimitExceededError,
    TenantRateLimiter,
)


# ============================================
# InMemoryRateLimiter Tests
# ============================================


class TestInMemoryRateLimiter:
    """Test in-memory fallback rate limiter."""

    @pytest.fixture
    def config(self):
        """Create test config with small limits for fast testing."""
        return RateLimitConfig(
            requests_per_window=5,
            window_seconds=60,
            enabled=True,
            fail_closed=True,
        )

    @pytest.fixture
    def limiter(self, config):
        """Create a fresh rate limiter for each test."""
        return InMemoryRateLimiter(config=config)

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self, limiter):
        """Should allow requests within the rate limit."""
        tenant_id = "tenant-123"

        # Make 5 requests (at the limit)
        for i in range(5):
            await limiter.check_rate_limit(tenant_id)

        # Verify counter
        info = await limiter.get_rate_limit_info(tenant_id)
        assert info["current_requests"] == 5
        assert info["remaining"] == 0

    @pytest.mark.asyncio
    async def test_rejects_requests_over_limit(self, limiter):
        """Should reject requests that exceed the rate limit."""
        tenant_id = "tenant-456"

        # Use up all 5 requests
        for _ in range(5):
            await limiter.check_rate_limit(tenant_id)

        # 6th request should fail
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.check_rate_limit(tenant_id)

        assert exc_info.value.tenant_id == tenant_id
        assert exc_info.value.limit == 5
        assert exc_info.value.window_seconds == 60
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_reset_clears_all_counters(self, limiter):
        """Reset should clear all tenant counters."""
        # Add requests for multiple tenants
        await limiter.check_rate_limit("tenant-1")
        await limiter.check_rate_limit("tenant-2")
        await limiter.check_rate_limit("tenant-3")

        # Reset
        limiter.reset()

        # Verify all counters cleared
        info1 = await limiter.get_rate_limit_info("tenant-1")
        info2 = await limiter.get_rate_limit_info("tenant-2")
        info3 = await limiter.get_rate_limit_info("tenant-3")

        assert info1["current_requests"] == 0
        assert info2["current_requests"] == 0
        assert info3["current_requests"] == 0

    @pytest.mark.asyncio
    async def test_different_tenants_have_separate_limits(self, limiter):
        """Each tenant should have independent rate limits."""
        # Use up limit for tenant-1
        for _ in range(5):
            await limiter.check_rate_limit("tenant-1")

        # tenant-1 should be blocked
        with pytest.raises(RateLimitExceededError):
            await limiter.check_rate_limit("tenant-1")

        # But tenant-2 should still work
        await limiter.check_rate_limit("tenant-2")

        info2 = await limiter.get_rate_limit_info("tenant-2")
        assert info2["current_requests"] == 1

    @pytest.mark.asyncio
    async def test_disabled_limiter_allows_all_requests(self, config):
        """Disabled rate limiter should allow unlimited requests."""
        config.enabled = False
        limiter = InMemoryRateLimiter(config=config)

        # Should allow many more than limit
        for _ in range(20):
            await limiter.check_rate_limit("tenant-unlimited")

        # No exception raised

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_when_disabled(self, config):
        """get_rate_limit_info should return enabled=False when disabled."""
        config.enabled = False
        limiter = InMemoryRateLimiter(config=config)

        info = await limiter.get_rate_limit_info("tenant-123")
        assert info["enabled"] is False
        assert info["tenant_id"] == "tenant-123"

    @pytest.mark.asyncio
    async def test_concurrent_requests_are_counted(self, limiter):
        """Concurrent requests should all be counted correctly."""
        tenant_id = "tenant-concurrent"

        # Fire 5 concurrent requests
        tasks = [limiter.check_rate_limit(tenant_id) for _ in range(5)]
        await asyncio.gather(*tasks)

        # All 5 should succeed
        info = await limiter.get_rate_limit_info(tenant_id)
        assert info["current_requests"] == 5

        # 6th should fail
        with pytest.raises(RateLimitExceededError):
            await limiter.check_rate_limit(tenant_id)

    @pytest.mark.asyncio
    async def test_storage_field_in_info(self, limiter):
        """get_rate_limit_info should indicate in-memory storage."""
        await limiter.check_rate_limit("tenant-123")
        info = await limiter.get_rate_limit_info("tenant-123")

        assert info["storage"] == "in-memory"

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_buckets(self):
        """Cleanup should remove expired buckets after window expires."""
        # Use very short window for testing
        config = RateLimitConfig(
            requests_per_window=5,
            window_seconds=1,  # 1 second window
            enabled=True,
        )
        limiter = InMemoryRateLimiter(config=config)
        limiter._cleanup_interval = 0  # Force cleanup on every check

        tenant_id = "tenant-cleanup"

        # Make a request
        await limiter.check_rate_limit(tenant_id)
        assert tenant_id in limiter._counters

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Next request triggers cleanup and creates new bucket
        await limiter.check_rate_limit(tenant_id)

        # Should have new bucket with count=1
        info = await limiter.get_rate_limit_info(tenant_id)
        assert info["current_requests"] == 1


# ============================================
# TenantRateLimiter with Redis Tests
# ============================================


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self, should_fail=False, fail_after=None):
        """
        Args:
            should_fail: If True, all operations raise ConnectionError
            fail_after: If set, fail after this many successful calls
        """
        self.should_fail = should_fail
        self.fail_after = fail_after
        self.call_count = 0
        self.counters = {}  # Simple in-memory counter for testing

    async def eval(self, script: str, numkeys: int, *keys_and_args):
        """Mock Lua script execution."""
        self.call_count += 1

        if self.should_fail or (self.fail_after and self.call_count > self.fail_after):
            raise ConnectionError("Redis connection failed")

        # Extract arguments
        key = keys_and_args[0]
        window = int(keys_and_args[1])
        limit = int(keys_and_args[2])

        # Simple counter logic
        current = self.counters.get(key, 0)

        if current >= limit:
            # Return: [allowed, current, ttl]
            return [0, current, window]

        # Increment
        self.counters[key] = current + 1

        # Return: [allowed, new_count, ttl]
        return [1, current + 1, window]

    async def get(self, key: str) -> Optional[str]:
        """Mock get operation."""
        if self.should_fail:
            raise ConnectionError("Redis connection failed")
        return str(self.counters.get(key, 0))

    def reset(self):
        """Reset counters (for testing)."""
        self.counters.clear()
        self.call_count = 0


class TestTenantRateLimiterRedisSuccess:
    """Test TenantRateLimiter when Redis is working."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return RateLimitConfig(
            requests_per_window=5,
            window_seconds=60,
            enabled=True,
            fail_closed=True,
        )

    @pytest.fixture
    def redis(self):
        """Create mock Redis client."""
        return MockRedisClient()

    @pytest.fixture
    def limiter(self, redis, config):
        """Create rate limiter with mock Redis."""
        return TenantRateLimiter(redis=redis, config=config)

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self, limiter, redis):
        """Should allow requests within limit when Redis works."""
        tenant_id = "tenant-redis-ok"

        # Make 5 requests
        for i in range(5):
            await limiter.check_rate_limit(tenant_id)

        # Verify Redis was called
        assert redis.call_count == 5

    @pytest.mark.asyncio
    async def test_rejects_requests_over_limit(self, limiter, redis):
        """Should reject requests over limit when Redis works."""
        tenant_id = "tenant-redis-limit"

        # Use up all 5 requests
        for _ in range(5):
            await limiter.check_rate_limit(tenant_id)

        # 6th request should fail
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.check_rate_limit(tenant_id)

        assert exc_info.value.tenant_id == tenant_id
        assert exc_info.value.limit == 5

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_success(self, limiter, redis):
        """Should return rate limit info when Redis works."""
        tenant_id = "tenant-info"

        # Make 3 requests
        for _ in range(3):
            await limiter.check_rate_limit(tenant_id)

        info = await limiter.get_rate_limit_info(tenant_id)
        assert info["tenant_id"] == tenant_id
        assert info["current_requests"] == 3
        assert info["limit"] == 5
        assert info["remaining"] == 2

    @pytest.mark.asyncio
    async def test_no_redis_client_skips_limiting(self, config):
        """Should skip rate limiting if Redis is not configured."""
        limiter = TenantRateLimiter(redis=None, config=config)

        # Should allow unlimited requests
        for _ in range(20):
            await limiter.check_rate_limit("tenant-no-redis")

        # No exception raised


# ============================================
# Fail-Closed Behavior Tests
# ============================================


class TestFailClosedBehavior:
    """Test fail-closed behavior (use in-memory fallback when Redis fails)."""

    @pytest.fixture
    def config(self):
        """Create test config with fail_closed=True."""
        return RateLimitConfig(
            requests_per_window=5,
            window_seconds=60,
            enabled=True,
            fail_closed=True,  # Fail closed
        )

    @pytest.fixture
    def failing_redis(self):
        """Create Redis client that always fails."""
        return MockRedisClient(should_fail=True)

    @pytest.fixture
    def limiter(self, failing_redis, config):
        """Create rate limiter with failing Redis."""
        return TenantRateLimiter(redis=failing_redis, config=config)

    @pytest.mark.asyncio
    async def test_uses_in_memory_fallback_when_redis_fails(self, limiter):
        """Should use in-memory fallback when Redis is unavailable."""
        tenant_id = "tenant-fallback"

        # Should succeed despite Redis failure
        await limiter.check_rate_limit(tenant_id)

        # Verify fallback was initialized
        assert limiter._in_memory_fallback is not None

    @pytest.mark.asyncio
    async def test_enforces_limits_in_fallback_mode(self, limiter):
        """Should enforce rate limits using in-memory fallback."""
        tenant_id = "tenant-fallback-limit"

        # Use up all 5 requests
        for _ in range(5):
            await limiter.check_rate_limit(tenant_id)

        # 6th request should fail with in-memory limiter
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.check_rate_limit(tenant_id)

        assert exc_info.value.tenant_id == tenant_id
        assert exc_info.value.limit == 5

    @pytest.mark.asyncio
    async def test_concurrent_requests_in_fallback(self, limiter):
        """Should handle concurrent requests in fallback mode."""
        tenant_id = "tenant-concurrent-fallback"

        # Fire 5 concurrent requests
        tasks = [limiter.check_rate_limit(tenant_id) for _ in range(5)]
        await asyncio.gather(*tasks)

        # 6th should fail
        with pytest.raises(RateLimitExceededError):
            await limiter.check_rate_limit(tenant_id)

    @pytest.mark.asyncio
    async def test_fallback_reuses_same_instance(self, limiter):
        """Should reuse the same in-memory fallback instance."""
        tenant_id = "tenant-reuse"

        # First request initializes fallback
        await limiter.check_rate_limit(tenant_id)
        fallback1 = limiter._in_memory_fallback

        # Second request reuses same fallback
        await limiter.check_rate_limit(tenant_id)
        fallback2 = limiter._in_memory_fallback

        assert fallback1 is fallback2

    @pytest.mark.asyncio
    async def test_fallback_inherits_config(self, limiter, config):
        """In-memory fallback should use same config as parent."""
        await limiter.check_rate_limit("tenant-config-test")

        fallback = limiter._in_memory_fallback
        assert fallback.config.requests_per_window == config.requests_per_window
        assert fallback.config.window_seconds == config.window_seconds


# ============================================
# Fail-Open Behavior Tests
# ============================================


class TestFailOpenBehavior:
    """Test fail-open behavior (allow requests when Redis fails)."""

    @pytest.fixture
    def config(self):
        """Create test config with fail_closed=False."""
        return RateLimitConfig(
            requests_per_window=5,
            window_seconds=60,
            enabled=True,
            fail_closed=False,  # Fail open (legacy mode)
        )

    @pytest.fixture
    def failing_redis(self):
        """Create Redis client that always fails."""
        return MockRedisClient(should_fail=True)

    @pytest.fixture
    def limiter(self, failing_redis, config):
        """Create rate limiter with failing Redis and fail-open config."""
        return TenantRateLimiter(redis=failing_redis, config=config)

    @pytest.mark.asyncio
    async def test_allows_unlimited_requests_when_redis_fails(self, limiter):
        """Should allow unlimited requests in fail-open mode."""
        tenant_id = "tenant-fail-open"

        # Should allow many requests despite Redis failure
        for _ in range(20):
            await limiter.check_rate_limit(tenant_id)

        # No exception raised

    @pytest.mark.asyncio
    async def test_does_not_initialize_fallback(self, limiter):
        """Should NOT initialize in-memory fallback in fail-open mode."""
        tenant_id = "tenant-no-fallback"

        # Make requests
        for _ in range(10):
            await limiter.check_rate_limit(tenant_id)

        # Fallback should remain None
        assert limiter._in_memory_fallback is None


# ============================================
# Transition Between Redis and Fallback Tests
# ============================================


class TestRedisToFallbackTransition:
    """Test transitioning from Redis to fallback and back."""

    @pytest.fixture
    def config(self):
        """Create test config with fail_closed=True."""
        return RateLimitConfig(
            requests_per_window=5,
            window_seconds=60,
            enabled=True,
            fail_closed=True,
        )

    @pytest.mark.asyncio
    async def test_transitions_to_fallback_after_redis_failure(self, config):
        """Should transition to fallback after Redis starts failing."""
        # Start with working Redis
        redis = MockRedisClient(fail_after=3)
        limiter = TenantRateLimiter(redis=redis, config=config)

        tenant_id = "tenant-transition"

        # First 3 requests use Redis
        for _ in range(3):
            await limiter.check_rate_limit(tenant_id)

        assert redis.call_count == 3
        assert limiter._in_memory_fallback is None

        # 4th request fails over to fallback
        await limiter.check_rate_limit(tenant_id)

        assert limiter._in_memory_fallback is not None

        # Subsequent requests use fallback
        await limiter.check_rate_limit(tenant_id)

        # Should have 2 requests in fallback (4th and 5th)
        info = await limiter._in_memory_fallback.get_rate_limit_info(tenant_id)
        assert info["current_requests"] == 2

    @pytest.mark.asyncio
    async def test_fallback_state_is_independent(self, config):
        """Fallback state should be independent from Redis state."""
        # Working Redis with 2 requests already made
        redis = MockRedisClient()
        limiter = TenantRateLimiter(redis=redis, config=config)

        tenant_id = "tenant-independent"

        # Make 2 requests via Redis
        await limiter.check_rate_limit(tenant_id)
        await limiter.check_rate_limit(tenant_id)

        # Now Redis fails
        redis.should_fail = True

        # Fallback starts from 0 (independent state)
        for _ in range(5):
            await limiter.check_rate_limit(tenant_id)

        # 6th request in fallback should fail
        with pytest.raises(RateLimitExceededError):
            await limiter.check_rate_limit(tenant_id)


# ============================================
# Edge Cases and Error Handling Tests
# ============================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_error_is_not_caught(self):
        """RateLimitExceededError should not be caught by exception handler."""
        config = RateLimitConfig(
            requests_per_window=1,
            window_seconds=60,
            enabled=True,
        )
        redis = MockRedisClient()
        limiter = TenantRateLimiter(redis=redis, config=config)

        tenant_id = "tenant-error-passthrough"

        # First request succeeds
        await limiter.check_rate_limit(tenant_id)

        # Second request raises RateLimitExceededError
        with pytest.raises(RateLimitExceededError):
            await limiter.check_rate_limit(tenant_id)

    @pytest.mark.asyncio
    async def test_get_rate_limit_info_handles_redis_failure(self):
        """get_rate_limit_info should handle Redis failures gracefully."""
        config = RateLimitConfig(enabled=True, fail_closed=True)
        redis = MockRedisClient(should_fail=True)
        limiter = TenantRateLimiter(redis=redis, config=config)

        info = await limiter.get_rate_limit_info("tenant-123")

        # Should return error info without crashing
        assert "error" in info
        assert info["tenant_id"] == "tenant-123"

    @pytest.mark.asyncio
    async def test_disabled_config_bypasses_all_checks(self):
        """Disabled rate limiting should bypass all checks."""
        config = RateLimitConfig(enabled=False)
        redis = MockRedisClient(should_fail=True)
        limiter = TenantRateLimiter(redis=redis, config=config)

        # Should allow unlimited requests even though Redis fails
        for _ in range(100):
            await limiter.check_rate_limit("tenant-disabled")

        # No exception raised
        assert redis.call_count == 0  # Redis not even called
