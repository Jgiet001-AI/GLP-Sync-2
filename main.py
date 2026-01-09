#!/usr/bin/env python3
"""HPE GreenLake Device Sync CLI.

This module provides a command-line interface for synchronizing device inventory
from the HPE GreenLake Platform (GLP) API to a PostgreSQL database. It supports
both full database sync and JSON-only export modes.

Architecture:
    - Uses OAuth2 client credentials flow via TokenManager
    - Fetches devices using paginated API calls (2000 devices/request)
    - Upserts to PostgreSQL with full device metadata and raw JSON storage

Environment Variables Required:
    - GLP_CLIENT_ID: OAuth2 client ID
    - GLP_CLIENT_SECRET: OAuth2 client secret  
    - GLP_TOKEN_URL: OAuth2 token endpoint
    - GLP_BASE_URL: GreenLake API base URL
    - DATABASE_URL: PostgreSQL connection string (optional for --json-only)

Example Usage:
    $ python main.py                      # Full sync to database
    $ python main.py --json-only          # Export to devices.json
    $ python main.py --backup backup.json # Sync + create backup

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
from src.glp.api.auth import TokenManager
from src.glp.api.devices import DeviceSyncer


async def setup_database():
    """Create database connection pool."""
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        return None
    
    try:
        import asyncpg
        
        # Parse DATABASE_URL and create pool
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


async def run_sync(json_only: bool = False, backup_file: str = None):
    """
    Run the device sync.
    
    Args:
        json_only: If True, only fetch and save to JSON (no database)
        backup_file: Optional JSON backup filename
    """
    start_time = datetime.utcnow()
    print(f"[Main] Starting sync at {start_time.isoformat()}")
    
    # Initialize token manager
    try:
        token_manager = TokenManager()
    except ValueError as e:
        print(f"[Main] Configuration error: {e}")
        sys.exit(1)
    
    # Setup database (if not json_only)
    db_pool = None
    if not json_only:
        db_pool = await setup_database()
        if db_pool is None:
            print("[Main] No database configured, falling back to JSON-only mode")
            json_only = True
    
    # Initialize syncer
    syncer = DeviceSyncer(
        token_manager=token_manager,
        db_pool=db_pool,
    )
    
    try:
        if json_only:
            # Just fetch and save to JSON
            filename = backup_file or "devices.json"
            count = await syncer.fetch_and_save_json(filename)
            print(f"[Main] Saved {count:,} devices to {filename}")
        else:
            # Full sync to database
            stats = await syncer.sync()
            
            # Also save a backup JSON if requested
            if backup_file:
                devices = await syncer.fetch_all_devices()
                import json
                with open(backup_file, "w") as f:
                    json.dump(devices, f, indent=2)
                print(f"[Main] Backup saved to {backup_file}")
            
            print(f"[Main] Sync stats: {stats}")
    
    finally:
        # Cleanup
        if db_pool:
            await db_pool.close()
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    print(f"[Main] Completed in {duration:.1f} seconds")


def main():
    parser = argparse.ArgumentParser(
        description="Sync HPE GreenLake devices to PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Full sync to database
  python main.py --json-only        # Fetch and save to devices.json
  python main.py --backup backup.json  # Sync to DB and save backup
        """
    )
    
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only fetch devices and save to JSON (no database required)"
    )
    
    parser.add_argument(
        "--backup",
        type=str,
        metavar="FILE",
        help="Save a JSON backup to FILE"
    )
    
    args = parser.parse_args()
    
    # Run the async sync
    asyncio.run(run_sync(
        json_only=args.json_only,
        backup_file=args.backup,
    ))


if __name__ == "__main__":
    main()