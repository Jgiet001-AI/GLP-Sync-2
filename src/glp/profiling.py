#!/usr/bin/env python3
"""Performance Profiling Utilities for GLP Sync.

This module provides comprehensive profiling tools for CPU, memory, database,
and end-to-end performance analysis. All profilers are designed for async code.

Usage:
    # 1. Use decorators for function-level profiling
    @profile_async
    async def my_function():
        ...

    # 2. Use context managers for block profiling
    async with AsyncProfiler("db_operation") as p:
        await db_query()
    print(p.stats())

    # 3. Use QueryProfiler for database analysis
    profiler = QueryProfiler(db_pool)
    await profiler.execute("SELECT * FROM devices", [])
    print(profiler.report())

Author: Performance Analysis
"""
import asyncio
import cProfile
import functools
import io
import logging
import pstats
import sys
import time
import tracemalloc
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ============================================
# Data Classes for Statistics
# ============================================

@dataclass
class TimingStats:
    """Statistics for a single timed operation."""
    name: str
    start_time: float
    end_time: float = 0.0
    duration_ms: float = 0.0
    memory_before: int = 0
    memory_after: int = 0
    memory_delta: int = 0

    def complete(self):
        """Mark timing as complete."""
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000


@dataclass
class QueryStats:
    """Statistics for a database query."""
    query: str
    params_count: int
    duration_ms: float
    rows_affected: int = 0
    error: Optional[str] = None


@dataclass
class ProfileReport:
    """Comprehensive profile report."""
    name: str
    total_duration_ms: float
    operations: list[TimingStats] = field(default_factory=list)
    queries: list[QueryStats] = field(default_factory=list)
    memory_peak_mb: float = 0.0
    memory_delta_mb: float = 0.0
    cpu_profile: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def summary(self) -> dict:
        """Return summary statistics."""
        query_times = [q.duration_ms for q in self.queries]
        return {
            "name": self.name,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "operations_count": len(self.operations),
            "queries_count": len(self.queries),
            "queries_total_ms": round(sum(query_times), 2) if query_times else 0,
            "queries_avg_ms": round(sum(query_times) / len(query_times), 2) if query_times else 0,
            "memory_peak_mb": round(self.memory_peak_mb, 2),
            "memory_delta_mb": round(self.memory_delta_mb, 2),
        }


# ============================================
# Timing Utilities
# ============================================

class Timer:
    """Simple high-precision timer."""

    def __init__(self, name: str = "operation"):
        self.name = name
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: float = 0

    def start(self):
        """Start the timer."""
        self.start_time = time.perf_counter()

    def stop(self) -> float:
        """Stop the timer and return duration in milliseconds."""
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        return self.duration_ms

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def __repr__(self):
        return f"Timer({self.name}: {self.duration_ms:.2f}ms)"


@asynccontextmanager
async def async_timer(name: str = "operation"):
    """Async context manager for timing operations.

    Usage:
        async with async_timer("fetch_devices") as t:
            devices = await fetch_all()
        print(f"Took {t.duration_ms:.2f}ms")
    """
    timer = Timer(name)
    timer.start()
    try:
        yield timer
    finally:
        timer.stop()
        logger.debug(f"[Timer] {name}: {timer.duration_ms:.2f}ms")


# ============================================
# CPU Profiling
# ============================================

class CPUProfiler:
    """CPU profiler using cProfile.

    Collects function call statistics including:
    - Total time per function
    - Number of calls
    - Cumulative time
    - Callers/callees
    """

    def __init__(self):
        self.profiler = cProfile.Profile()
        self.stats: Optional[pstats.Stats] = None

    def start(self):
        """Start profiling."""
        self.profiler.enable()

    def stop(self):
        """Stop profiling and generate stats."""
        self.profiler.disable()
        stream = io.StringIO()
        self.stats = pstats.Stats(self.profiler, stream=stream)

    def get_stats_string(self, sort_by: str = "cumulative", limit: int = 20) -> str:
        """Get formatted statistics string."""
        if not self.stats:
            return "No profile data collected"

        stream = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=stream)
        stats.sort_stats(sort_by)
        stats.print_stats(limit)
        return stream.getvalue()

    def get_top_functions(self, limit: int = 10) -> list[dict]:
        """Get top functions by cumulative time."""
        if not self.stats:
            return []

        results = []
        for (filename, lineno, func_name), (cc, nc, tt, ct, callers) in list(
            self.stats.stats.items()
        )[:limit]:
            results.append({
                "function": f"{func_name}",
                "file": f"{filename}:{lineno}",
                "calls": nc,
                "total_time_ms": tt * 1000,
                "cumulative_time_ms": ct * 1000,
            })
        return results

    def save(self, filepath: str):
        """Save profile data to file for later analysis."""
        self.profiler.dump_stats(filepath)
        logger.info(f"CPU profile saved to {filepath}")


@contextmanager
def cpu_profile(name: str = "profile"):
    """Context manager for CPU profiling.

    Usage:
        with cpu_profile("sync_devices") as profiler:
            sync_devices()
        print(profiler.get_stats_string())
    """
    profiler = CPUProfiler()
    profiler.start()
    try:
        yield profiler
    finally:
        profiler.stop()


# ============================================
# Memory Profiling
# ============================================

class MemoryProfiler:
    """Memory profiler using tracemalloc.

    Tracks memory allocations to identify:
    - Memory leaks
    - High-allocation code paths
    - Peak memory usage
    """

    def __init__(self):
        self.snapshot_before: Optional[tracemalloc.Snapshot] = None
        self.snapshot_after: Optional[tracemalloc.Snapshot] = None
        self.peak_bytes: int = 0
        self.current_bytes: int = 0

    def start(self):
        """Start memory tracking."""
        tracemalloc.start()
        self.snapshot_before = tracemalloc.take_snapshot()

    def stop(self):
        """Stop tracking and capture final snapshot."""
        self.snapshot_after = tracemalloc.take_snapshot()
        self.current_bytes, self.peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    def get_stats(self) -> dict:
        """Get memory statistics."""
        return {
            "peak_mb": self.peak_bytes / (1024 * 1024),
            "current_mb": self.current_bytes / (1024 * 1024),
        }

    def get_top_allocations(self, limit: int = 10) -> list[dict]:
        """Get top memory allocations."""
        if not self.snapshot_after:
            return []

        top_stats = self.snapshot_after.statistics("lineno")[:limit]

        return [
            {
                "file": str(stat.traceback),
                "size_mb": stat.size / (1024 * 1024),
                "count": stat.count,
            }
            for stat in top_stats
        ]

    def get_diff(self, limit: int = 10) -> list[dict]:
        """Get memory allocation difference between start and end."""
        if not self.snapshot_before or not self.snapshot_after:
            return []

        diff_stats = self.snapshot_after.compare_to(
            self.snapshot_before, "lineno"
        )[:limit]

        return [
            {
                "file": str(stat.traceback),
                "size_diff_mb": stat.size_diff / (1024 * 1024),
                "count_diff": stat.count_diff,
            }
            for stat in diff_stats
        ]


@contextmanager
def memory_profile(name: str = "memory"):
    """Context manager for memory profiling.

    Usage:
        with memory_profile("load_devices") as profiler:
            devices = load_all_devices()
        print(f"Peak memory: {profiler.get_stats()['peak_mb']:.2f}MB")
    """
    profiler = MemoryProfiler()
    profiler.start()
    try:
        yield profiler
    finally:
        profiler.stop()


# ============================================
# Database Query Profiling
# ============================================

class QueryProfiler:
    """Database query profiler.

    Wraps database connections to collect query timing statistics.
    Useful for identifying slow queries and N+1 patterns.
    """

    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        self.queries: list[QueryStats] = []
        self.query_counts: dict[str, int] = defaultdict(int)
        self.query_times: dict[str, list[float]] = defaultdict(list)

    async def execute(
        self,
        query: str,
        params: list = None,
        conn=None,
    ) -> Any:
        """Execute query with timing."""
        params = params or []
        timer = Timer("query")

        timer.start()
        try:
            if conn:
                result = await conn.execute(query, *params)
            elif self.db_pool:
                async with self.db_pool.acquire() as conn:
                    result = await conn.execute(query, *params)
            else:
                raise ValueError("No connection or pool provided")

            timer.stop()

            stats = QueryStats(
                query=self._normalize_query(query),
                params_count=len(params),
                duration_ms=timer.duration_ms,
            )
            self.queries.append(stats)
            self._track_query(query, timer.duration_ms)

            return result

        except Exception as e:
            timer.stop()
            stats = QueryStats(
                query=self._normalize_query(query),
                params_count=len(params),
                duration_ms=timer.duration_ms,
                error=str(e),
            )
            self.queries.append(stats)
            raise

    async def fetchval(
        self,
        query: str,
        params: list = None,
        conn=None,
    ) -> Any:
        """Fetch single value with timing."""
        params = params or []
        timer = Timer("query")

        timer.start()
        try:
            if conn:
                result = await conn.fetchval(query, *params)
            elif self.db_pool:
                async with self.db_pool.acquire() as conn:
                    result = await conn.fetchval(query, *params)
            else:
                raise ValueError("No connection or pool provided")

            timer.stop()

            stats = QueryStats(
                query=self._normalize_query(query),
                params_count=len(params),
                duration_ms=timer.duration_ms,
            )
            self.queries.append(stats)
            self._track_query(query, timer.duration_ms)

            return result

        except Exception as e:
            timer.stop()
            raise

    def _normalize_query(self, query: str) -> str:
        """Normalize query for grouping (remove specific values)."""
        # Simple normalization - replace $N params
        import re
        normalized = re.sub(r'\$\d+', '?', query)
        normalized = ' '.join(normalized.split())
        return normalized[:200]  # Truncate long queries

    def _track_query(self, query: str, duration_ms: float):
        """Track query for pattern analysis."""
        normalized = self._normalize_query(query)
        self.query_counts[normalized] += 1
        self.query_times[normalized].append(duration_ms)

    def report(self) -> dict:
        """Generate query profiling report."""
        total_queries = len(self.queries)
        total_time = sum(q.duration_ms for q in self.queries)

        # Find repeated queries (potential N+1)
        repeated_queries = [
            {
                "query": query,
                "count": count,
                "total_ms": sum(self.query_times[query]),
                "avg_ms": sum(self.query_times[query]) / count,
            }
            for query, count in self.query_counts.items()
            if count > 1
        ]
        repeated_queries.sort(key=lambda x: x["count"], reverse=True)

        # Find slow queries
        slow_queries = [
            {
                "query": q.query,
                "duration_ms": q.duration_ms,
            }
            for q in sorted(self.queries, key=lambda x: x.duration_ms, reverse=True)[:10]
        ]

        return {
            "total_queries": total_queries,
            "total_time_ms": round(total_time, 2),
            "avg_query_time_ms": round(total_time / total_queries, 2) if total_queries else 0,
            "unique_query_patterns": len(self.query_counts),
            "repeated_queries": repeated_queries[:10],
            "slow_queries": slow_queries,
        }

    def detect_n_plus_one(self, threshold: int = 5) -> list[dict]:
        """Detect potential N+1 query patterns."""
        return [
            {
                "query": query,
                "count": count,
                "suggestion": "Consider using batch query or JOIN",
            }
            for query, count in self.query_counts.items()
            if count >= threshold
        ]


# ============================================
# Async Function Decorators
# ============================================

def profile_async(
    name: str = None,
    log_result: bool = True,
    include_memory: bool = False,
):
    """Decorator for profiling async functions.

    Usage:
        @profile_async("fetch_devices", include_memory=True)
        async def fetch_devices():
            ...
    """
    def decorator(func: Callable):
        nonlocal name
        if name is None:
            name = func.__name__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            memory_profiler = None

            if include_memory:
                memory_profiler = MemoryProfiler()
                memory_profiler.start()

            timer = Timer(name)
            timer.start()

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                timer.stop()

                if memory_profiler:
                    memory_profiler.stop()
                    mem_stats = memory_profiler.get_stats()

                if log_result:
                    if include_memory and memory_profiler:
                        logger.info(
                            f"[Profile] {name}: {timer.duration_ms:.2f}ms, "
                            f"peak_memory: {mem_stats['peak_mb']:.2f}MB"
                        )
                    else:
                        logger.info(f"[Profile] {name}: {timer.duration_ms:.2f}ms")

        return wrapper
    return decorator


def profile_sync(name: str = None, log_result: bool = True):
    """Decorator for profiling sync functions."""
    def decorator(func: Callable):
        nonlocal name
        if name is None:
            name = func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            timer = Timer(name)
            timer.start()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                timer.stop()
                if log_result:
                    logger.info(f"[Profile] {name}: {timer.duration_ms:.2f}ms")

        return wrapper
    return decorator


# ============================================
# Comprehensive Profiler
# ============================================

class AsyncProfiler:
    """Comprehensive async profiler combining CPU, memory, and timing.

    Usage:
        async with AsyncProfiler("full_sync") as profiler:
            await sync_all_devices()

        report = profiler.get_report()
        print(report.summary())
    """

    def __init__(
        self,
        name: str,
        cpu: bool = True,
        memory: bool = True,
        queries: bool = False,
        db_pool=None,
    ):
        self.name = name
        self.enable_cpu = cpu
        self.enable_memory = memory
        self.enable_queries = queries

        self.timer = Timer(name)
        self.cpu_profiler: Optional[CPUProfiler] = None
        self.memory_profiler: Optional[MemoryProfiler] = None
        self.query_profiler: Optional[QueryProfiler] = None

        if queries and db_pool:
            self.query_profiler = QueryProfiler(db_pool)

    async def __aenter__(self):
        if self.enable_cpu:
            self.cpu_profiler = CPUProfiler()
            self.cpu_profiler.start()

        if self.enable_memory:
            self.memory_profiler = MemoryProfiler()
            self.memory_profiler.start()

        self.timer.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.timer.stop()

        if self.cpu_profiler:
            self.cpu_profiler.stop()

        if self.memory_profiler:
            self.memory_profiler.stop()

    def get_report(self) -> ProfileReport:
        """Generate comprehensive profile report."""
        report = ProfileReport(
            name=self.name,
            total_duration_ms=self.timer.duration_ms,
        )

        if self.memory_profiler:
            mem_stats = self.memory_profiler.get_stats()
            report.memory_peak_mb = mem_stats["peak_mb"]

        if self.cpu_profiler:
            report.cpu_profile = self.cpu_profiler.get_stats_string(limit=15)

        if self.query_profiler:
            report.queries = self.query_profiler.queries

        return report


# ============================================
# Benchmark Runner
# ============================================

class BenchmarkRunner:
    """Run benchmarks with statistical analysis.

    Usage:
        runner = BenchmarkRunner()

        @runner.benchmark("fetch_devices", iterations=10)
        async def fetch_devices():
            ...

        results = await runner.run_all()
        runner.print_report()
    """

    def __init__(self):
        self.benchmarks: dict[str, dict] = {}
        self.results: dict[str, list[float]] = defaultdict(list)

    def benchmark(
        self,
        name: str,
        iterations: int = 5,
        warmup: int = 1,
    ):
        """Decorator to register a benchmark."""
        def decorator(func: Callable):
            self.benchmarks[name] = {
                "func": func,
                "iterations": iterations,
                "warmup": warmup,
            }
            return func
        return decorator

    async def run_benchmark(self, name: str) -> dict:
        """Run a single benchmark."""
        config = self.benchmarks.get(name)
        if not config:
            raise ValueError(f"Benchmark '{name}' not found")

        func = config["func"]
        iterations = config["iterations"]
        warmup = config["warmup"]

        # Warmup runs
        for _ in range(warmup):
            await func()

        # Timed runs
        times = []
        for _ in range(iterations):
            timer = Timer(name)
            timer.start()
            await func()
            timer.stop()
            times.append(timer.duration_ms)

        self.results[name] = times

        return {
            "name": name,
            "iterations": iterations,
            "min_ms": min(times),
            "max_ms": max(times),
            "avg_ms": sum(times) / len(times),
            "total_ms": sum(times),
        }

    async def run_all(self) -> list[dict]:
        """Run all registered benchmarks."""
        results = []
        for name in self.benchmarks:
            result = await self.run_benchmark(name)
            results.append(result)
        return results

    def print_report(self):
        """Print formatted benchmark report."""
        print("\n" + "=" * 70)
        print("BENCHMARK RESULTS")
        print("=" * 70)
        print(f"{'Benchmark':<30} {'Iterations':<12} {'Avg (ms)':<12} {'Min (ms)':<12} {'Max (ms)':<12}")
        print("-" * 70)

        for name, times in self.results.items():
            if times:
                avg = sum(times) / len(times)
                print(f"{name:<30} {len(times):<12} {avg:<12.2f} {min(times):<12.2f} {max(times):<12.2f}")

        print("=" * 70)


# ============================================
# Utility Functions
# ============================================

def format_bytes(bytes_val: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} TB"


def print_profile_report(report: ProfileReport):
    """Pretty-print a profile report."""
    print("\n" + "=" * 70)
    print(f"PROFILE REPORT: {report.name}")
    print("=" * 70)
    print(f"Timestamp: {report.timestamp}")
    print(f"Total Duration: {report.total_duration_ms:.2f}ms")
    print(f"Peak Memory: {report.memory_peak_mb:.2f}MB")

    if report.queries:
        print(f"\nQueries: {len(report.queries)}")
        total_query_time = sum(q.duration_ms for q in report.queries)
        print(f"Total Query Time: {total_query_time:.2f}ms")

    if report.cpu_profile:
        print("\n--- CPU PROFILE ---")
        print(report.cpu_profile)

    print("=" * 70)
