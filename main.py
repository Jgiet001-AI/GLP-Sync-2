#!/usr/bin/env python3
"""HPE GreenLake Device & Subscription Sync CLI.

This module provides a command-line interface for synchronizing inventory
from the HPE GreenLake Platform (GLP) API to a PostgreSQL database. It supports
both full database sync and JSON-only export modes for devices and subscriptions.

Architecture:
    - Uses GLPClient as the shared HTTP layer for all API calls
    - TokenManager handles OAuth2 client credentials flow
    - DeviceSyncer and SubscriptionSyncer compose GLPClient
    - Supports concurrent sync of multiple resource types

Environment Variables Required:
    - GLP_CLIENT_ID: OAuth2 client ID
    - GLP_CLIENT_SECRET: OAuth2 client secret  
    - GLP_TOKEN_URL: OAuth2 token endpoint
    - GLP_BASE_URL: GreenLake API base URL
    - DATABASE_URL: PostgreSQL connection string (optional for --json-only)

Example Usage:
    $ python main.py                              # Sync devices to database
    $ python main.py --json-only                  # Export devices to JSON
    $ python main.py --subscriptions              # Sync subscriptions
    $ python main.py --all                        # Sync devices + subscriptions
    $ python main.py --expiring-days 90           # Show expiring subscriptions

Author: HPE GreenLake Team
"""
import os
import sys
import asyncio
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Local imports
from src.glp.api import (
    TokenManager,
    GLPClient,
    DeviceSyncer,
    SubscriptionSyncer,
)


async def setup_database():
    """Create database connection pool.
    
    Returns:
        asyncpg.Pool or None if database not configured
    """
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        return None
    
    try:
        import asyncpg
        
        pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        
        print(f"[Main] Connected to PostgreSQL")
        return pool
        
    except ImportError:
        print("[Main] asyncpg not installed. Run: pip install asyncpg")
        return None
    except Exception as e:
        print(f"[Main] Database connection failed: {e}")
        return None


async def run_device_sync(
    client: GLPClient,
    db_pool,
    json_only: bool = False,
    backup_file: str = None,
) -> dict:
    """Run device synchronization.
    
    Args:
        client: Configured GLPClient instance
        db_pool: Database connection pool (can be None for JSON-only)
        json_only: If True, only export to JSON
        backup_file: Optional JSON backup filename
    
    Returns:
        Sync statistics dictionary
    """
    syncer = DeviceSyncer(client=client, db_pool=db_pool)
    
    if json_only:
        filename = backup_file or "devices.json"
        count = await syncer.fetch_and_save_json(filename)
        return {"devices_exported": count, "file": filename}
    else:
        stats = await syncer.sync()
        
        # Also save a backup JSON if requested
        if backup_file:
            devices = await syncer.fetch_all_devices()
            import json
            with open(backup_file, "w") as f:
                json.dump(devices, f, indent=2)
            print(f"[Main] Device backup saved to {backup_file}")
        
        return stats


async def run_subscription_sync(
    client: GLPClient,
    db_pool,
    json_only: bool = False,
    backup_file: str = None,
) -> dict:
    """Run subscription synchronization.
    
    Args:
        client: Configured GLPClient instance
        db_pool: Database connection pool (can be None for JSON-only)
        json_only: If True, only export to JSON
        backup_file: Optional JSON backup filename
    
    Returns:
        Sync statistics dictionary
    """
    syncer = SubscriptionSyncer(client=client, db_pool=db_pool)
    
    if json_only:
        filename = backup_file or "subscriptions.json"
        count = await syncer.fetch_and_save_json(filename)
        return {"subscriptions_exported": count, "file": filename}
    else:
        stats = await syncer.sync()
        
        # Also save a backup JSON if requested
        if backup_file:
            subscriptions = await syncer.fetch_all_subscriptions()
            import json
            with open(backup_file, "w") as f:
                json.dump(subscriptions, f, indent=2)
            print(f"[Main] Subscription backup saved to {backup_file}")
        
        return stats


async def show_expiring_subscriptions(
    client: GLPClient,
    days: int = 90,
) -> None:
    """Display subscriptions expiring within N days.
    
    Args:
        client: Configured GLPClient instance
        days: Number of days to look ahead
    """
    syncer = SubscriptionSyncer(client=client)
    
    print(f"\n[Main] Fetching subscriptions expiring in next {days} days...")
    expiring = await syncer.fetch_expiring_soon(days=days)
    
    if not expiring:
        print(f"✓ No subscriptions expiring in the next {days} days")
        return
    
    print(f"\n⚠️  Found {len(expiring)} expiring subscription(s):\n")
    print(f"{'Key':<20} {'Type':<20} {'End Date':<25} {'Status':<12}")
    print("-" * 80)
    
    for sub in expiring:
        key = sub.get("key", "N/A")[:18]
        sub_type = sub.get("subscriptionType", "N/A")[:18]
        end_time = sub.get("endTime", "N/A")[:23]
        status = sub.get("subscriptionStatus", "N/A")
        print(f"{key:<20} {sub_type:<20} {end_time:<25} {status:<12}")
    
    # Summary by type
    print("\n" + "-" * 80)
    summary = syncer.summarize_by_type(expiring)
    print("By Type:", dict(summary))


async def run_sync(args: argparse.Namespace):
    """Main sync orchestration function.
    
    Args:
        args: Parsed command-line arguments
    """
    start_time = datetime.utcnow()
    print(f"[Main] Starting at {start_time.isoformat()}")
    
    # Initialize token manager
    try:
        token_manager = TokenManager()
    except ValueError as e:
        print(f"[Main] Configuration error: {e}")
        sys.exit(1)
    
    # Setup database (if not json_only)
    db_pool = None
    json_only = args.json_only
    
    if not json_only:
        db_pool = await setup_database()
        if db_pool is None and not args.expiring_days:
            print("[Main] No database configured, falling back to JSON-only mode")
            json_only = True
    
    try:
        # Use GLPClient as async context manager
        async with GLPClient(token_manager) as client:
            
            # Handle --expiring-days separately (no DB needed)
            if args.expiring_days:
                await show_expiring_subscriptions(client, days=args.expiring_days)
                return
            
            # Determine what to sync
            sync_devices = args.devices or args.all or (not args.subscriptions)
            sync_subscriptions = args.subscriptions or args.all
            
            results = {}
            
            # Run syncs (could be parallelized with asyncio.gather)
            if sync_devices:
                print("\n" + "=" * 60)
                print("SYNCING DEVICES")
                print("=" * 60)
                results["devices"] = await run_device_sync(
                    client=client,
                    db_pool=db_pool,
                    json_only=json_only,
                    backup_file=args.backup if not args.subscriptions else None,
                )
            
            if sync_subscriptions:
                print("\n" + "=" * 60)
                print("SYNCING SUBSCRIPTIONS")
                print("=" * 60)
                results["subscriptions"] = await run_subscription_sync(
                    client=client,
                    db_pool=db_pool,
                    json_only=json_only,
                    backup_file=args.subscription_backup,
                )
            
            # Print summary
            print("\n" + "=" * 60)
            print("SYNC COMPLETE")
            print("=" * 60)
            for resource, stats in results.items():
                print(f"\n{resource.upper()}: {stats}")
    
    finally:
        # Cleanup
        if db_pool:
            await db_pool.close()
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    print(f"\n[Main] Completed in {duration:.1f} seconds")


def main():
    parser = argparse.ArgumentParser(
        description="Sync HPE GreenLake devices and subscriptions to PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Sync devices to database
  python main.py --json-only              # Export devices to devices.json
  python main.py --subscriptions          # Sync subscriptions only
  python main.py --all                    # Sync both devices and subscriptions
  python main.py --expiring-days 90       # List subscriptions expiring in 90 days
  python main.py --backup backup.json     # Sync devices + create backup
        """
    )
    
    # Resource selection
    resource_group = parser.add_argument_group("Resource Selection")
    resource_group.add_argument(
        "--devices",
        action="store_true",
        help="Sync devices (default if no resource specified)"
    )
    resource_group.add_argument(
        "--subscriptions",
        action="store_true",
        help="Sync subscriptions"
    )
    resource_group.add_argument(
        "--all",
        action="store_true",
        help="Sync both devices and subscriptions"
    )
    
    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--json-only",
        action="store_true",
        help="Only fetch and save to JSON (no database required)"
    )
    output_group.add_argument(
        "--backup",
        type=str,
        metavar="FILE",
        help="Save a JSON backup of devices to FILE"
    )
    output_group.add_argument(
        "--subscription-backup",
        type=str,
        metavar="FILE",
        help="Save a JSON backup of subscriptions to FILE"
    )
    
    # Subscription-specific options
    sub_group = parser.add_argument_group("Subscription Options")
    sub_group.add_argument(
        "--expiring-days",
        type=int,
        metavar="DAYS",
        help="Show subscriptions expiring within DAYS (no sync, just report)"
    )
    
    args = parser.parse_args()
    
    # Run the async sync
    asyncio.run(run_sync(args))


if __name__ == "__main__":
    main()