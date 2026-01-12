#!/usr/bin/env python3
"""Test script for Aruba Central integration.

This script verifies the Aruba Central integration works correctly:
1. Token acquisition from HPE SSO
2. API connectivity to Aruba Central
3. Device fetching with pagination
4. Database sync (optional, requires PostgreSQL)

Usage:
    # Test API only (no database)
    python test_aruba_central.py

    # Test with database sync
    python test_aruba_central.py --with-db

    # Save devices to JSON file
    python test_aruba_central.py --save-json

    # Verbose output
    python test_aruba_central.py -v

Environment Variables Required:
    ARUBA_CLIENT_ID     - OAuth2 client ID
    ARUBA_CLIENT_SECRET - OAuth2 client secret
    ARUBA_BASE_URL      - Regional API base URL (e.g., https://us2.api.central.arubanetworks.com)

Optional:
    DATABASE_URL        - PostgreSQL connection string (for --with-db)
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def setup_logging(verbose: bool = False):
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    # Reduce noise from aiohttp
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def check_env_vars() -> dict:
    """Check required environment variables are set."""
    required = {
        "ARUBA_CLIENT_ID": os.getenv("ARUBA_CLIENT_ID"),
        "ARUBA_CLIENT_SECRET": os.getenv("ARUBA_CLIENT_SECRET"),
        "ARUBA_BASE_URL": os.getenv("ARUBA_BASE_URL"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"\n[ERROR] Missing required environment variables: {', '.join(missing)}")
        print("\nPlease set these in your .env file:")
        for var in missing:
            print(f"  {var}=your-value-here")
        sys.exit(1)

    return required


async def test_token_manager():
    """Test 1: Token acquisition."""
    print("\n" + "=" * 60)
    print("TEST 1: Token Acquisition")
    print("=" * 60)

    from src.glp.api import ArubaTokenManager

    try:
        manager = ArubaTokenManager()
        print(f"  Token URL: {manager.token_url}")
        print(f"  Client ID: {manager.client_id[:8]}...")

        # Get token
        token = await manager.get_token()
        print(f"  [OK] Token acquired: {token[:30]}...")

        # Check token info
        info = manager.token_info
        print(f"  [OK] Token expires in: {info['time_remaining_seconds']:.0f}s")

        # Test caching
        token2 = await manager.get_token()
        assert token == token2, "Token should be cached"
        print("  [OK] Token caching works")

        return True, manager

    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        return False, None


async def test_api_connectivity(token_manager):
    """Test 2: API connectivity."""
    print("\n" + "=" * 60)
    print("TEST 2: API Connectivity")
    print("=" * 60)

    from src.glp.api import ArubaCentralClient

    base_url = os.getenv("ARUBA_BASE_URL")
    print(f"  Base URL: {base_url}")

    try:
        async with ArubaCentralClient(token_manager) as client:
            # Try to fetch first page of devices
            data = await client.get(
                "/network-monitoring/v1alpha1/device-inventory",
                params={"limit": 5}
            )

            print(f"  [OK] API responded successfully")
            print(f"  Response keys: {list(data.keys())}")

            # Check response structure
            if "items" in data:
                items = data["items"]
                print(f"  [OK] Found 'items' key with {len(items)} devices")
            elif "devices" in data:
                items = data["devices"]
                print(f"  [OK] Found 'devices' key with {len(items)} devices")
            else:
                items = []
                print(f"  [WARN] Unknown response structure: {list(data.keys())}")

            # Show total count if available
            if "total" in data:
                print(f"  Total devices in Central: {data['total']:,}")
            elif "count" in data:
                print(f"  Count in response: {data['count']}")

            # Check pagination
            if "next" in data:
                print(f"  [OK] Pagination cursor present: {data['next'][:30] if data['next'] else 'None'}...")

            # Show sample device
            if items:
                device = items[0]
                print(f"\n  Sample device:")
                print(f"    Serial: {device.get('serialNumber', 'N/A')}")
                print(f"    Name: {device.get('deviceName', 'N/A')}")
                print(f"    Type: {device.get('deviceType', 'N/A')}")
                print(f"    Status: {device.get('status', 'N/A')}")
                print(f"    IP: {device.get('ipv4', 'N/A')}")

            # Check rate limits
            if client.rate_limit_info:
                rl = client.rate_limit_info
                print(f"\n  Rate Limit Info:")
                print(f"    Remaining: {rl.remaining}/{rl.limit}")

            return True, client, data

    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None


async def test_pagination(token_manager, max_pages: int = 3):
    """Test 3: Pagination."""
    print("\n" + "=" * 60)
    print(f"TEST 3: Pagination (max {max_pages} pages)")
    print("=" * 60)

    from src.glp.api import ArubaCentralClient, ArubaPaginationConfig

    try:
        async with ArubaCentralClient(token_manager) as client:
            config = ArubaPaginationConfig(
                page_size=100,
                delay_between_pages=0.5,
                max_pages=max_pages,
            )

            total_devices = 0
            pages = 0

            async for page in client.paginate(
                "/network-monitoring/v1alpha1/device-inventory",
                config=config,
            ):
                pages += 1
                total_devices += len(page)
                print(f"  Page {pages}: {len(page)} devices")

            print(f"\n  [OK] Fetched {total_devices} devices in {pages} pages")
            return True, total_devices

    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


async def test_database_sync(token_manager):
    """Test 4: Database sync (optional)."""
    print("\n" + "=" * 60)
    print("TEST 4: Database Sync")
    print("=" * 60)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("  [SKIP] DATABASE_URL not set")
        return None

    from src.glp.api import ArubaCentralClient, ArubaCentralSyncer, create_pool, close_pool

    try:
        # Create database pool
        print("  Connecting to database...")
        pool = await create_pool(database_url)
        print(f"  [OK] Connected to database")

        # Run sync
        async with ArubaCentralClient(token_manager) as client:
            syncer = ArubaCentralSyncer(client=client, db_pool=pool)

            print("  Running sync (this may take a while)...")
            stats = await syncer.sync()

            print(f"\n  Sync Results:")
            print(f"    Total pages: {stats.get('total_pages', 'N/A')}")
            print(f"    Devices upserted: {stats.get('total_upserted', 'N/A')}")
            print(f"    Devices skipped: {stats.get('total_skipped', 'N/A')}")
            print(f"    Unique serials: {stats.get('unique_serials', 'N/A')}")
            print(f"    Errors: {stats.get('errors', 'N/A')}")

        # Query results
        async with pool.acquire() as conn:
            # Count devices by platform
            result = await conn.fetch('''
                SELECT
                    CASE
                        WHEN in_greenlake AND in_central THEN 'Both Platforms'
                        WHEN in_greenlake THEN 'GreenLake Only'
                        WHEN in_central THEN 'Central Only'
                        ELSE 'Unknown'
                    END as platform,
                    COUNT(*) as count
                FROM devices
                WHERE NOT archived
                GROUP BY 1
                ORDER BY 2 DESC
            ''')

            print(f"\n  Platform Coverage:")
            for row in result:
                print(f"    {row['platform']}: {row['count']:,}")

            # Count Central status
            status_result = await conn.fetch('''
                SELECT central_status, COUNT(*) as count
                FROM devices
                WHERE in_central = TRUE AND NOT archived
                GROUP BY central_status
            ''')

            if status_result:
                print(f"\n  Central Device Status:")
                for row in status_result:
                    status = row['central_status'] or 'Unknown'
                    print(f"    {status}: {row['count']:,}")

        await close_pool(pool)
        print(f"\n  [OK] Database sync completed successfully")
        return True

    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def save_to_json(token_manager, filepath: str = "central_devices.json"):
    """Save all devices to JSON file."""
    print("\n" + "=" * 60)
    print(f"Saving devices to {filepath}")
    print("=" * 60)

    from src.glp.api import ArubaCentralClient, ArubaCentralSyncer

    try:
        async with ArubaCentralClient(token_manager) as client:
            syncer = ArubaCentralSyncer(client=client)
            count = await syncer.fetch_and_save_json(filepath)
            print(f"  [OK] Saved {count:,} devices to {filepath}")
            return True
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        return False


async def main():
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Test Aruba Central integration")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--with-db", action="store_true", help="Include database sync test")
    parser.add_argument("--save-json", action="store_true", help="Save devices to JSON file")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages for pagination test")
    args = parser.parse_args()

    setup_logging(args.verbose)

    print("\n" + "=" * 60)
    print("ARUBA CENTRAL INTEGRATION TEST")
    print("=" * 60)
    print(f"Started: {datetime.now().isoformat()}")

    # Check environment
    env_vars = check_env_vars()
    print(f"\nEnvironment:")
    print(f"  Base URL: {env_vars['ARUBA_BASE_URL']}")
    print(f"  Client ID: {env_vars['ARUBA_CLIENT_ID'][:8]}...")

    results = {}

    # Test 1: Token
    success, token_manager = await test_token_manager()
    results["Token Acquisition"] = success

    if not success:
        print("\n[ABORT] Cannot continue without token")
        return 1

    # Test 2: API
    success, client, data = await test_api_connectivity(token_manager)
    results["API Connectivity"] = success

    if not success:
        print("\n[ABORT] Cannot continue without API access")
        return 1

    # Test 3: Pagination
    success, count = await test_pagination(token_manager, args.max_pages)
    results["Pagination"] = success

    # Test 4: Database (optional)
    if args.with_db:
        success = await test_database_sync(token_manager)
        results["Database Sync"] = success

    # Save JSON (optional)
    if args.save_json:
        success = await save_to_json(token_manager)
        results["Save JSON"] = success

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = 0
    failed = 0
    skipped = 0

    for test, result in results.items():
        if result is True:
            status = "[PASS]"
            passed += 1
        elif result is False:
            status = "[FAIL]"
            failed += 1
        else:
            status = "[SKIP]"
            skipped += 1
        print(f"  {status} {test}")

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"Finished: {datetime.now().isoformat()}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
