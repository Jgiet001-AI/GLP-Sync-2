#!/usr/bin/env python3
"""Database Utilities for HPE GreenLake Sync.

This module provides database utilities including:
    - Transaction context managers with automatic commit/rollback
    - Connection pool management
    - Error handling and retry for database operations

Example:
    async with database_transaction(pool) as conn:
        await conn.execute("INSERT INTO ...")
        await conn.execute("UPDATE ...")
        # Automatic commit on success, rollback on exception

Author: HPE GreenLake Team
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from .exceptions import (
    ConnectionPoolError,
    DatabaseError,
    IntegrityError,
    TransactionError,
)

logger = logging.getLogger(__name__)


# ============================================
# Transaction Context Managers
# ============================================

@asynccontextmanager
async def database_transaction(
    pool,
    isolation: str = "read_committed",
    readonly: bool = False,
    deferrable: bool = False,
) -> AsyncIterator[Any]:
    """Context manager for database transactions with automatic commit/rollback.

    Acquires a connection from the pool, starts a transaction, and ensures
    proper commit on success or rollback on exception.

    Args:
        pool: asyncpg connection pool
        isolation: Transaction isolation level
            ("serializable", "repeatable_read", "read_committed")
        readonly: If True, transaction is read-only
        deferrable: If True, transaction is deferrable (only with serializable)

    Yields:
        Database connection within transaction

    Raises:
        ConnectionPoolError: If connection cannot be acquired
        TransactionError: If transaction fails
        IntegrityError: If integrity constraint violated

    Example:
        async with database_transaction(pool) as conn:
            await conn.execute("INSERT INTO devices ...")
            await conn.execute("UPDATE sync_history ...")
            # Commits automatically on exit
    """
    if pool is None:
        raise ConnectionPoolError("Database connection pool is not initialized")

    conn = None
    try:
        # Acquire connection with timeout
        try:
            conn = await asyncio.wait_for(
                pool.acquire(),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            raise ConnectionPoolError(
                "Timeout acquiring database connection",
                details={"timeout_seconds": 30},
            )
        except Exception as e:
            raise ConnectionPoolError(
                f"Failed to acquire database connection: {e}",
                cause=e,
            )

        # Start transaction
        transaction = conn.transaction(
            isolation=isolation,
            readonly=readonly,
            deferrable=deferrable,
        )

        try:
            await transaction.start()
        except Exception as e:
            raise TransactionError(
                f"Failed to start transaction: {e}",
                cause=e,
            )

        try:
            yield conn
            # Commit on successful exit
            await transaction.commit()
            logger.debug("Transaction committed successfully")

        except Exception as e:
            # Rollback on any exception
            try:
                await transaction.rollback()
                logger.debug("Transaction rolled back due to exception")
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")

            # Re-raise with appropriate exception type
            raise _convert_db_exception(e)

    finally:
        if conn:
            await pool.release(conn)


@asynccontextmanager
async def database_connection(pool) -> AsyncIterator[Any]:
    """Simple context manager for database connection without transaction.

    Use this for read-only operations or when you need manual transaction control.

    Args:
        pool: asyncpg connection pool

    Yields:
        Database connection

    Example:
        async with database_connection(pool) as conn:
            result = await conn.fetch("SELECT * FROM devices LIMIT 10")
    """
    if pool is None:
        raise ConnectionPoolError("Database connection pool is not initialized")

    conn = None
    try:
        conn = await asyncio.wait_for(pool.acquire(), timeout=30.0)
        yield conn
    except asyncio.TimeoutError:
        raise ConnectionPoolError(
            "Timeout acquiring database connection",
            details={"timeout_seconds": 30},
        )
    finally:
        if conn:
            await pool.release(conn)


# ============================================
# Batch Operations
# ============================================

@asynccontextmanager
async def batch_transaction(
    pool,
    batch_size: int = 100,
) -> AsyncIterator["BatchExecutor"]:
    """Context manager for batch database operations.

    Collects operations and executes them in batches for better performance.

    Args:
        pool: asyncpg connection pool
        batch_size: Number of operations per batch

    Yields:
        BatchExecutor instance

    Example:
        async with batch_transaction(pool, batch_size=100) as batch:
            for device in devices:
                await batch.add("INSERT INTO devices ...", device.id, device.name)
            # Executes remaining operations on exit
    """
    async with database_transaction(pool) as conn:
        executor = BatchExecutor(conn, batch_size)
        try:
            yield executor
            # Flush remaining operations
            await executor.flush()
        except Exception:
            # Don't try to flush on error
            raise


class BatchExecutor:
    """Executes database operations in batches.

    Collects operations and executes them when batch size is reached.
    """

    def __init__(self, conn, batch_size: int = 100):
        self.conn = conn
        self.batch_size = batch_size
        self._operations: list[tuple[str, tuple]] = []
        self._executed_count = 0

    async def add(self, query: str, *args):
        """Add an operation to the batch.

        Args:
            query: SQL query string
            *args: Query parameters
        """
        self._operations.append((query, args))

        if len(self._operations) >= self.batch_size:
            await self.flush()

    async def flush(self):
        """Execute all pending operations."""
        if not self._operations:
            return

        for query, args in self._operations:
            await self.conn.execute(query, *args)

        self._executed_count += len(self._operations)
        logger.debug(f"Batch executed {len(self._operations)} operations")
        self._operations.clear()

    @property
    def executed_count(self) -> int:
        """Get total number of executed operations."""
        return self._executed_count


# ============================================
# Error Conversion
# ============================================

def _convert_db_exception(e: Exception) -> DatabaseError:
    """Convert database exception to appropriate GLPError subtype."""
    error_str = str(e).lower()

    # Check for specific error types
    if "unique" in error_str or "duplicate" in error_str:
        return IntegrityError(
            f"Duplicate entry: {e}",
            constraint="unique",
            cause=e,
        )

    if "foreign key" in error_str or "violates foreign key" in error_str:
        return IntegrityError(
            f"Foreign key violation: {e}",
            constraint="foreign_key",
            cause=e,
        )

    if "not null" in error_str:
        return IntegrityError(
            f"Not null violation: {e}",
            constraint="not_null",
            cause=e,
        )

    if "deadlock" in error_str:
        return TransactionError(
            f"Deadlock detected: {e}",
            operation="transaction",
            cause=e,
        )

    if "timeout" in error_str or "timed out" in error_str:
        return TransactionError(
            f"Database operation timed out: {e}",
            operation="query",
            cause=e,
        )

    # If it's already a DatabaseError, return as-is
    if isinstance(e, DatabaseError):
        return e

    # Generic database error
    return DatabaseError(
        f"Database operation failed: {e}",
        cause=e,
    )


# ============================================
# Connection Pool Helpers
# ============================================

async def create_pool(
    database_url: str,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: float = 60.0,
    **kwargs,
):
    """Create a database connection pool with error handling.

    Args:
        database_url: PostgreSQL connection string
        min_size: Minimum pool connections
        max_size: Maximum pool connections
        command_timeout: Default query timeout in seconds
        **kwargs: Additional asyncpg.create_pool arguments

    Returns:
        asyncpg.Pool instance

    Raises:
        ConnectionPoolError: If pool creation fails
    """
    try:
        import asyncpg

        pool = await asyncpg.create_pool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
            **kwargs,
        )
        logger.info(
            f"Database pool created (min={min_size}, max={max_size})"
        )
        return pool

    except ImportError:
        raise ConnectionPoolError(
            "asyncpg is not installed. Run: pip install asyncpg"
        )
    except Exception as e:
        raise ConnectionPoolError(
            f"Failed to create database pool: {e}",
            cause=e,
        )


async def close_pool(pool, timeout: float = 10.0):
    """Close database pool gracefully.

    Args:
        pool: asyncpg pool to close
        timeout: Maximum time to wait for connections to close
    """
    if pool is None:
        return

    try:
        await asyncio.wait_for(pool.close(), timeout=timeout)
        logger.info("Database pool closed")
    except asyncio.TimeoutError:
        logger.warning(f"Pool close timed out after {timeout}s, terminating")
        pool.terminate()
    except Exception as e:
        logger.error(f"Error closing pool: {e}")
        pool.terminate()


# ============================================
# Health Check
# ============================================

async def check_database_health(pool) -> dict[str, Any]:
    """Check database connection health.

    Args:
        pool: asyncpg connection pool

    Returns:
        Dict with health status information
    """
    if pool is None:
        return {
            "healthy": False,
            "error": "Pool not initialized",
        }

    try:
        async with database_connection(pool) as conn:
            result = await conn.fetchval("SELECT 1")
            pool_size = pool.get_size()
            pool_free = pool.get_idle_size()

            return {
                "healthy": result == 1,
                "pool_size": pool_size,
                "pool_free": pool_free,
                "pool_used": pool_size - pool_free,
            }

    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
        }


# ============================================
# Exports
# ============================================

__all__ = [
    "database_transaction",
    "database_connection",
    "batch_transaction",
    "BatchExecutor",
    "create_pool",
    "close_pool",
    "check_database_health",
]
