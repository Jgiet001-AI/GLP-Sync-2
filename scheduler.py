#!/usr/bin/env python3
"""Automated Scheduler for HPE GreenLake and Aruba Central Sync.

This module provides a long-running scheduler that automatically syncs
devices and/or subscriptions at configurable intervals. Designed to run
as the main process in a Docker container.

Architecture:
    - Simple asyncio loop with sleep (no external dependencies)
    - Graceful shutdown on SIGTERM/SIGINT
    - Configurable via environment variables
    - Health check endpoint via optional HTTP server
    - Supports both GreenLake and Aruba Central as data sources

Environment Variables:
    SYNC_INTERVAL_MINUTES: Minutes between sync runs (default: 60)
    SYNC_DEVICES: Enable GreenLake device sync (default: true)
    SYNC_SUBSCRIPTIONS: Enable subscription sync (default: true)
    SYNC_CENTRAL: Enable Aruba Central device sync (default: true)
    SYNC_ON_STARTUP: Run sync immediately on startup (default: true)
    HEALTH_CHECK_PORT: Port for health check endpoint (default: 8080, 0 to disable)

    GreenLake credentials:
        GLP_CLIENT_ID, GLP_CLIENT_SECRET, GLP_TOKEN_URL, GLP_BASE_URL

    Aruba Central credentials:
        ARUBA_CLIENT_ID, ARUBA_CLIENT_SECRET, ARUBA_BASE_URL

    Database:
        DATABASE_URL

Example:
    # Run every 30 minutes, sync both platforms
    SYNC_INTERVAL_MINUTES=30 python scheduler.py

    # Run every 6 hours, GreenLake devices only
    SYNC_INTERVAL_MINUTES=360 SYNC_SUBSCRIPTIONS=false SYNC_CENTRAL=false python scheduler.py

    # Run Aruba Central only
    SYNC_DEVICES=false SYNC_SUBSCRIPTIONS=false SYNC_CENTRAL=true python scheduler.py

Docker Usage:
    docker run -e SYNC_INTERVAL_MINUTES=60 -e DATABASE_URL=... glp-sync

Author: HPE GreenLake Team
"""
import asyncio
import logging
import os
import signal
import sys
import traceback
from datetime import UTC, datetime, timedelta
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Local imports
from src.glp.api import (
    ArubaCentralClient,
    ArubaCentralSyncer,
    ArubaTokenManager,
    DeviceSyncer,
    GLPClient,
    SubscriptionSyncer,
    TokenManager,
)

# Initialize logger
logger = logging.getLogger(__name__)

# ============================================
# Configuration
# ============================================

class SchedulerConfig:
    """Configuration loaded from environment variables."""

    def __init__(self):
        self.interval_minutes = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))
        self.sync_devices = os.getenv("SYNC_DEVICES", "true").lower() == "true"
        self.sync_subscriptions = os.getenv("SYNC_SUBSCRIPTIONS", "true").lower() == "true"
        self.sync_central = os.getenv("SYNC_CENTRAL", "true").lower() == "true"
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
            f"central={self.sync_central}, "
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
    aruba_token_manager: Optional[ArubaTokenManager] = None,
) -> dict:
    """Run a single sync cycle.

    Subscriptions are synced first (sequential) to satisfy FK constraints,
    then GreenLake devices and Aruba Central are synced in parallel.

    Args:
        config: Scheduler configuration
        token_manager: TokenManager instance for GreenLake
        db_pool: Database connection pool (can be None)
        aruba_token_manager: ArubaTokenManager instance for Aruba Central (optional)

    Returns:
        Dict with sync results
    """
    start_time = datetime.now(UTC)
    results = {
        "started_at": start_time.isoformat(),
        "devices": None,
        "subscriptions": None,
        "central": None,
        "success": False,
        "error": None,
    }

    try:
        # Step 1: Sync subscriptions FIRST (before devices)
        # This ensures subscription records exist before device_subscriptions
        # foreign key references are created during device sync
        if config.sync_subscriptions:
            try:
                async with GLPClient(token_manager) as client:
                    print("[Scheduler] Syncing subscriptions...")
                    syncer = SubscriptionSyncer(client=client, db_pool=db_pool)

                    if db_pool:
                        results["subscriptions"] = await syncer.sync()
                    else:
                        subs = await syncer.fetch_all_subscriptions()
                        results["subscriptions"] = {"fetched": len(subs), "mode": "fetch-only"}

                    logger.info("Subscription sync completed successfully")

            except Exception as e:
                # Log detailed error for subscription sync
                error_type = type(e).__name__
                error_msg = str(e)

                logger.error(
                    f"Subscription sync failed: {error_type}: {error_msg}",
                    exc_info=True
                )
                print(f"[Scheduler] ERROR: Subscription sync failed: {error_type}: {error_msg}")
                print(f"[Scheduler] Traceback: {traceback.format_exc()}")

                results["subscriptions"] = {
                    "error": error_msg,
                    "error_type": error_type,
                    "success": False
                }
                # Re-raise since subscription sync must succeed before device sync
                raise

        # Step 2: Run GreenLake device sync and Aruba Central sync in PARALLEL
        # These are independent operations writing to different columns
        parallel_tasks = []
        task_names = []

        # Define GreenLake device sync task
        async def sync_glp_devices():
            """Sync GreenLake devices with comprehensive error handling."""
            try:
                async with GLPClient(token_manager) as client:
                    print("[Scheduler] Syncing GreenLake devices...")
                    syncer = DeviceSyncer(client=client, db_pool=db_pool)

                    if db_pool:
                        return await syncer.sync()
                    else:
                        devices = await syncer.fetch_all_devices()
                        return {"fetched": len(devices), "mode": "fetch-only"}

            except Exception as e:
                # Log detailed error information
                logger.error(
                    f"GreenLake device sync failed: {type(e).__name__}: {e}",
                    exc_info=True
                )
                print(f"[Scheduler] ERROR: GreenLake device sync failed: {type(e).__name__}: {e}")
                print(f"[Scheduler] Traceback: {traceback.format_exc()}")
                # Re-raise to be caught by gather()
                raise

        # Define Aruba Central sync task
        async def sync_aruba_central():
            """Sync Aruba Central devices with comprehensive error handling."""
            try:
                async with ArubaCentralClient(aruba_token_manager) as central_client:
                    print("[Scheduler] Syncing Aruba Central devices...")
                    syncer = ArubaCentralSyncer(client=central_client, db_pool=db_pool)

                    if db_pool:
                        return await syncer.sync()
                    else:
                        central_devices = await syncer.fetch_all_devices()
                        return {"fetched": len(central_devices), "mode": "fetch-only"}

            except Exception as e:
                # Log detailed error information
                logger.error(
                    f"Aruba Central sync failed: {type(e).__name__}: {e}",
                    exc_info=True
                )
                print(f"[Scheduler] ERROR: Aruba Central sync failed: {type(e).__name__}: {e}")
                print(f"[Scheduler] Traceback: {traceback.format_exc()}")
                # Re-raise to be caught by gather()
                raise

        # Build task list
        if config.sync_devices:
            parallel_tasks.append(sync_glp_devices())
            task_names.append("devices")

        if config.sync_central and aruba_token_manager:
            parallel_tasks.append(sync_aruba_central())
            task_names.append("central")

        # Handle missing credentials warning
        if config.sync_central and not aruba_token_manager:
            print("[Scheduler] WARNING: SYNC_CENTRAL enabled but Aruba credentials not configured")
            results["central"] = {"skipped": True, "reason": "credentials_missing"}

        # Execute parallel tasks if any
        if parallel_tasks:
            if len(parallel_tasks) > 1:
                print("[Scheduler] Running GreenLake devices and Aruba Central sync in parallel...")

            # Use return_exceptions=True to handle partial failures
            parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

            # Process results and handle exceptions
            has_errors = False
            for i, result in enumerate(parallel_results):
                task_name = task_names[i]

                if isinstance(result, Exception):
                    # Log detailed error information
                    error_type = type(result).__name__
                    error_msg = str(result)

                    logger.error(
                        f"Parallel sync task '{task_name}' failed: {error_type}: {error_msg}",
                        exc_info=result
                    )
                    print(f"[Scheduler] ERROR: {task_name} sync failed: {error_type}: {error_msg}")

                    # Store error details in results
                    results[task_name] = {
                        "error": error_msg,
                        "error_type": error_type,
                        "success": False
                    }
                    has_errors = True
                else:
                    # Successful result
                    logger.info(f"Parallel sync task '{task_name}' completed successfully")
                    results[task_name] = result

            # Only mark success if no errors occurred
            if not has_errors:
                results["success"] = True
            else:
                # Log summary of parallel sync failures
                failed_tasks = [task_names[i] for i, r in enumerate(parallel_results) if isinstance(r, Exception)]
                logger.warning(f"Parallel sync completed with failures in: {', '.join(failed_tasks)}")
                print(f"[Scheduler] WARNING: Parallel sync completed with failures in: {', '.join(failed_tasks)}")
        else:
            # No parallel tasks to run, mark as successful
            results["success"] = True

    except Exception as e:
        # Log top-level sync errors with full context
        error_type = type(e).__name__
        error_msg = str(e)

        logger.error(
            f"Sync cycle failed: {error_type}: {error_msg}",
            exc_info=True
        )
        print(f"[Scheduler] ERROR during sync: {error_type}: {error_msg}")
        print(f"[Scheduler] Traceback: {traceback.format_exc()}")

        results["error"] = error_msg
        results["error_type"] = error_type
        results["success"] = False

    end_time = datetime.now(UTC)
    results["completed_at"] = end_time.isoformat()
    results["duration_seconds"] = (end_time - start_time).total_seconds()

    return results


async def run_sync_with_retry(
    config: SchedulerConfig,
    token_manager: TokenManager,
    db_pool,
    aruba_token_manager: Optional[ArubaTokenManager] = None,
) -> dict:
    """Run sync with retry logic on failure.

    Args:
        config: Scheduler configuration
        token_manager: TokenManager instance for GreenLake
        db_pool: Database connection pool
        aruba_token_manager: ArubaTokenManager instance for Aruba Central (optional)

    Returns:
        Dict with sync results
    """
    last_error = None

    for attempt in range(config.max_retries):
        results = await run_sync(config, token_manager, db_pool, aruba_token_manager)

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
        self.started_at: datetime = datetime.now(UTC)


async def health_check_handler(reader, writer, state: HealthState):
    """Handle HTTP health check requests."""
    # Read request (we don't care about the content)
    await reader.read(1024)

    # Build response
    uptime = (datetime.now(UTC) - state.started_at).total_seconds()
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
    aruba_token_manager: Optional[ArubaTokenManager] = None,
):
    """Main scheduling loop.

    Args:
        config: Scheduler configuration
        token_manager: TokenManager instance for GreenLake
        db_pool: Database connection pool
        health_state: Shared health state
        shutdown_event: Event to signal shutdown
        aruba_token_manager: ArubaTokenManager instance for Aruba Central (optional)
    """
    interval_seconds = config.interval_minutes * 60

    # Initial sync on startup
    if config.sync_on_startup:
        print("[Scheduler] Running initial sync on startup...")
        results = await run_sync_with_retry(config, token_manager, db_pool, aruba_token_manager)
        health_state.total_syncs += 1
        health_state.last_sync_at = datetime.now(UTC)
        health_state.last_sync_success = results["success"]
        if not results["success"]:
            health_state.failed_syncs += 1
        print(f"[Scheduler] Initial sync complete: {results}")

    # Calculate next run time
    next_run = datetime.now(UTC) + timedelta(seconds=interval_seconds)
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
        print(f"[Scheduler] Time: {datetime.now(UTC).isoformat()}")

        results = await run_sync_with_retry(config, token_manager, db_pool, aruba_token_manager)

        health_state.total_syncs += 1
        health_state.last_sync_at = datetime.now(UTC)
        health_state.last_sync_success = results["success"]
        if not results["success"]:
            health_state.failed_syncs += 1

        print(f"[Scheduler] Sync complete: success={results['success']}, duration={results.get('duration_seconds', 0):.1f}s")

        # Calculate next run
        next_run = datetime.now(UTC) + timedelta(seconds=interval_seconds)
        print(f"[Scheduler] Next sync at {next_run.isoformat()} (in {config.interval_minutes} minutes)")

    print("[Scheduler] Shutdown requested, exiting loop")


# ============================================
# Main Entry Point
# ============================================

async def main():
    """Main entry point for the scheduler."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    print("=" * 60)
    print("HPE GreenLake Sync Scheduler")
    print("=" * 60)

    # Load configuration
    config = SchedulerConfig()
    print(f"[Scheduler] Config: {config}")

    # Validate we have something to sync
    if not config.sync_devices and not config.sync_subscriptions and not config.sync_central:
        print("[Scheduler] ERROR: Nothing to sync (SYNC_DEVICES, SYNC_SUBSCRIPTIONS, and SYNC_CENTRAL are all false)")
        sys.exit(1)

    # Block invalid configuration: devices without subscriptions when DB is configured
    # The device_subscriptions table has a FK constraint to subscriptions table
    # so devices must be synced AFTER subscriptions (which we do), but both must be enabled
    if config.sync_devices and not config.sync_subscriptions:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            print("[Scheduler] ERROR: SYNC_DEVICES=true but SYNC_SUBSCRIPTIONS=false with DATABASE_URL set")
            print("[Scheduler] ERROR: Device sync requires subscriptions to be synced first (FK constraint)")
            print("[Scheduler] ERROR: Please set SYNC_SUBSCRIPTIONS=true or disable DATABASE_URL for fetch-only mode")
            sys.exit(1)
        else:
            # In fetch-only mode (no DB), this is allowed
            print("[Scheduler] INFO: SYNC_DEVICES=true but SYNC_SUBSCRIPTIONS=false (fetch-only mode, no DB)")

    # Initialize GreenLake token manager (required for devices/subscriptions)
    token_manager = None
    if config.sync_devices or config.sync_subscriptions:
        try:
            token_manager = TokenManager()
            print("[Scheduler] GreenLake TokenManager initialized")
        except ValueError as e:
            print(f"[Scheduler] ERROR: GreenLake credentials missing: {e}")
            if not config.sync_central:
                sys.exit(1)
            print("[Scheduler] Continuing with Aruba Central only...")

    # Initialize Aruba Central token manager (optional)
    aruba_token_manager = None
    if config.sync_central:
        try:
            aruba_token_manager = ArubaTokenManager()
            print("[Scheduler] ArubaTokenManager initialized")
        except ValueError as e:
            print(f"[Scheduler] WARNING: Aruba Central credentials missing: {e}")
            if not token_manager:
                print("[Scheduler] ERROR: No valid credentials for any sync source")
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
            aruba_token_manager=aruba_token_manager,
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
