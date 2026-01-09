#!/usr/bin/env python3
"""Resilience Patterns for HPE GreenLake Platform API.

This module provides resilience patterns to handle transient failures:
    - Retry with exponential backoff
    - Circuit breaker
    - Graceful degradation helpers

These patterns help build fault-tolerant applications that can handle
network issues, rate limits, and service outages gracefully.

Example:
    # Retry with exponential backoff
    @retry(max_attempts=3, backoff_factor=2.0)
    async def fetch_data():
        return await api.get("/endpoint")

    # Circuit breaker
    circuit = CircuitBreaker(failure_threshold=5, timeout=60)
    result = await circuit.call(fetch_data)

Author: HPE GreenLake Team
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, TypeVar

from .exceptions import (
    CircuitOpenError,
    NetworkError,
    RateLimitError,
    ServerError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================
# Retry with Exponential Backoff
# ============================================

# Default exceptions that are considered retryable
DEFAULT_RETRYABLE_EXCEPTIONS = (
    NetworkError,
    RateLimitError,
    ServerError,
    asyncio.TimeoutError,
    ConnectionResetError,
    OSError,
)


def retry(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: tuple = DEFAULT_RETRYABLE_EXCEPTIONS,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """Decorator for retrying async functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including first try)
        backoff_factor: Multiplier for delay between attempts (2.0 = double each time)
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay in seconds between retries
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called before each retry with (exception, attempt)

    Returns:
        Decorator function

    Example:
        @retry(max_attempts=3, backoff_factor=2.0)
        async def fetch_data():
            return await api.get("/endpoint")

        # With custom retry callback
        def log_retry(exc, attempt):
            logger.warning(f"Retry {attempt} after {exc}")

        @retry(max_attempts=5, on_retry=log_retry)
        async def fetch_with_logging():
            return await api.get("/endpoint")
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception: Optional[Exception] = None
            delay = initial_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    # Check if RateLimitError has specific retry_after
                    if isinstance(e, RateLimitError) and e.retry_after:
                        delay = float(e.retry_after)

                    if attempt < max_attempts:
                        # Calculate delay with optional jitter
                        actual_delay = min(delay, max_delay)
                        if jitter:
                            actual_delay = actual_delay * (0.5 + random.random())

                        # Call retry callback if provided
                        if on_retry:
                            on_retry(e, attempt)

                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {actual_delay:.1f}s"
                        )

                        await asyncio.sleep(actual_delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed. Last error: {e}"
                        )
                        raise

                except Exception:
                    # Non-retryable exception, re-raise immediately
                    raise

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error")

        return wrapper
    return decorator


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args,
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = DEFAULT_RETRYABLE_EXCEPTIONS,
    **kwargs,
) -> T:
    """Retry an async function call with exponential backoff.

    This is a non-decorator version for when you need to retry inline.

    Args:
        func: Async function to call
        *args: Arguments to pass to func
        max_attempts: Maximum attempts
        backoff_factor: Delay multiplier
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        retryable_exceptions: Exceptions to retry on
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result from func

    Example:
        result = await retry_async(
            api.get,
            "/endpoint",
            max_attempts=3,
            params={"limit": 100}
        )
    """
    last_exception: Optional[Exception] = None
    delay = initial_delay

    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)

        except retryable_exceptions as e:
            last_exception = e

            if isinstance(e, RateLimitError) and e.retry_after:
                delay = float(e.retry_after)

            if attempt < max_attempts:
                actual_delay = min(delay * (0.5 + random.random()), max_delay)
                logger.warning(
                    f"Retry {attempt}/{max_attempts}: {e}. Waiting {actual_delay:.1f}s"
                )
                await asyncio.sleep(actual_delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                raise

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")


# ============================================
# Circuit Breaker
# ============================================

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failing, requests rejected immediately
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation. Requests pass through. Failures are counted.
    - OPEN: Too many failures. Requests are rejected immediately.
    - HALF_OPEN: After timeout, allow one request through to test recovery.

    State Transitions:
        CLOSED -> OPEN: When failure_count >= failure_threshold
        OPEN -> HALF_OPEN: When timeout expires
        HALF_OPEN -> CLOSED: When test request succeeds
        HALF_OPEN -> OPEN: When test request fails

    Attributes:
        failure_threshold: Number of failures before opening circuit
        timeout: Seconds to wait before attempting recovery (OPEN -> HALF_OPEN)
        success_threshold: Successes needed in HALF_OPEN to close circuit

    Example:
        circuit = CircuitBreaker(failure_threshold=5, timeout=60)

        try:
            result = await circuit.call(fetch_data)
        except CircuitOpenError:
            # Use fallback or cached data
            result = get_cached_data()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        success_threshold: int = 2,
        name: str = "default",
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            timeout: Seconds before trying to close circuit
            success_threshold: Successes needed in HALF_OPEN to close
            name: Circuit breaker name for logging
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        return self._state == CircuitState.OPEN

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    def _should_attempt(self) -> bool:
        """Check if request should be attempted based on current state."""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if timeout has passed
            if self._last_failure_time:
                elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                if elapsed >= self.timeout:
                    return True
            return False

        # HALF_OPEN - allow request
        return True

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs,
    ) -> T:
        """Execute function through the circuit breaker.

        Args:
            func: Async function to execute
            *args: Arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitOpenError: If circuit is open and timeout hasn't passed
            Any exception from func (after updating circuit state)
        """
        async with self._lock:
            if not self._should_attempt():
                reset_at = None
                if self._last_failure_time:
                    reset_at = self._last_failure_time + timedelta(seconds=self.timeout)

                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is open",
                    reset_at=reset_at,
                    failure_count=self._failure_count,
                )

            # Transition to HALF_OPEN if coming from OPEN
            if self._state == CircuitState.OPEN:
                logger.info(f"Circuit '{self.name}' transitioning to HALF_OPEN")
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0

        # Execute the function (outside the lock)
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure(e)
            raise

    async def _on_success(self):
        """Handle successful request."""
        async with self._lock:
            self._failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    logger.info(
                        f"Circuit '{self.name}' closing after "
                        f"{self._success_count} successes"
                    )
                    self._state = CircuitState.CLOSED
                    self._success_count = 0

    async def _on_failure(self, exception: Exception):
        """Handle failed request."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()

            if self._state == CircuitState.HALF_OPEN:
                # Test request failed, reopen circuit
                logger.warning(
                    f"Circuit '{self.name}' reopening after test failure: {exception}"
                )
                self._state = CircuitState.OPEN

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    logger.warning(
                        f"Circuit '{self.name}' opening after "
                        f"{self._failure_count} failures"
                    )
                    self._state = CircuitState.OPEN

    def reset(self):
        """Manually reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        logger.info(f"Circuit '{self.name}' manually reset")

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status for monitoring."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "timeout_seconds": self.timeout,
            "last_failure_at": (
                self._last_failure_time.isoformat()
                if self._last_failure_time
                else None
            ),
        }


# ============================================
# Graceful Degradation Helpers
# ============================================

async def with_fallback(
    primary: Callable[..., Awaitable[T]],
    fallback: Callable[..., Awaitable[T]],
    *args,
    log_error: bool = True,
    **kwargs,
) -> T:
    """Try primary function, fall back to fallback on error.

    Args:
        primary: Primary async function to try
        fallback: Fallback async function if primary fails
        *args: Arguments to pass to both functions
        log_error: Whether to log the primary error
        **kwargs: Keyword arguments to pass to both functions

    Returns:
        Result from primary or fallback

    Example:
        result = await with_fallback(
            fetch_from_api,
            fetch_from_cache,
            user_id=123
        )
    """
    try:
        return await primary(*args, **kwargs)
    except Exception as e:
        if log_error:
            logger.warning(f"Primary function failed, using fallback: {e}")
        return await fallback(*args, **kwargs)


async def with_timeout(
    func: Callable[..., Awaitable[T]],
    timeout_seconds: float,
    *args,
    default: Optional[T] = None,
    raise_on_timeout: bool = True,
    **kwargs,
) -> Optional[T]:
    """Execute async function with timeout.

    Args:
        func: Async function to execute
        timeout_seconds: Maximum execution time in seconds
        *args: Arguments for func
        default: Value to return on timeout (if raise_on_timeout=False)
        raise_on_timeout: Whether to raise TimeoutError on timeout
        **kwargs: Keyword arguments for func

    Returns:
        Result from func, or default on timeout

    Raises:
        asyncio.TimeoutError: If timeout occurs and raise_on_timeout=True
    """
    try:
        return await asyncio.wait_for(
            func(*args, **kwargs),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        if raise_on_timeout:
            raise
        logger.warning(f"Function timed out after {timeout_seconds}s, returning default")
        return default


def try_or_default(
    default: T,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator that returns default value on any exception.

    Args:
        default: Value to return on exception

    Returns:
        Decorator function

    Example:
        @try_or_default(default=[])
        async def get_items():
            return await api.get("/items")
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"{func.__name__} failed, returning default: {e}")
                return default
        return wrapper
    return decorator


# ============================================
# Concurrent Processing Patterns
# ============================================

async def process_concurrent(
    items: list[T],
    processor: Callable[[T], Awaitable[Any]],
    max_concurrent: int = 10,
    return_exceptions: bool = False,
) -> list[Any]:
    """Process items concurrently with bounded concurrency.

    Uses a semaphore to limit the number of concurrent operations,
    preventing resource exhaustion when processing large item lists.

    Args:
        items: List of items to process
        processor: Async function to apply to each item
        max_concurrent: Maximum concurrent operations (default: 10)
        return_exceptions: If True, return exceptions instead of raising

    Returns:
        List of results in the same order as input items

    Example:
        async def fetch_user(user_id: int) -> dict:
            return await api.get(f"/users/{user_id}")

        users = await process_concurrent(
            user_ids,
            fetch_user,
            max_concurrent=5
        )
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_processor(item: T) -> Any:
        async with semaphore:
            return await processor(item)

    tasks = [bounded_processor(item) for item in items]
    return await asyncio.gather(*tasks, return_exceptions=return_exceptions)


async def process_pages_concurrent(
    pages_iterator,
    item_processor: Callable[[Any], Awaitable[Any]],
    max_concurrent: int = 10,
    on_page_complete: Optional[Callable[[int, list], None]] = None,
) -> tuple[list[Any], list[Exception]]:
    """Process paginated data with concurrent item processing.

    Fetches pages sequentially (respecting rate limits) but processes
    items within each page concurrently for optimal throughput.

    Args:
        pages_iterator: Async iterator yielding pages of items
        item_processor: Async function to process each item
        max_concurrent: Max concurrent item processors per page
        on_page_complete: Optional callback(page_num, results) after each page

    Returns:
        Tuple of (all_results, all_errors)

    Example:
        async for page in client.paginate("/devices"):
            # This processes items sequentially

        # Better: Process items concurrently within pages
        results, errors = await process_pages_concurrent(
            client.paginate("/devices"),
            process_device,
            max_concurrent=20
        )
    """
    all_results = []
    all_errors = []
    page_num = 0

    async for page in pages_iterator:
        page_num += 1

        results = await process_concurrent(
            page,
            item_processor,
            max_concurrent=max_concurrent,
            return_exceptions=True,
        )

        # Separate successes from failures
        page_results = []
        for result in results:
            if isinstance(result, Exception):
                all_errors.append(result)
            else:
                page_results.append(result)

        all_results.extend(page_results)

        if on_page_complete:
            on_page_complete(page_num, page_results)

    return all_results, all_errors


async def gather_with_errors(
    *coros_or_futures,
    max_concurrent: Optional[int] = None,
) -> tuple[list[Any], list[Exception]]:
    """Execute coroutines concurrently, separating results from errors.

    Unlike asyncio.gather(return_exceptions=True), this returns
    results and errors in separate lists for easier handling.

    Args:
        *coros_or_futures: Coroutines or futures to execute
        max_concurrent: Optional limit on concurrent execution

    Returns:
        Tuple of (successful_results, exceptions)

    Example:
        results, errors = await gather_with_errors(
            fetch_user(1),
            fetch_user(2),
            fetch_user(3),
        )
        if errors:
            logger.warning(f"{len(errors)} requests failed")
    """
    if max_concurrent:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded(coro):
            async with semaphore:
                return await coro

        coros_or_futures = [bounded(c) for c in coros_or_futures]

    outcomes = await asyncio.gather(*coros_or_futures, return_exceptions=True)

    results = []
    errors = []
    for outcome in outcomes:
        if isinstance(outcome, Exception):
            errors.append(outcome)
        else:
            results.append(outcome)

    return results, errors


async def run_concurrent_tasks(
    tasks_dict: dict[str, Callable[[], Awaitable[T]]],
    fail_fast: bool = False,
) -> dict[str, T | Exception]:
    """Run named tasks concurrently with result tracking.

    Provides TaskGroup-like functionality that works across Python versions.
    Each task is identified by a name for easy result retrieval.

    Args:
        tasks_dict: Dict mapping task names to async callables
        fail_fast: If True, cancel remaining tasks on first failure

    Returns:
        Dict mapping task names to results or exceptions

    Example:
        results = await run_concurrent_tasks({
            "devices": fetch_devices,
            "subscriptions": fetch_subscriptions,
            "users": fetch_users,
        })

        devices = results["devices"]
        if isinstance(devices, Exception):
            logger.error(f"Device fetch failed: {devices}")
    """
    async def execute_named(name: str, func: Callable[[], Awaitable[T]]) -> tuple[str, T | Exception]:
        try:
            result = await func()
            return (name, result)
        except Exception as e:
            return (name, e)

    if fail_fast:
        # Use TaskGroup for fail-fast behavior (Python 3.11+)
        task_handles: dict[str, asyncio.Task] = {}
        exception_occurred = False

        try:
            async with asyncio.TaskGroup() as tg:
                task_handles = {
                    name: tg.create_task(func())
                    for name, func in tasks_dict.items()
                }
        except ExceptionGroup:
            # TaskGroup raised ExceptionGroup - collect results outside the except block
            exception_occurred = True

        # Collect results (works whether exception occurred or not)
        results = {}
        for name, task in task_handles.items():
            if task.done():
                try:
                    results[name] = task.result()
                except Exception as e:
                    results[name] = e
            else:
                results[name] = asyncio.CancelledError("Task was cancelled")

        return results
    else:
        # Standard gather for non-fail-fast
        outcomes = await asyncio.gather(
            *[execute_named(name, func) for name, func in tasks_dict.items()],
            return_exceptions=True,
        )

        results = {}
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                # This shouldn't happen since execute_named catches exceptions
                continue
            name, result = outcome
            results[name] = result

        return results


class ConcurrentBatcher:
    """Batch and process items concurrently with configurable limits.

    Collects items and processes them in batches when the batch size
    is reached or when explicitly flushed.

    Attributes:
        batch_size: Number of items per batch
        max_concurrent: Max concurrent batch processors
        processor: Async function to process a batch

    Example:
        async def save_devices(devices: list[dict]):
            await db.insert_many("devices", devices)

        batcher = ConcurrentBatcher(
            batch_size=100,
            max_concurrent=3,
            processor=save_devices
        )

        async for page in client.paginate("/devices"):
            for device in page:
                await batcher.add(device)

        await batcher.flush()  # Process remaining items
    """

    def __init__(
        self,
        batch_size: int,
        processor: Callable[[list[Any]], Awaitable[Any]],
        max_concurrent: int = 3,
    ):
        self.batch_size = batch_size
        self.processor = processor
        self.max_concurrent = max_concurrent

        self._buffer: list[Any] = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._pending_tasks: list[asyncio.Task] = []
        self._results: list[Any] = []
        self._errors: list[Exception] = []

    async def add(self, item: Any) -> None:
        """Add an item to the buffer, processing if batch size reached."""
        self._buffer.append(item)

        if len(self._buffer) >= self.batch_size:
            await self._process_batch(self._buffer[:])
            self._buffer = []

    async def _process_batch(self, batch: list[Any]) -> None:
        """Process a batch with concurrency limiting."""
        async with self._semaphore:
            try:
                result = await self.processor(batch)
                self._results.append(result)
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
                self._errors.append(e)

    async def flush(self) -> tuple[list[Any], list[Exception]]:
        """Process any remaining items and wait for all batches.

        Returns:
            Tuple of (all_results, all_errors)
        """
        if self._buffer:
            await self._process_batch(self._buffer)
            self._buffer = []

        return self._results, self._errors

    @property
    def pending_count(self) -> int:
        """Number of items waiting to be processed."""
        return len(self._buffer)


# ============================================
# Exports
# ============================================

__all__ = [
    # Retry
    "retry",
    "retry_async",
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    # Graceful Degradation
    "with_fallback",
    "with_timeout",
    "try_or_default",
    # Concurrent Processing
    "process_concurrent",
    "process_pages_concurrent",
    "gather_with_errors",
    "run_concurrent_tasks",
    "ConcurrentBatcher",
]
