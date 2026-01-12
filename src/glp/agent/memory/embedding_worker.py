"""
Background Embedding Worker.

Processes embedding jobs asynchronously using SKIP LOCKED pattern
for safe concurrent processing. Handles both message and memory embeddings.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Embedding job status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"  # Dead letter queue - max retries exceeded


class SourceType(str, Enum):
    """Source of the embedding job."""

    MESSAGE = "message"
    MEMORY = "memory"


@dataclass
class EmbeddingJob:
    """Represents an embedding job to process."""

    id: UUID
    tenant_id: str
    source_type: SourceType
    source_id: UUID
    content: str
    status: JobStatus
    retry_count: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class IAsyncDBPool(Protocol):
    """Protocol for async database pool."""

    async def acquire(self): ...
    async def execute(self, query: str, *args) -> str: ...
    async def fetch(self, query: str, *args) -> list[Any]: ...
    async def fetchrow(self, query: str, *args) -> Optional[Any]: ...
    async def fetchval(self, query: str, *args) -> Any: ...


class IEmbeddingProvider(Protocol):
    """Protocol for embedding generation."""

    async def embed(self, text: str) -> tuple[list[float], str, int]: ...
    async def embed_batch(
        self, texts: list[str]
    ) -> list[tuple[list[float], str, int]]: ...


class EmbeddingWorker:
    """Background worker for generating embeddings.

    Uses PostgreSQL's SKIP LOCKED for safe concurrent processing.
    Multiple workers can run simultaneously without conflicts.

    Features:
    - Batch processing for efficiency
    - Retry with exponential backoff
    - Dead letter queue for failed jobs
    - Graceful shutdown support
    - Per-tenant isolation

    Usage:
        worker = EmbeddingWorker(db_pool, embedding_provider)
        await worker.start()  # Runs until stopped
        # or
        await worker.process_batch(batch_size=10)  # Single batch

    Architecture:
        1. Jobs are created by triggers on agent_messages/agent_memory
        2. Worker claims jobs using SELECT FOR UPDATE SKIP LOCKED
        3. Embeddings are generated via provider
        4. Source records are updated with embeddings
        5. Jobs are marked completed or failed
    """

    # Configuration
    MAX_RETRIES = 3
    BASE_RETRY_DELAY_SECONDS = 5
    MAX_RETRY_DELAY_SECONDS = 300  # 5 minutes
    POLL_INTERVAL_SECONDS = 2
    DEFAULT_BATCH_SIZE = 10

    def __init__(
        self,
        db_pool: IAsyncDBPool,
        embedding_provider: IEmbeddingProvider,
        worker_id: Optional[str] = None,
    ):
        """Initialize the embedding worker.

        Args:
            db_pool: Async database connection pool
            embedding_provider: Provider for generating embeddings
            worker_id: Unique identifier for this worker instance
        """
        self.db = db_pool
        self.embedding_provider = embedding_provider
        self.worker_id = worker_id or f"worker-{id(self)}"
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        """Start the worker loop.

        Runs continuously until stop() is called.

        Args:
            batch_size: Number of jobs to process per batch
            poll_interval: Seconds between polling for new jobs
        """
        self._running = True
        self._shutdown_event.clear()

        logger.info(f"Starting embedding worker {self.worker_id}")

        while self._running:
            try:
                processed = await self.process_batch(batch_size)

                if processed == 0:
                    # No jobs available, wait before polling again
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=poll_interval,
                        )
                    except asyncio.TimeoutError:
                        pass  # Normal timeout, continue loop
                else:
                    logger.debug(
                        f"Worker {self.worker_id} processed {processed} jobs"
                    )

            except asyncio.CancelledError:
                logger.info(f"Worker {self.worker_id} cancelled")
                break
            except Exception as e:
                logger.exception(f"Worker {self.worker_id} error: {e}")
                # Brief pause on error before retrying
                await asyncio.sleep(1)

        logger.info(f"Worker {self.worker_id} stopped")

    def stop(self) -> None:
        """Signal the worker to stop gracefully."""
        self._running = False
        self._shutdown_event.set()

    async def process_batch(self, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
        """Process a batch of pending embedding jobs.

        Uses SKIP LOCKED to safely claim jobs without conflicts.

        Args:
            batch_size: Maximum jobs to process

        Returns:
            Number of jobs processed
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                # Claim pending jobs with SKIP LOCKED
                rows = await conn.fetch(
                    """
                    SELECT id, tenant_id, source_type, source_id, content,
                           status, retry_count, last_error, created_at, updated_at
                    FROM agent_embedding_jobs
                    WHERE status = 'pending'
                      AND (retry_count < $1 OR retry_count IS NULL)
                    ORDER BY created_at ASC
                    LIMIT $2
                    FOR UPDATE SKIP LOCKED
                    """,
                    self.MAX_RETRIES,
                    batch_size,
                )

                if not rows:
                    return 0

                # Mark as processing
                job_ids = [row["id"] for row in rows]
                await conn.execute(
                    """
                    UPDATE agent_embedding_jobs
                    SET status = 'processing', updated_at = NOW()
                    WHERE id = ANY($1)
                    """,
                    job_ids,
                )

        # Process jobs outside transaction for better isolation
        jobs = [
            EmbeddingJob(
                id=row["id"],
                tenant_id=row["tenant_id"],
                source_type=SourceType(row["source_type"]),
                source_id=row["source_id"],
                content=row["content"],
                status=JobStatus(row["status"]),
                retry_count=row["retry_count"] or 0,
                last_error=row["last_error"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

        # Generate embeddings in batch
        texts = [job.content for job in jobs]
        try:
            embeddings = await self.embedding_provider.embed_batch(texts)
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            # Mark all as failed and return
            await self._mark_jobs_failed(jobs, str(e))
            return len(jobs)

        # Update source records and mark jobs complete
        for job, (embedding, model, dimension) in zip(jobs, embeddings):
            try:
                await self._update_source_embedding(
                    job, embedding, model, dimension
                )
                await self._mark_job_completed(job)
            except Exception as e:
                logger.error(f"Failed to update job {job.id}: {e}")
                await self._mark_job_failed(job, str(e))

        return len(jobs)

    async def _update_source_embedding(
        self,
        job: EmbeddingJob,
        embedding: list[float],
        model: str,
        dimension: int,
    ) -> None:
        """Update the source record with its embedding.

        Args:
            job: The embedding job
            embedding: Generated embedding vector
            model: Model used for embedding
            dimension: Embedding dimension
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                # Set tenant context for RLS
                await conn.execute(
                    "SET LOCAL app.tenant_id = $1",
                    job.tenant_id,
                )

                if job.source_type == SourceType.MESSAGE:
                    # Update agent_messages table
                    await conn.execute(
                        """
                        UPDATE agent_messages
                        SET embedding = $1,
                            embedding_model = $2,
                            embedding_dimension = $3
                        WHERE id = $4
                        """,
                        embedding,
                        model,
                        dimension,
                        job.source_id,
                    )
                elif job.source_type == SourceType.MEMORY:
                    # Update agent_memory table
                    await conn.execute(
                        """
                        UPDATE agent_memory
                        SET embedding = $1,
                            embedding_model = $2,
                            embedding_dimension = $3,
                            updated_at = NOW()
                        WHERE id = $4
                        """,
                        embedding,
                        model,
                        dimension,
                        job.source_id,
                    )

    async def _mark_job_completed(self, job: EmbeddingJob) -> None:
        """Mark a job as completed."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_embedding_jobs
                SET status = 'completed', updated_at = NOW()
                WHERE id = $1
                """,
                job.id,
            )

    async def _mark_job_failed(self, job: EmbeddingJob, error: str) -> None:
        """Mark a job as failed with retry logic.

        Jobs exceeding MAX_RETRIES are moved to dead letter queue.

        Args:
            job: The failed job
            error: Error message
        """
        new_retry_count = job.retry_count + 1

        if new_retry_count >= self.MAX_RETRIES:
            # Move to dead letter queue
            status = JobStatus.DEAD.value
            logger.warning(
                f"Job {job.id} moved to dead letter queue after "
                f"{new_retry_count} retries: {error}"
            )
        else:
            # Schedule for retry
            status = JobStatus.PENDING.value
            logger.info(
                f"Job {job.id} scheduled for retry "
                f"({new_retry_count}/{self.MAX_RETRIES}): {error}"
            )

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_embedding_jobs
                SET status = $1,
                    retry_count = $2,
                    last_error = $3,
                    updated_at = NOW()
                WHERE id = $4
                """,
                status,
                new_retry_count,
                error[:500],  # Truncate error message
                job.id,
            )

    async def _mark_jobs_failed(
        self, jobs: list[EmbeddingJob], error: str
    ) -> None:
        """Mark multiple jobs as failed."""
        for job in jobs:
            await self._mark_job_failed(job, error)

    async def get_stats(self) -> dict[str, Any]:
        """Get worker statistics.

        Returns:
            Dict with job counts by status
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, COUNT(*) as count
                FROM agent_embedding_jobs
                GROUP BY status
                """
            )

            stats = {
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "dead": 0,
            }

            for row in rows:
                stats[row["status"]] = row["count"]

            # Get additional metrics
            oldest_pending = await conn.fetchval(
                """
                SELECT created_at
                FROM agent_embedding_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
            )

            if oldest_pending:
                stats["oldest_pending_age_seconds"] = (
                    datetime.now(oldest_pending.tzinfo) - oldest_pending
                ).total_seconds()

            return stats

    async def retry_dead_jobs(self, max_jobs: int = 100) -> int:
        """Retry jobs from the dead letter queue.

        Resets retry count and status to pending.

        Args:
            max_jobs: Maximum jobs to retry

        Returns:
            Number of jobs retried
        """
        async with self.db.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE agent_embedding_jobs
                SET status = 'pending',
                    retry_count = 0,
                    updated_at = NOW()
                WHERE id IN (
                    SELECT id FROM agent_embedding_jobs
                    WHERE status = 'dead'
                    ORDER BY created_at ASC
                    LIMIT $1
                )
                """,
                max_jobs,
            )

            # Extract count from result like "UPDATE 5"
            count = int(result.split()[-1]) if result else 0

            if count > 0:
                logger.info(f"Retried {count} dead letter jobs")

            return count

    async def cleanup_old_completed(self, days: int = 7) -> int:
        """Clean up old completed jobs.

        Args:
            days: Age threshold for deletion

        Returns:
            Number of jobs deleted
        """
        async with self.db.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM agent_embedding_jobs
                WHERE status = 'completed'
                  AND updated_at < NOW() - $1::interval
                """,
                f"{days} days",
            )

            count = int(result.split()[-1]) if result else 0

            if count > 0:
                logger.info(f"Cleaned up {count} old completed jobs")

            return count


class EmbeddingWorkerPool:
    """Pool of embedding workers for parallel processing.

    Manages multiple worker instances for higher throughput.

    Usage:
        pool = EmbeddingWorkerPool(db_pool, embedding_provider, num_workers=4)
        await pool.start()
        # ... later
        await pool.stop()
    """

    def __init__(
        self,
        db_pool: IAsyncDBPool,
        embedding_provider: IEmbeddingProvider,
        num_workers: int = 2,
    ):
        """Initialize the worker pool.

        Args:
            db_pool: Database connection pool
            embedding_provider: Embedding provider
            num_workers: Number of concurrent workers
        """
        self.db_pool = db_pool
        self.embedding_provider = embedding_provider
        self.num_workers = num_workers
        self.workers: list[EmbeddingWorker] = []
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all workers in the pool."""
        for i in range(self.num_workers):
            worker = EmbeddingWorker(
                self.db_pool,
                self.embedding_provider,
                worker_id=f"pool-worker-{i}",
            )
            self.workers.append(worker)
            task = asyncio.create_task(worker.start())
            self._tasks.append(task)

        logger.info(f"Started embedding worker pool with {self.num_workers} workers")

    async def stop(self) -> None:
        """Stop all workers gracefully."""
        for worker in self.workers:
            worker.stop()

        # Wait for all workers to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self.workers.clear()
        self._tasks.clear()

        logger.info("Embedding worker pool stopped")

    async def get_stats(self) -> dict[str, Any]:
        """Get aggregated stats from all workers."""
        if not self.workers:
            return {}

        # Use first worker's stats (they share the same DB)
        return await self.workers[0].get_stats()
