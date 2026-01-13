"""
Background Task Worker for Agent Operations.

Provides a bounded queue with worker for background tasks like pattern learning,
fact extraction, and other non-blocking operations.

Key Features:
- Bounded queue prevents memory exhaustion under load
- Configurable retry with exponential backoff
- Metrics for monitoring queue health
- Graceful shutdown with task completion timeout

This replaces fire-and-forget asyncio.create_task calls which:
- Can lose errors silently
- Have no backpressure when overloaded
- Are difficult to audit/monitor
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a background task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class BackgroundTask:
    """A task queued for background execution."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    coro_func: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Any = None


@dataclass
class WorkerMetrics:
    """Metrics for monitoring the background worker."""

    tasks_submitted: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_dropped: int = 0  # Dropped due to queue full
    total_retries: int = 0
    current_queue_size: int = 0
    peak_queue_size: int = 0


class BackgroundWorker:
    """Background task worker with bounded queue.

    Usage:
        worker = BackgroundWorker(max_queue_size=100)
        await worker.start()

        # Queue a task
        task_id = await worker.submit(
            learn_pattern,
            tenant_id="123",
            pattern_type=PatternType.TOOL_SUCCESS,
        )

        # On shutdown
        await worker.stop(timeout=30)

    Attributes:
        max_queue_size: Maximum tasks in queue (prevents memory exhaustion)
        max_concurrent: Maximum concurrent task executions
        retry_base_delay: Base delay for exponential backoff (seconds)
    """

    def __init__(
        self,
        max_queue_size: int = 100,
        max_concurrent: int = 5,
        retry_base_delay: float = 1.0,
        max_retry_delay: float = 60.0,
    ):
        """Initialize the background worker.

        Args:
            max_queue_size: Maximum tasks in queue
            max_concurrent: Maximum concurrent executions
            retry_base_delay: Base delay for retries (seconds)
            max_retry_delay: Maximum retry delay (seconds)
        """
        self.max_queue_size = max_queue_size
        self.max_concurrent = max_concurrent
        self.retry_base_delay = retry_base_delay
        self.max_retry_delay = max_retry_delay

        self._queue: asyncio.Queue[BackgroundTask] = asyncio.Queue(maxsize=max_queue_size)
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._metrics = WorkerMetrics()
        self._shutdown_event = asyncio.Event()

    @property
    def metrics(self) -> WorkerMetrics:
        """Get current metrics."""
        self._metrics.current_queue_size = self._queue.qsize()
        return self._metrics

    async def start(self) -> None:
        """Start the background worker."""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()

        # Start worker tasks
        for i in range(self.max_concurrent):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)

        logger.info(f"Background worker started with {self.max_concurrent} workers")

    async def stop(self, timeout: float = 30.0) -> None:
        """Stop the worker gracefully.

        Args:
            timeout: Maximum time to wait for tasks to complete
        """
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        # Wait for queue to drain (with timeout)
        if not self._queue.empty():
            logger.info(f"Waiting for {self._queue.qsize()} tasks to complete...")
            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    f"Shutdown timeout: {self._queue.qsize()} tasks remaining"
                )

        # Cancel workers
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        logger.info("Background worker stopped")

    async def submit(
        self,
        coro_func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        name: str = "",
        max_attempts: int = 3,
        **kwargs: Any,
    ) -> Optional[UUID]:
        """Submit a task for background execution.

        Args:
            coro_func: Async function to execute
            *args: Positional arguments for the function
            name: Human-readable task name for logging
            max_attempts: Maximum retry attempts
            **kwargs: Keyword arguments for the function

        Returns:
            Task UUID if submitted, None if queue is full
        """
        if not self._running:
            logger.warning("Background worker not running - task not submitted")
            return None

        task = BackgroundTask(
            name=name or coro_func.__name__,
            coro_func=coro_func,
            args=args,
            kwargs=kwargs,
            max_attempts=max_attempts,
        )

        try:
            self._queue.put_nowait(task)
            self._metrics.tasks_submitted += 1
            self._metrics.peak_queue_size = max(
                self._metrics.peak_queue_size, self._queue.qsize()
            )
            logger.debug(f"Task {task.id} ({task.name}) queued")
            return task.id
        except asyncio.QueueFull:
            self._metrics.tasks_dropped += 1
            logger.warning(
                f"Queue full ({self.max_queue_size}) - dropped task: {task.name}"
            )
            return None

    async def _worker_loop(self, worker_id: int) -> None:
        """Worker loop that processes tasks from the queue."""
        logger.debug(f"Worker {worker_id} started")

        while self._running or not self._queue.empty():
            try:
                # Use timeout to allow checking _running flag
                try:
                    task = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                await self._execute_task(task, worker_id)
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Worker {worker_id} error: {e}")

        logger.debug(f"Worker {worker_id} stopped")

    async def _execute_task(self, task: BackgroundTask, worker_id: int) -> None:
        """Execute a single task with retry logic."""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        task.attempts += 1

        try:
            if task.coro_func is None:
                raise ValueError("Task has no coroutine function")

            task.result = await task.coro_func(*task.args, **task.kwargs)
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            self._metrics.tasks_completed += 1

            logger.debug(
                f"Task {task.id} ({task.name}) completed "
                f"(attempt {task.attempts}, worker {worker_id})"
            )

        except Exception as e:
            task.error = str(e)

            if task.attempts < task.max_attempts:
                # Retry with exponential backoff
                task.status = TaskStatus.RETRYING
                delay = min(
                    self.retry_base_delay * (2 ** (task.attempts - 1)),
                    self.max_retry_delay,
                )
                self._metrics.total_retries += 1

                logger.warning(
                    f"Task {task.id} ({task.name}) failed (attempt {task.attempts}), "
                    f"retrying in {delay:.1f}s: {e}"
                )

                await asyncio.sleep(delay)

                # Re-queue for retry (if queue not full)
                try:
                    self._queue.put_nowait(task)
                except asyncio.QueueFull:
                    task.status = TaskStatus.FAILED
                    self._metrics.tasks_failed += 1
                    logger.error(
                        f"Task {task.id} ({task.name}) retry failed - queue full"
                    )
            else:
                # Max retries exceeded
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                self._metrics.tasks_failed += 1

                logger.error(
                    f"Task {task.id} ({task.name}) failed after {task.attempts} attempts: {e}"
                )


# Global worker instance (initialized on demand)
_background_worker: Optional[BackgroundWorker] = None


def get_background_worker() -> BackgroundWorker:
    """Get the global background worker instance."""
    global _background_worker
    if _background_worker is None:
        _background_worker = BackgroundWorker()
    return _background_worker


async def init_background_worker(
    max_queue_size: int = 100,
    max_concurrent: int = 5,
) -> BackgroundWorker:
    """Initialize and start the global background worker."""
    global _background_worker
    _background_worker = BackgroundWorker(
        max_queue_size=max_queue_size,
        max_concurrent=max_concurrent,
    )
    await _background_worker.start()
    return _background_worker


async def shutdown_background_worker(timeout: float = 30.0) -> None:
    """Shutdown the global background worker."""
    global _background_worker
    if _background_worker:
        await _background_worker.stop(timeout=timeout)
        _background_worker = None
