#!/usr/bin/env python3
"""GLP Sync Performance Benchmark Suite.

This script provides comprehensive performance profiling for the GLP sync system,
including CPU profiling, memory analysis, database query patterns, and end-to-end timing.

Usage:
    # Full benchmark (requires database and API credentials)
    python benchmark.py

    # Quick benchmark with mocked data (no external dependencies)
    python benchmark.py --mock

    # Specific profiling modes
    python benchmark.py --cpu              # CPU profiling only
    python benchmark.py --memory           # Memory profiling only
    python benchmark.py --queries          # Database query analysis
    python benchmark.py --all              # All profiling modes

    # Export results
    python benchmark.py --output report.json
    python benchmark.py --cpu-dump profile.prof  # For snakeviz visualization

Example:
    # Run with mock data and see memory usage
    python benchmark.py --mock --memory

    # Profile real sync and save CPU profile for visualization
    python benchmark.py --cpu --cpu-dump sync.prof
    # Then visualize with: snakeviz sync.prof

Requirements:
    - For real sync: GLP_CLIENT_ID, GLP_CLIENT_SECRET, DATABASE_URL env vars
    - For mock mode: No external dependencies
    - Optional: snakeviz for CPU profile visualization (pip install snakeviz)
    - Optional: memory_profiler for detailed memory (pip install memory_profiler)

Author: Performance Analysis
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("asyncpg").setLevel(logging.WARNING)

# Import profiling utilities
from src.glp.profiling import (
    AsyncProfiler,
    BenchmarkRunner,
    CPUProfiler,
    MemoryProfiler,
    QueryProfiler,
    Timer,
    async_timer,
    cpu_profile,
    memory_profile,
    print_profile_report,
    profile_async,
)


# ============================================
# Mock Data Generator
# ============================================

class MockDataGenerator:
    """Generate mock device and subscription data for benchmarking."""

    @staticmethod
    def generate_devices(count: int = 1000) -> list[dict]:
        """Generate mock device records."""
        devices = []
        for i in range(count):
            devices.append({
                "id": f"device-{i:06d}",
                "macAddress": f"AA:BB:CC:DD:{i//256:02X}:{i%256:02X}",
                "serialNumber": f"SN{i:08d}",
                "partNumber": f"PN-{i % 100:04d}",
                "deviceType": ["COMPUTE", "STORAGE", "NETWORK"][i % 3],
                "model": f"Model-{i % 50}",
                "region": ["US-WEST", "US-EAST", "EU-WEST", "APAC"][i % 4],
                "archived": False,
                "deviceName": f"Device {i}",
                "secondaryName": None,
                "assignedState": ["ASSIGNED", "UNASSIGNED", "PENDING"][i % 3],
                "type": "compute.device",
                "tenantWorkspaceId": f"workspace-{i % 10}",
                "application": {
                    "id": f"app-{i % 5}",
                    "resourceUri": f"/apps/app-{i % 5}",
                },
                "location": {
                    "id": f"loc-{i % 20}",
                    "locationName": f"Location {i % 20}",
                    "city": ["San Jose", "Austin", "Seattle", "Denver"][i % 4],
                    "state": ["CA", "TX", "WA", "CO"][i % 4],
                    "country": "USA",
                    "postalCode": f"{10000 + i % 90000}",
                    "streetAddress": f"{i} Main Street",
                    "latitude": 37.0 + (i % 10) * 0.1,
                    "longitude": -122.0 + (i % 10) * 0.1,
                    "locationSource": "MANUAL",
                },
                "dedicatedPlatformWorkspace": {"id": f"dpw-{i % 3}"},
                "subscription": [
                    {"id": f"sub-{i * 2}", "resourceUri": f"/subs/sub-{i * 2}"},
                    {"id": f"sub-{i * 2 + 1}", "resourceUri": f"/subs/sub-{i * 2 + 1}"},
                ],
                "tags": {
                    "environment": ["prod", "dev", "staging"][i % 3],
                    "owner": f"team-{i % 10}",
                },
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-06-15T12:00:00Z",
            })
        return devices

    @staticmethod
    def generate_subscriptions(count: int = 500) -> list[dict]:
        """Generate mock subscription records."""
        subscriptions = []
        for i in range(count):
            subscriptions.append({
                "key": f"SUB-{i:06d}",
                "id": f"subscription-{i:06d}",
                "subscriptionType": ["HARDWARE", "SOFTWARE", "SUPPORT"][i % 3],
                "subscriptionStatus": ["ACTIVE", "EXPIRED", "PENDING"][i % 3],
                "productDescription": f"Product {i % 100}",
                "startTime": "2024-01-01T00:00:00Z",
                "endTime": "2025-12-31T23:59:59Z",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-06-15T12:00:00Z",
            })
        return subscriptions


# ============================================
# Benchmark Functions
# ============================================

async def benchmark_api_fetch(client, syncer_class, endpoint_name: str) -> dict:
    """Benchmark API fetch operations."""
    async with AsyncProfiler(f"api_fetch_{endpoint_name}", memory=True) as profiler:
        syncer = syncer_class(client=client)
        if endpoint_name == "devices":
            data = await syncer.fetch_all_devices()
        else:
            data = await syncer.fetch_all_subscriptions()

    report = profiler.get_report()
    return {
        "operation": f"fetch_{endpoint_name}",
        "count": len(data),
        "duration_ms": report.total_duration_ms,
        "memory_peak_mb": report.memory_peak_mb,
        "items_per_second": len(data) / (report.total_duration_ms / 1000) if report.total_duration_ms > 0 else 0,
    }


async def benchmark_db_sync(syncer, data: list, name: str) -> dict:
    """Benchmark database sync operations."""
    async with AsyncProfiler(f"db_sync_{name}", memory=True) as profiler:
        try:
            stats = await syncer.sync_to_postgres(data)
        except Exception as e:
            logger.warning(f"Sync completed with errors: {e}")
            stats = {"error": str(e)}

    report = profiler.get_report()
    return {
        "operation": f"sync_{name}",
        "count": len(data),
        "duration_ms": report.total_duration_ms,
        "memory_peak_mb": report.memory_peak_mb,
        "items_per_second": len(data) / (report.total_duration_ms / 1000) if report.total_duration_ms > 0 else 0,
        "stats": stats,
    }


async def benchmark_mock_db_operations(device_count: int = 1000) -> dict:
    """Benchmark simulated database operations (no real DB needed)."""
    devices = MockDataGenerator.generate_devices(device_count)

    results = {
        "device_count": device_count,
        "operations": [],
    }

    # Benchmark: JSON serialization (simulates raw_data JSONB insert)
    with memory_profile("json_serialization") as mp:
        timer = Timer("json_serialize")
        timer.start()
        serialized = [json.dumps(d) for d in devices]
        timer.stop()

    mem_stats = mp.get_stats()
    results["operations"].append({
        "operation": "json_serialize",
        "count": len(devices),
        "duration_ms": timer.duration_ms,
        "memory_peak_mb": mem_stats["peak_mb"],
        "items_per_second": len(devices) / (timer.duration_ms / 1000),
    })

    # Benchmark: Field extraction (simulates INSERT parameter prep)
    timer = Timer("field_extraction")
    timer.start()
    for device in devices:
        _ = (
            device["id"],
            device.get("macAddress"),
            device.get("serialNumber"),
            device.get("deviceType"),
            (device.get("application") or {}).get("id"),
            (device.get("location") or {}).get("id"),
        )
    timer.stop()

    results["operations"].append({
        "operation": "field_extraction",
        "count": len(devices),
        "duration_ms": timer.duration_ms,
        "items_per_second": len(devices) / (timer.duration_ms / 1000),
    })

    # Benchmark: Existence check simulation (dict lookup vs list search)
    existing_ids = {d["id"] for d in devices[:device_count // 2]}

    timer = Timer("existence_check_dict")
    timer.start()
    for device in devices:
        _ = device["id"] in existing_ids
    timer.stop()

    results["operations"].append({
        "operation": "existence_check_dict",
        "count": len(devices),
        "duration_ms": timer.duration_ms,
        "items_per_second": len(devices) / (timer.duration_ms / 1000),
    })

    # Benchmark: List comprehension for subscriptions
    timer = Timer("subscription_extract")
    timer.start()
    for device in devices:
        subs = device.get("subscription") or []
        sub_ids = [(s.get("id"), s.get("resourceUri")) for s in subs if s.get("id")]
    timer.stop()

    results["operations"].append({
        "operation": "subscription_extract",
        "count": len(devices),
        "duration_ms": timer.duration_ms,
        "items_per_second": len(devices) / (timer.duration_ms / 1000),
    })

    # Benchmark: Tag extraction
    timer = Timer("tag_extract")
    timer.start()
    for device in devices:
        tags = device.get("tags") or {}
        tag_pairs = [(k, v) for k, v in tags.items()]
    timer.stop()

    results["operations"].append({
        "operation": "tag_extract",
        "count": len(devices),
        "duration_ms": timer.duration_ms,
        "items_per_second": len(devices) / (timer.duration_ms / 1000),
    })

    return results


async def benchmark_memory_scaling(sizes: list[int] = None) -> dict:
    """Benchmark memory usage at different dataset sizes."""
    if sizes is None:
        sizes = [100, 500, 1000, 2000, 5000, 10000]

    results = []

    for size in sizes:
        with memory_profile(f"devices_{size}") as mp:
            devices = MockDataGenerator.generate_devices(size)
            # Force memory allocation
            serialized = json.dumps(devices)

        mem_stats = mp.get_stats()
        results.append({
            "device_count": size,
            "memory_peak_mb": mem_stats["peak_mb"],
            "mb_per_1000_devices": mem_stats["peak_mb"] / (size / 1000),
        })

        logger.info(f"Size {size}: {mem_stats['peak_mb']:.2f}MB")

    return {"memory_scaling": results}


async def profile_cpu_detailed(device_count: int = 1000, save_path: Optional[str] = None) -> dict:
    """Detailed CPU profiling of data processing."""
    devices = MockDataGenerator.generate_devices(device_count)

    with cpu_profile("detailed_processing") as profiler:
        # Simulate full processing pipeline
        for device in devices:
            # Parse timestamps
            created = device.get("createdAt", "").replace("Z", "+00:00") if device.get("createdAt") else None
            updated = device.get("updatedAt", "").replace("Z", "+00:00") if device.get("updatedAt") else None

            # Extract nested objects
            application = device.get("application") or {}
            location = device.get("location") or {}
            dedicated = device.get("dedicatedPlatformWorkspace") or {}

            # Build insert tuple
            values = (
                device["id"],
                device.get("macAddress"),
                device.get("serialNumber"),
                device.get("partNumber"),
                device.get("deviceType"),
                device.get("model"),
                device.get("region"),
                device.get("archived", False),
                device.get("deviceName"),
                application.get("id"),
                application.get("resourceUri"),
                dedicated.get("id"),
                location.get("id"),
                location.get("locationName"),
                json.dumps(device),
            )

            # Extract subscriptions
            subs = device.get("subscription") or []
            sub_tuples = [(device["id"], s.get("id"), s.get("resourceUri")) for s in subs]

            # Extract tags
            tags = device.get("tags") or {}
            tag_tuples = [(device["id"], k, v) for k, v in tags.items()]

    if save_path:
        profiler.save(save_path)
        logger.info(f"CPU profile saved to {save_path}")
        logger.info(f"Visualize with: snakeviz {save_path}")

    return {
        "device_count": device_count,
        "top_functions": profiler.get_top_functions(10),
        "profile_path": save_path,
    }


async def run_query_analysis(db_pool) -> dict:
    """Analyze database query patterns."""
    if not db_pool:
        return {"error": "No database connection available"}

    profiler = QueryProfiler(db_pool)

    # Simulate the N+1 pattern from sync_to_postgres
    devices = MockDataGenerator.generate_devices(100)

    for device in devices:
        # Existence check (N queries)
        await profiler.fetchval(
            "SELECT 1 FROM devices WHERE id = $1",
            [device["id"]],
        )

    report = profiler.report()
    n_plus_one = profiler.detect_n_plus_one(threshold=5)

    return {
        "query_report": report,
        "n_plus_one_detected": n_plus_one,
    }


# ============================================
# Main Benchmark Runner
# ============================================

async def run_benchmarks(args: argparse.Namespace) -> dict:
    """Run all benchmarks and collect results."""
    start_time = datetime.utcnow()
    results = {
        "timestamp": start_time.isoformat(),
        "mode": "mock" if args.mock else "live",
        "benchmarks": [],
    }

    logger.info("=" * 60)
    logger.info("GLP SYNC PERFORMANCE BENCHMARK")
    logger.info("=" * 60)

    # 1. Mock data benchmarks (always run)
    if args.mock or not (args.cpu or args.memory or args.queries):
        logger.info("\n--- Mock Data Operations Benchmark ---")
        mock_results = await benchmark_mock_db_operations(
            device_count=args.device_count
        )
        results["benchmarks"].append({
            "name": "mock_operations",
            "results": mock_results,
        })

        for op in mock_results["operations"]:
            logger.info(
                f"  {op['operation']}: {op['duration_ms']:.2f}ms "
                f"({op['items_per_second']:.0f} items/sec)"
            )

    # 2. Memory scaling benchmark
    if args.memory or args.all:
        logger.info("\n--- Memory Scaling Benchmark ---")
        mem_results = await benchmark_memory_scaling()
        results["benchmarks"].append({
            "name": "memory_scaling",
            "results": mem_results,
        })

    # 3. CPU profiling
    if args.cpu or args.all:
        logger.info("\n--- CPU Profiling ---")
        cpu_results = await profile_cpu_detailed(
            device_count=args.device_count,
            save_path=args.cpu_dump,
        )
        results["benchmarks"].append({
            "name": "cpu_profile",
            "results": cpu_results,
        })

        logger.info("Top CPU consumers:")
        for func in cpu_results["top_functions"][:5]:
            logger.info(
                f"  {func['function']}: {func['cumulative_time_ms']:.2f}ms "
                f"({func['calls']} calls)"
            )

    # 4. Live API + DB benchmarks (requires credentials)
    if not args.mock and (args.live or args.all):
        logger.info("\n--- Live API/DB Benchmark ---")

        try:
            from src.glp.api import DeviceSyncer, GLPClient, SubscriptionSyncer, TokenManager
            import asyncpg

            token_manager = TokenManager()
            db_url = os.getenv("DATABASE_URL")

            if db_url:
                db_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
            else:
                db_pool = None
                logger.warning("No DATABASE_URL, skipping DB benchmarks")

            async with GLPClient(token_manager) as client:
                # Benchmark device fetch
                logger.info("Fetching devices...")
                device_bench = await benchmark_api_fetch(
                    client, DeviceSyncer, "devices"
                )
                results["benchmarks"].append({
                    "name": "api_fetch_devices",
                    "results": device_bench,
                })
                logger.info(
                    f"  Devices: {device_bench['count']} in "
                    f"{device_bench['duration_ms']:.0f}ms "
                    f"({device_bench['items_per_second']:.0f}/sec)"
                )

                # Benchmark subscription fetch
                logger.info("Fetching subscriptions...")
                sub_bench = await benchmark_api_fetch(
                    client, SubscriptionSyncer, "subscriptions"
                )
                results["benchmarks"].append({
                    "name": "api_fetch_subscriptions",
                    "results": sub_bench,
                })
                logger.info(
                    f"  Subscriptions: {sub_bench['count']} in "
                    f"{sub_bench['duration_ms']:.0f}ms "
                    f"({sub_bench['items_per_second']:.0f}/sec)"
                )

            if db_pool:
                await db_pool.close()

        except ValueError as e:
            logger.warning(f"Skipping live benchmarks: {e}")
        except Exception as e:
            logger.error(f"Live benchmark error: {e}")

    # 5. Query pattern analysis
    if args.queries or args.all:
        logger.info("\n--- Query Pattern Analysis ---")

        if args.mock:
            # Simulate query patterns without real DB
            logger.info("  Analyzing typical query patterns...")

            # Estimate N+1 impact
            n_devices = args.device_count
            queries_per_device = 4  # SELECT exists, INSERT/UPDATE, DELETE subs, DELETE tags
            inserts_per_device = 3  # main + avg 2 subs + avg 2 tags = ~5 but grouped

            total_queries = n_devices * queries_per_device
            estimated_overhead_ms = total_queries * 0.5  # ~0.5ms per query

            results["benchmarks"].append({
                "name": "query_analysis",
                "results": {
                    "estimated_queries": total_queries,
                    "estimated_overhead_ms": estimated_overhead_ms,
                    "n_plus_one_patterns": [
                        {"query": "SELECT 1 FROM devices WHERE id = ?", "count": n_devices},
                        {"query": "DELETE FROM device_subscriptions WHERE device_id = ?", "count": n_devices},
                        {"query": "DELETE FROM device_tags WHERE device_id = ?", "count": n_devices},
                    ],
                    "optimization_suggestions": [
                        "Use UPSERT (INSERT ON CONFLICT) instead of SELECT + INSERT/UPDATE",
                        "Batch DELETE operations with IN clause",
                        "Use executemany() for bulk inserts",
                        "Consider batch transaction scope (100 devices per transaction)",
                    ],
                },
            })

            logger.info(f"  Estimated {total_queries} queries for {n_devices} devices")
            logger.info(f"  Estimated overhead: {estimated_overhead_ms:.0f}ms")

    # Summary
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    results["total_duration_seconds"] = duration

    logger.info("\n" + "=" * 60)
    logger.info("BENCHMARK COMPLETE")
    logger.info(f"Total time: {duration:.1f} seconds")
    logger.info("=" * 60)

    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Results saved to {args.output}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="GLP Sync Performance Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmark.py --mock              # Quick benchmark with mock data
  python benchmark.py --memory            # Memory scaling analysis
  python benchmark.py --cpu               # CPU profiling
  python benchmark.py --cpu-dump sync.prof  # Save CPU profile for snakeviz
  python benchmark.py --all               # All profiling modes
  python benchmark.py --output report.json  # Save results to JSON
        """
    )

    # Mode selection
    mode_group = parser.add_argument_group("Profiling Modes")
    mode_group.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data (no API/DB required)"
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Run live API/DB benchmarks (requires credentials)"
    )
    mode_group.add_argument(
        "--cpu",
        action="store_true",
        help="Enable CPU profiling"
    )
    mode_group.add_argument(
        "--memory",
        action="store_true",
        help="Enable memory profiling"
    )
    mode_group.add_argument(
        "--queries",
        action="store_true",
        help="Enable query pattern analysis"
    )
    mode_group.add_argument(
        "--all",
        action="store_true",
        help="Enable all profiling modes"
    )

    # Configuration
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "--device-count",
        type=int,
        default=1000,
        help="Number of mock devices to generate (default: 1000)"
    )

    # Output
    output_group = parser.add_argument_group("Output")
    output_group.add_argument(
        "--output",
        type=str,
        metavar="FILE",
        help="Save results to JSON file"
    )
    output_group.add_argument(
        "--cpu-dump",
        type=str,
        metavar="FILE",
        help="Save CPU profile to file (use with snakeviz)"
    )

    args = parser.parse_args()

    # Default to mock mode if no flags specified
    if not any([args.mock, args.live, args.cpu, args.memory, args.queries, args.all]):
        args.mock = True

    # Run benchmarks
    asyncio.run(run_benchmarks(args))


if __name__ == "__main__":
    main()
