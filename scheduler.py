#!/usr/bin/env python3
"""Automated Scheduler for HPE GreenLake Sync.

This module provides a long-running scheduler that automatically syncs
devices and/or subscriptions at configurable intervals. Designed to run
as the main process in a Docker container.

Architecture:
    - Simple asyncio loop with sleep (no external dependencies)
    - Graceful shutdown on SIGTERM/SIGINT
    - Configurable via environment variables
    - Health check endpoint via optional HTTP server

Environment Variables:
    SYNC_INTERVAL_MINUTES: Minutes between sync runs (default: 60)
    SYNC_DEVICES: Enable device sync (default: true)
    SYNC_SUBSCRIPTIONS: Enable subscription sync (default: true)
    SYNC_ON_STARTUP: Run sync immediately on startup (default: true)
    HEALTH_CHECK_PORT: Port for health check endpoint (default: 8080, 0 to disable)

    Plus all the standard GLP_* and DATABASE_URL variables.

Example:
    # Run every 30 minutes, sync both
    SYNC_INTERVAL_MINUTES=30 python scheduler.py

    # Run every 6 hours, devices only
    SYNC_INTERVAL_MINUTES=360 SYNC_SUBSCRIPTIONS=false python scheduler.py

Docker Usage:
    docker run -e SYNC_INTERVAL_MINUTES=60 -e DATABASE_URL=... glp-sync

Author: HPE GreenLake Team
"""
import asyncio
import os
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Local imports
from src.glp.api import (
    DeviceSyncer,
    GLPClient,
    SubscriptionSyncer,
    TokenManager,
)

# ============================================
# Configuration
# ============================================

class SchedulerConfig:
    """Configuration loaded from environment variables."""

    def __init__(self):
        self.interval_minutes = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))
        self.sync_devices = os.getenv("SYNC_DEVICES", "true").lower() == "true"
        self.sync_subscriptions = os.getenv("SYNC_SUBSCRIPTIONS", "true").lower() == "true"
        self.sync_on_startup = os.getenv("SYNC_ON_STARTUP", "true").lower() == "true"
        self.health_check_port = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
        self.max_retries = int(os.getenv("SYNC_MAX_RETRIES", "3"))
        self.retry_delay_minutes = int(os.getenv("SYNC_RETRY_DELAY_MINUTES", "5"))

    def __repr__(self):
        return (
            f"SchedulerConfig("
            f"interval={self.interval_minutes}m, "
            f"devices={self.sync_devices}, "
            f"subscriptions={self.sync_subscriptions}, "
            f"startup={self.sync_on_startup}, "
            f"health_port={self.health_check_port})"
        )


# ============================================
# Database Connection
# ============================================

async def create_db_pool():
    """Create database connection pool.

    Returns:
        asyncpg.Pool or None if database not configured
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("[Scheduler] WARNING: DATABASE_URL not set, running in fetch-only mode")
        return None

    try:
        import asyncpg

        pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )

        print("[Scheduler] Connected to PostgreSQL")
        return pool

    except ImportError:
        print("[Scheduler] ERROR: asyncpg not installed")
        return None
    except Exception as e:
        print(f"[Scheduler] ERROR: Database connection failed: {e}")
        return None


# ============================================
# Sync Logic
# ============================================

async def run_sync(
    config: SchedulerConfig,
    token_manager: TokenManager,
    db_pool,
) -> dict:
    """Run a single sync cycle.

    Args:
        config: Scheduler configuration
        token_manager: TokenManager instance
        db_pool: Database connection pool (can be None)

    Returns:
        Dict with sync results
    """
    start_time = datetime.utcnow()
    results = {
        "started_at": start_time.isoformat(),
        "devices": None,
        "subscriptions": None,
        "success": False,
        "error": None,
    }

    try:
        async with GLPClient(token_manager) as client:
            # Sync devices
            if config.sync_devices:
                print("[Scheduler] Syncing devices...")
                syncer = DeviceSyncer(client=client, db_pool=db_pool)

                if db_pool:
                    results["devices"] = await syncer.sync()
                else:
                    devices = await syncer.fetch_all_devices()
                    results["devices"] = {"fetched": len(devices), "mode": "fetch-only"}

            # Sync subscriptions
            if config.sync_subscriptions:
                print("[Scheduler] Syncing subscriptions...")
                syncer = SubscriptionSyncer(client=client, db_pool=db_pool)

                if db_pool:
                    results["subscriptions"] = await syncer.sync()
                else:
                    subs = await syncer.fetch_all_subscriptions()
                    results["subscriptions"] = {"fetched": len(subs), "mode": "fetch-only"}

            results["success"] = True

    except Exception as e:
        results["error"] = str(e)
        print(f"[Scheduler] ERROR during sync: {e}")

    end_time = datetime.utcnow()
    results["completed_at"] = end_time.isoformat()
    results["duration_seconds"] = (end_time - start_time).total_seconds()

    return results


async def run_sync_with_retry(
    config: SchedulerConfig,
    token_manager: TokenManager,
    db_pool,
) -> dict:
    """Run sync with retry logic on failure.

    Args:
        config: Scheduler configuration
        token_manager: TokenManager instance
        db_pool: Database connection pool

    Returns:
        Dict with sync results
    """
    last_error = None

    for attempt in range(config.max_retries):
        results = await run_sync(config, token_manager, db_pool)

        if results["success"]:
            if attempt > 0:
                print(f"[Scheduler] Sync succeeded on attempt {attempt + 1}")
            return results

        last_error = results.get("error")

        if attempt < config.max_retries - 1:
            wait_minutes = config.retry_delay_minutes * (attempt + 1)
            print(f"[Scheduler] Sync failed, retrying in {wait_minutes} minutes (attempt {attempt + 1}/{config.max_retries})")
            await asyncio.sleep(wait_minutes * 60)

    print(f"[Scheduler] Sync failed after {config.max_retries} attempts: {last_error}")
    return results


# ============================================
# Health Check Server
# ============================================

class HealthState:
    """Shared state for health checks."""

    def __init__(self):
        self.last_sync_at: Optional[datetime] = None
        self.last_sync_success: bool = False
        self.total_syncs: int = 0
        self.failed_syncs: int = 0
        self.started_at: datetime = datetime.utcnow()


async def health_check_handler(reader, writer, state: HealthState):
    """Handle HTTP health check requests."""
    # Read request (we don't care about the content)
    await reader.read(1024)

    # Build response
    uptime = (datetime.utcnow() - state.started_at).total_seconds()
    status = "healthy" if state.last_sync_success or state.total_syncs == 0 else "unhealthy"

    body = (
        f'{{"status": "{status}", '
        f'"uptime_seconds": {uptime:.0f}, '
        f'"total_syncs": {state.total_syncs}, '
        f'"failed_syncs": {state.failed_syncs}, '
        f'"last_sync_at": "{state.last_sync_at.isoformat() if state.last_sync_at else "never"}"}}'
    )

    http_status = 200 if status == "healthy" else 503
    response = (
        f"HTTP/1.1 {http_status} {'OK' if http_status == 200 else 'Service Unavailable'}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
        f"{body}"
    )

    writer.write(response.encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def start_health_server(port: int, state: HealthState):
    """Start the health check HTTP server."""
    if port <= 0:
        return None

    async def handler(reader, writer):
        await health_check_handler(reader, writer, state)

    server = await asyncio.start_server(handler, "0.0.0.0", port)
    print(f"[Scheduler] Health check server listening on port {port}")
    return server


# ============================================
# Main Scheduler Loop
# ============================================

async def scheduler_loop(
    config: SchedulerConfig,
    token_manager: TokenManager,
    db_pool,
    health_state: HealthState,
    shutdown_event: asyncio.Event,
):
    """Main scheduling loop.

    Args:
        config: Scheduler configuration
        token_manager: TokenManager instance
        db_pool: Database connection pool
        health_state: Shared health state
        shutdown_event: Event to signal shutdown
    """
    interval_seconds = config.interval_minutes * 60

    # Initial sync on startup
    if config.sync_on_startup:
        print("[Scheduler] Running initial sync on startup...")
        results = await run_sync_with_retry(config, token_manager, db_pool)
        health_state.total_syncs += 1
        health_state.last_sync_at = datetime.utcnow()
        health_state.last_sync_success = results["success"]
        if not results["success"]:
            health_state.failed_syncs += 1
        print(f"[Scheduler] Initial sync complete: {results}")

    # Calculate next run time
    next_run = datetime.utcnow() + timedelta(seconds=interval_seconds)
    print(f"[Scheduler] Next sync at {next_run.isoformat()} (in {config.interval_minutes} minutes)")

    while not shutdown_event.is_set():
        try:
            # Wait for either the interval or shutdown
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=interval_seconds,
            )
            # If we get here, shutdown was requested
            break
        except asyncio.TimeoutError:
            # Timeout means it's time to sync
            pass

        # Run sync
        print("\n[Scheduler] ========== SCHEDULED SYNC ==========")
        print(f"[Scheduler] Time: {datetime.utcnow().isoformat()}")

        results = await run_sync_with_retry(config, token_manager, db_pool)

        health_state.total_syncs += 1
        health_state.last_sync_at = datetime.utcnow()
        health_state.last_sync_success = results["success"]
        if not results["success"]:
            health_state.failed_syncs += 1

        print(f"[Scheduler] Sync complete: success={results['success']}, duration={results.get('duration_seconds', 0):.1f}s")

        # Calculate next run
        next_run = datetime.utcnow() + timedelta(seconds=interval_seconds)
        print(f"[Scheduler] Next sync at {next_run.isoformat()} (in {config.interval_minutes} minutes)")

    print("[Scheduler] Shutdown requested, exiting loop")


# ============================================
# Main Entry Point
# ============================================

async def main():
    """Main entry point for the scheduler."""
    print("=" * 60)
    print("HPE GreenLake Sync Scheduler")
    print("=" * 60)

    # Load configuration
    config = SchedulerConfig()
    print(f"[Scheduler] Config: {config}")

    # Validate we have something to sync
    if not config.sync_devices and not config.sync_subscriptions:
        print("[Scheduler] ERROR: Nothing to sync (both SYNC_DEVICES and SYNC_SUBSCRIPTIONS are false)")
        sys.exit(1)

    # Initialize token manager
    try:
        token_manager = TokenManager()
        print("[Scheduler] TokenManager initialized")
    except ValueError as e:
        print(f"[Scheduler] ERROR: {e}")
        sys.exit(1)

    # Create database pool
    db_pool = await create_db_pool()

    # Health state
    health_state = HealthState()

    # Shutdown event
    shutdown_event = asyncio.Event()

    # Signal handlers
    def handle_shutdown(signum, frame):
        print(f"\n[Scheduler] Received signal {signum}, initiating shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start health server
    health_server = await start_health_server(config.health_check_port, health_state)

    try:
        # Run the scheduler loop
        await scheduler_loop(
            config=config,
            token_manager=token_manager,
            db_pool=db_pool,
            health_state=health_state,
            shutdown_event=shutdown_event,
        )
    finally:
        # Cleanup
        print("[Scheduler] Cleaning up...")

        if health_server:
            health_server.close()
            await health_server.wait_closed()

        if db_pool:
            await db_pool.close()

        print("[Scheduler] Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
