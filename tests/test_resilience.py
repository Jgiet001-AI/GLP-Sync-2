#!/usr/bin/env python3
"""Comprehensive tests for resilience patterns.

Tests cover:
    - Circuit breaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
    - Retry with exponential backoff behavior
    - Concurrent execution patterns
    - Graceful degradation helpers

These tests verify the resilience patterns work correctly under various
failure scenarios and concurrent workloads.
"""
import asyncio
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests", 1)[0])
from src.glp.api.resilience import (
    CircuitBreaker,
    CircuitState,
    ConcurrentBatcher,
    DEFAULT_RETRYABLE_EXCEPTIONS,
    gather_with_errors,
    process_concurrent,
    process_pages_concurrent,
    retry,
    retry_async,
    run_concurrent_tasks,
    try_or_default,
    with_fallback,
    with_timeout,
)
from src.glp.api.exceptions import (
    CircuitOpenError,
    NetworkError,
    RateLimitError,
    ServerError,
)


# ============================================
# Circuit Breaker State Transition Tests
# ============================================

class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state machine transitions."""

    def test_initial_state_is_closed(self):
        """Circuit should start in CLOSED state."""
        circuit = CircuitBreaker(failure_threshold=3)
        assert circuit.state == CircuitState.CLOSED
        assert not circuit.is_open
        assert circuit.failure_count == 0

    @pytest.mark.asyncio
    async def test_closed_to_open_after_failures(self):
        """Circuit should open after reaching failure threshold."""
        circuit = CircuitBreaker(failure_threshold=3, timeout=60.0)

        async def failing_func():
            raise ServerError("Server error", status_code=500)

        # First two failures - still closed
        for i in range(2):
            with pytest.raises(ServerError):
                await circuit.call(failing_func)

            assert circuit.state == CircuitState.CLOSED
            assert circuit.failure_count == i + 1

        # Third failure - should open
        with pytest.raises(ServerError):
            await circuit.call(failing_func)

        assert circuit.state == CircuitState.OPEN
        assert circuit.is_open
        assert circuit.failure_count == 3

    @pytest.mark.asyncio
    async def test_open_rejects_requests_immediately(self):
        """Open circuit should reject requests without calling function."""
        circuit = CircuitBreaker(failure_threshold=1, timeout=60.0)
        call_count = 0

        async def tracked_func():
            nonlocal call_count
            call_count += 1
            raise ServerError("fail", status_code=500)

        # Trigger open
        with pytest.raises(ServerError):
            await circuit.call(tracked_func)

        assert call_count == 1
        assert circuit.is_open

        # Should reject without calling
        with pytest.raises(CircuitOpenError):
            await circuit.call(tracked_func)

        assert call_count == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_timeout(self):
        """Circuit should transition to HALF_OPEN after timeout."""
        circuit = CircuitBreaker(failure_threshold=1, timeout=0.1)

        async def failing_func():
            raise ServerError("fail", status_code=500)

        # Trigger open
        with pytest.raises(ServerError):
            await circuit.call(failing_func)

        assert circuit.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Next call should transition to HALF_OPEN
        with pytest.raises(ServerError):
            await circuit.call(failing_func)

        # After failure in HALF_OPEN, goes back to OPEN
        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(self):
        """Circuit should close after successful requests in HALF_OPEN."""
        circuit = CircuitBreaker(
            failure_threshold=1,
            timeout=0.1,
            success_threshold=2,
        )

        call_count = 0

        async def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ServerError("fail", status_code=500)
            return "success"

        # Trigger open
        with pytest.raises(ServerError):
            await circuit.call(sometimes_fails)

        assert circuit.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # First success in HALF_OPEN
        result = await circuit.call(sometimes_fails)
        assert result == "success"
        assert circuit.state == CircuitState.HALF_OPEN

        # Second success - should close
        result = await circuit.call(sometimes_fails)
        assert result == "success"
        assert circuit.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self):
        """Circuit should reopen if request fails in HALF_OPEN state."""
        circuit = CircuitBreaker(failure_threshold=1, timeout=0.1)

        async def always_fails():
            raise ServerError("fail", status_code=500)

        # Trigger open
        with pytest.raises(ServerError):
            await circuit.call(always_fails)

        assert circuit.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Fail in HALF_OPEN - should reopen
        with pytest.raises(ServerError):
            await circuit.call(always_fails)

        assert circuit.state == CircuitState.OPEN

    def test_manual_reset(self):
        """Should be able to manually reset circuit to CLOSED."""
        circuit = CircuitBreaker(failure_threshold=1)
        circuit._state = CircuitState.OPEN
        circuit._failure_count = 10

        circuit.reset()

        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

    def test_get_status_returns_monitoring_data(self):
        """Should return comprehensive status for monitoring."""
        circuit = CircuitBreaker(
            failure_threshold=5,
            timeout=60.0,
            name="test_circuit",
        )

        status = circuit.get_status()

        assert status["name"] == "test_circuit"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 5
        assert status["timeout_seconds"] == 60.0


# ============================================
# Retry Behavior Tests
# ============================================

class TestRetryBehavior:
    """Test retry decorator and function behavior."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_first_attempt(self):
        """Should return immediately on success."""
        call_count = 0

        @retry(max_attempts=3)
        async def succeeds():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await succeeds()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Should retry and succeed after transient failures."""
        call_count = 0

        @retry(max_attempts=3, initial_delay=0.01)
        async def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkError("Network error")
            return "success"

        result = await fails_twice()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausts_attempts(self):
        """Should raise after exhausting all attempts."""
        call_count = 0

        @retry(max_attempts=3, initial_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise NetworkError("Always fails")

        with pytest.raises(NetworkError):
            await always_fails()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_respects_rate_limit_delay(self):
        """Should wait for Retry-After on RateLimitError."""
        call_count = 0
        start_time = time.time()

        @retry(max_attempts=2, initial_delay=0.01)
        async def rate_limited():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError(
                    "Rate limited",
                    retry_after=0.1,
                    endpoint="/test"
                )
            return "success"

        result = await rate_limited()
        elapsed = time.time() - start_time

        assert result == "success"
        assert call_count == 2
        # Allow small tolerance for timing variance
        assert elapsed >= 0.08  # Waited approximately for retry_after

    @pytest.mark.asyncio
    async def test_retry_non_retryable_fails_immediately(self):
        """Should not retry non-retryable exceptions."""
        call_count = 0

        @retry(max_attempts=3, retryable_exceptions=(NetworkError,))
        async def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            await raises_value_error()

        assert call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_retry_async_inline(self):
        """Test inline retry_async function."""
        call_count = 0

        async def flaky_function(value: int):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise NetworkError("Flaky")
            return value * 2

        result = await retry_async(
            flaky_function,
            42,
            max_attempts=3,
            initial_delay=0.01,
        )

        assert result == 84
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_callback_called(self):
        """Should call on_retry callback before each retry."""
        retry_calls = []

        def on_retry_callback(exc, attempt):
            retry_calls.append((str(exc), attempt))

        @retry(max_attempts=3, initial_delay=0.01, on_retry=on_retry_callback)
        async def fails_twice():
            if len(retry_calls) < 2:
                raise NetworkError("Fail")
            return "success"

        await fails_twice()

        assert len(retry_calls) == 2
        assert retry_calls[0][1] == 1  # First retry
        assert retry_calls[1][1] == 2  # Second retry

    @pytest.mark.asyncio
    async def test_exponential_backoff_increases_delay(self):
        """Verify delay increases exponentially between retries."""
        delays = []
        last_time = [None]

        @retry(
            max_attempts=4,
            initial_delay=0.05,
            backoff_factor=2.0,
            jitter=False,  # Disable jitter for predictable timing
        )
        async def track_delays():
            now = time.time()
            if last_time[0] is not None:
                delays.append(now - last_time[0])
            last_time[0] = now
            raise NetworkError("fail")

        with pytest.raises(NetworkError):
            await track_delays()

        # Should have 3 delays (between 4 attempts)
        assert len(delays) == 3

        # Each delay should be roughly double the previous (with some tolerance)
        # First ~0.05s, second ~0.1s, third ~0.2s
        assert delays[1] > delays[0] * 1.5  # At least 1.5x growth
        assert delays[2] > delays[1] * 1.5


# ============================================
# Concurrent Execution Tests
# ============================================

class TestConcurrentExecution:
    """Test concurrent processing patterns."""

    @pytest.mark.asyncio
    async def test_process_concurrent_basic(self):
        """Should process items concurrently."""
        processed = []

        async def processor(item: int):
            await asyncio.sleep(0.01)
            processed.append(item)
            return item * 2

        items = [1, 2, 3, 4, 5]
        results = await process_concurrent(items, processor)

        assert len(results) == 5
        assert set(results) == {2, 4, 6, 8, 10}
        assert set(processed) == {1, 2, 3, 4, 5}

    @pytest.mark.asyncio
    async def test_process_concurrent_respects_limit(self):
        """Should not exceed max_concurrent limit."""
        concurrent_count = 0
        max_seen = 0

        async def tracked_processor(item: int):
            nonlocal concurrent_count, max_seen
            concurrent_count += 1
            max_seen = max(max_seen, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return item

        items = list(range(20))
        await process_concurrent(items, tracked_processor, max_concurrent=5)

        assert max_seen <= 5

    @pytest.mark.asyncio
    async def test_process_concurrent_with_errors(self):
        """Should handle errors when return_exceptions=True."""
        async def sometimes_fails(item: int):
            if item % 2 == 0:
                raise ValueError(f"Even number: {item}")
            return item * 2

        items = [1, 2, 3, 4, 5]
        results = await process_concurrent(
            items,
            sometimes_fails,
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 3  # 1, 3, 5
        assert len(failures) == 2  # 2, 4

    @pytest.mark.asyncio
    async def test_gather_with_errors_separates_results(self):
        """Should separate successful results from exceptions."""
        async def success():
            return "ok"

        async def failure():
            raise ValueError("fail")

        results, errors = await gather_with_errors(
            success(),
            failure(),
            success(),
            failure(),
        )

        assert len(results) == 2
        assert len(errors) == 2
        assert all(r == "ok" for r in results)
        assert all(isinstance(e, ValueError) for e in errors)

    @pytest.mark.asyncio
    async def test_gather_with_errors_max_concurrent(self):
        """Should respect max_concurrent limit."""
        concurrent_count = 0
        max_seen = 0

        async def tracked():
            nonlocal concurrent_count, max_seen
            concurrent_count += 1
            max_seen = max(max_seen, concurrent_count)
            await asyncio.sleep(0.02)
            concurrent_count -= 1
            return "ok"

        coros = [tracked() for _ in range(10)]
        results, errors = await gather_with_errors(*coros, max_concurrent=3)

        assert len(results) == 10
        assert len(errors) == 0
        assert max_seen <= 3

    @pytest.mark.asyncio
    async def test_run_concurrent_tasks_with_names(self):
        """Should return results keyed by task name."""
        async def fetch_devices():
            await asyncio.sleep(0.01)
            return ["device1", "device2"]

        async def fetch_subscriptions():
            await asyncio.sleep(0.01)
            return ["sub1"]

        results = await run_concurrent_tasks({
            "devices": fetch_devices,
            "subscriptions": fetch_subscriptions,
        })

        assert "devices" in results
        assert "subscriptions" in results
        assert results["devices"] == ["device1", "device2"]
        assert results["subscriptions"] == ["sub1"]

    @pytest.mark.asyncio
    async def test_run_concurrent_tasks_with_failures(self):
        """Should capture exceptions in results dict."""
        async def succeeds():
            return "ok"

        async def fails():
            raise ValueError("task failed")

        results = await run_concurrent_tasks({
            "success": succeeds,
            "failure": fails,
        })

        assert results["success"] == "ok"
        assert isinstance(results["failure"], ValueError)

    @pytest.mark.asyncio
    async def test_process_pages_concurrent(self):
        """Should process paginated data with concurrent item processing."""
        processed_items = []

        async def mock_paginator():
            yield [1, 2, 3]
            yield [4, 5, 6]
            yield [7, 8, 9]

        async def item_processor(item: int):
            await asyncio.sleep(0.01)
            processed_items.append(item)
            return item * 10

        page_callbacks = []

        def on_page(page_num, results):
            page_callbacks.append((page_num, len(results)))

        results, errors = await process_pages_concurrent(
            mock_paginator(),
            item_processor,
            max_concurrent=5,
            on_page_complete=on_page,
        )

        assert len(results) == 9
        assert set(results) == {10, 20, 30, 40, 50, 60, 70, 80, 90}
        assert len(errors) == 0
        assert len(page_callbacks) == 3


# ============================================
# Concurrent Batcher Tests
# ============================================

class TestConcurrentBatcher:
    """Test ConcurrentBatcher class."""

    @pytest.mark.asyncio
    async def test_batcher_processes_full_batches(self):
        """Should process batch when batch_size reached."""
        batches_processed = []

        async def processor(batch: list):
            batches_processed.append(batch.copy())
            return len(batch)

        batcher = ConcurrentBatcher(
            batch_size=3,
            processor=processor,
        )

        for i in range(5):
            await batcher.add(i)

        # Should have processed one batch of 3
        assert len(batches_processed) == 1
        assert batches_processed[0] == [0, 1, 2]

        # Remaining 2 items in buffer
        assert batcher.pending_count == 2

    @pytest.mark.asyncio
    async def test_batcher_flush_processes_remaining(self):
        """Should process remaining items on flush."""
        batches_processed = []

        async def processor(batch: list):
            batches_processed.append(batch.copy())
            return len(batch)

        batcher = ConcurrentBatcher(
            batch_size=3,
            processor=processor,
        )

        for i in range(5):
            await batcher.add(i)

        results, errors = await batcher.flush()

        # Should have processed 2 batches total
        assert len(batches_processed) == 2
        assert batches_processed[1] == [3, 4]
        assert batcher.pending_count == 0

    @pytest.mark.asyncio
    async def test_batcher_collects_errors(self):
        """Should collect errors from failed batches."""
        call_count = 0

        async def failing_processor(batch: list):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First batch failed")
            return len(batch)

        batcher = ConcurrentBatcher(
            batch_size=2,
            processor=failing_processor,
        )

        for i in range(4):
            await batcher.add(i)

        results, errors = await batcher.flush()

        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)


# ============================================
# Graceful Degradation Tests
# ============================================

class TestGracefulDegradation:
    """Test graceful degradation helpers."""

    @pytest.mark.asyncio
    async def test_with_fallback_uses_primary(self):
        """Should use primary when it succeeds."""
        async def primary():
            return "primary"

        async def fallback():
            return "fallback"

        result = await with_fallback(primary, fallback)

        assert result == "primary"

    @pytest.mark.asyncio
    async def test_with_fallback_uses_fallback_on_error(self):
        """Should use fallback when primary fails."""
        async def primary():
            raise ValueError("fail")

        async def fallback():
            return "fallback"

        result = await with_fallback(primary, fallback, log_error=False)

        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_with_timeout_succeeds_within_limit(self):
        """Should return result when completed within timeout."""
        async def fast_func():
            await asyncio.sleep(0.01)
            return "done"

        result = await with_timeout(fast_func, 1.0)

        assert result == "done"

    @pytest.mark.asyncio
    async def test_with_timeout_raises_on_exceed(self):
        """Should raise TimeoutError when limit exceeded."""
        async def slow_func():
            await asyncio.sleep(10)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await with_timeout(slow_func, 0.05, raise_on_timeout=True)

    @pytest.mark.asyncio
    async def test_with_timeout_returns_default(self):
        """Should return default when timeout and raise_on_timeout=False."""
        async def slow_func():
            await asyncio.sleep(10)
            return "done"

        result = await with_timeout(
            slow_func,
            0.05,
            default="timed_out",
            raise_on_timeout=False,
        )

        assert result == "timed_out"

    @pytest.mark.asyncio
    async def test_try_or_default_returns_result(self):
        """Should return result on success."""
        @try_or_default(default=[])
        async def get_items():
            return [1, 2, 3]

        result = await get_items()

        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_try_or_default_returns_default_on_error(self):
        """Should return default on any exception."""
        @try_or_default(default=[])
        async def get_items():
            raise RuntimeError("fail")

        result = await get_items()

        assert result == []


# ============================================
# Integration Tests
# ============================================

class TestResilienceIntegration:
    """Integration tests combining multiple resilience patterns."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_retry(self):
        """Test circuit breaker working with retry pattern."""
        circuit = CircuitBreaker(failure_threshold=2, timeout=0.1)
        call_count = 0

        @retry(max_attempts=2, initial_delay=0.01)
        async def retryable_operation():
            nonlocal call_count
            call_count += 1
            return await circuit.call(async_always_fails)

        async def async_always_fails():
            raise ServerError("fail", status_code=500)

        # First attempt: retries twice, fails, opens circuit
        with pytest.raises(ServerError):
            await retryable_operation()

        # Circuit should be open after 2 calls
        assert circuit.is_open

    @pytest.mark.asyncio
    async def test_concurrent_with_circuit_breaker(self):
        """Test concurrent processing with circuit breaker protection."""
        circuit = CircuitBreaker(failure_threshold=5, timeout=60.0)
        success_count = 0
        failure_count = 0

        async def protected_call(item: int):
            nonlocal success_count, failure_count
            try:
                result = await circuit.call(process_item, item)
                success_count += 1
                return result
            except (ServerError, CircuitOpenError):
                failure_count += 1
                return None

        async def process_item(item: int):
            if item % 3 == 0:
                raise ServerError("fail", status_code=500)
            return item * 2

        items = list(range(1, 21))  # 1-20
        results = await process_concurrent(
            items,
            protected_call,
            max_concurrent=5,
        )

        # Some succeeded, some failed
        assert success_count > 0
        assert failure_count > 0

        # Non-None results should be doubled values
        valid_results = [r for r in results if r is not None]
        assert all(r % 2 == 0 for r in valid_results)


# ============================================
# Run tests
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
