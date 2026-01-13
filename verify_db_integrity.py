#!/usr/bin/env python3
"""Database Integrity Verification Script.

Verifies database integrity after parallel sync operations by checking:
1. Record counts in core tables (devices, subscriptions, device_subscriptions)
2. Foreign key constraint integrity (no orphaned device_subscriptions)
3. Latest sync_history entry showing successful completion
4. Data consistency and referential integrity

Usage:
    python verify_db_integrity.py

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (required)

Exit Codes:
    0: All checks passed
    1: One or more checks failed
    2: Database connection error or missing configuration
"""
import asyncio
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Tuple

import asyncpg
from dotenv import load_dotenv

load_dotenv()


class IntegrityCheck:
    """Represents a single integrity verification check."""

    def __init__(self, name: str, passed: bool, details: str):
        self.name = name
        self.passed = passed
        self.details = details

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} | {self.name}\n       {self.details}"


async def verify_database_integrity() -> List[IntegrityCheck]:
    """Run all database integrity checks.

    Returns:
        List of IntegrityCheck results
    """
    checks = []

    # Get database URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable not set")
        sys.exit(2)

    try:
        # Connect to database
        conn = await asyncpg.connect(database_url)

        try:
            # Check 1: Count devices
            device_count = await conn.fetchval("SELECT COUNT(*) FROM devices;")
            checks.append(IntegrityCheck(
                "Devices count",
                device_count >= 0,
                f"Total devices: {device_count:,}"
            ))

            # Check 2: Count subscriptions
            subscription_count = await conn.fetchval("SELECT COUNT(*) FROM subscriptions;")
            checks.append(IntegrityCheck(
                "Subscriptions count",
                subscription_count >= 0,
                f"Total subscriptions: {subscription_count:,}"
            ))

            # Check 3: Count device_subscriptions relationships
            device_sub_count = await conn.fetchval("SELECT COUNT(*) FROM device_subscriptions;")
            checks.append(IntegrityCheck(
                "Device-subscription relationships count",
                device_sub_count >= 0,
                f"Total relationships: {device_sub_count:,}"
            ))

            # Check 4: Verify no orphaned device_subscriptions (FK constraint integrity)
            orphaned_query = """
                SELECT COUNT(*)
                FROM device_subscriptions ds
                WHERE NOT EXISTS (
                    SELECT 1 FROM subscriptions s WHERE s.id = ds.subscription_id
                );
            """
            orphaned_count = await conn.fetchval(orphaned_query)
            checks.append(IntegrityCheck(
                "Foreign key constraint integrity",
                orphaned_count == 0,
                f"Orphaned device_subscriptions: {orphaned_count} (expected: 0)"
            ))

            # Check 5: Verify device references in device_subscriptions exist
            orphaned_devices_query = """
                SELECT COUNT(*)
                FROM device_subscriptions ds
                WHERE NOT EXISTS (
                    SELECT 1 FROM devices d WHERE d.id = ds.device_id
                );
            """
            orphaned_devices = await conn.fetchval(orphaned_devices_query)
            checks.append(IntegrityCheck(
                "Device references integrity",
                orphaned_devices == 0,
                f"Orphaned device references: {orphaned_devices} (expected: 0)"
            ))

            # Check 6: Get latest sync_history entry
            latest_sync_query = """
                SELECT
                    id, resource_type, started_at, completed_at,
                    status, records_fetched, records_inserted, records_updated,
                    records_errors, error_message
                FROM sync_history
                ORDER BY started_at DESC
                LIMIT 1;
            """
            latest_sync = await conn.fetchrow(latest_sync_query)

            if latest_sync:
                sync_id = latest_sync['id']
                resource_type = latest_sync['resource_type']
                started_at = latest_sync['started_at']
                completed_at = latest_sync['completed_at']
                status = latest_sync['status']
                records_fetched = latest_sync['records_fetched'] or 0
                records_inserted = latest_sync['records_inserted'] or 0
                records_updated = latest_sync['records_updated'] or 0
                records_errors = latest_sync['records_errors'] or 0
                error_message = latest_sync['error_message']

                # Format duration
                duration = ""
                if completed_at and started_at:
                    duration_seconds = (completed_at - started_at).total_seconds()
                    duration = f" (duration: {duration_seconds:.2f}s)"

                sync_details = (
                    f"ID: {sync_id}, Type: {resource_type}, Status: {status}\n"
                    f"       Started: {started_at.strftime('%Y-%m-%d %H:%M:%S')}{duration}\n"
                    f"       Fetched: {records_fetched:,}, Inserted: {records_inserted:,}, "
                    f"Updated: {records_updated:,}, Errors: {records_errors:,}"
                )
                if error_message:
                    sync_details += f"\n       Error: {error_message}"

                checks.append(IntegrityCheck(
                    "Latest sync history entry",
                    status == 'completed' and error_message is None and records_errors == 0,
                    sync_details
                ))
            else:
                checks.append(IntegrityCheck(
                    "Latest sync history entry",
                    False,
                    "No sync history records found"
                ))

            # Check 7: Verify all device_subscriptions have both valid device_id and subscription_id
            invalid_relationships_query = """
                SELECT COUNT(*)
                FROM device_subscriptions ds
                WHERE ds.device_id IS NULL OR ds.subscription_id IS NULL;
            """
            invalid_relationships = await conn.fetchval(invalid_relationships_query)
            checks.append(IntegrityCheck(
                "Relationship data completeness",
                invalid_relationships == 0,
                f"Invalid relationships (NULL keys): {invalid_relationships} (expected: 0)"
            ))

            # Check 8: Verify devices table has required fields populated
            devices_missing_data_query = """
                SELECT COUNT(*)
                FROM devices
                WHERE serial_number IS NULL OR raw_data IS NULL;
            """
            devices_missing_data = await conn.fetchval(devices_missing_data_query)
            checks.append(IntegrityCheck(
                "Device data completeness",
                devices_missing_data == 0,
                f"Devices with missing required fields: {devices_missing_data} (expected: 0)"
            ))

            # Check 9: Verify subscriptions table has required fields populated
            subs_missing_data_query = """
                SELECT COUNT(*)
                FROM subscriptions
                WHERE raw_data IS NULL;
            """
            subs_missing_data = await conn.fetchval(subs_missing_data_query)
            checks.append(IntegrityCheck(
                "Subscription data completeness",
                subs_missing_data == 0,
                f"Subscriptions with missing raw_data: {subs_missing_data} (expected: 0)"
            ))

            # Check 10: Summary statistics
            summary_query = """
                SELECT
                    (SELECT COUNT(*) FROM devices WHERE archived = FALSE) as active_devices,
                    (SELECT COUNT(*) FROM subscriptions WHERE subscription_status = 'STARTED') as active_subscriptions,
                    (SELECT COUNT(DISTINCT device_id) FROM device_subscriptions) as devices_with_subscriptions;
            """
            summary = await conn.fetchrow(summary_query)

            checks.append(IntegrityCheck(
                "Database summary",
                True,  # Informational check, always passes
                (
                    f"Active devices: {summary['active_devices']:,}, "
                    f"Active subscriptions: {summary['active_subscriptions']:,}, "
                    f"Devices with subscriptions: {summary['devices_with_subscriptions']:,}"
                )
            ))

        finally:
            await conn.close()

    except asyncpg.PostgresError as e:
        print(f"❌ ERROR: Database error: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"❌ ERROR: Unexpected error: {e}")
        sys.exit(2)

    return checks


def print_results(checks: List[IntegrityCheck]) -> bool:
    """Print verification results.

    Args:
        checks: List of integrity check results

    Returns:
        True if all checks passed, False otherwise
    """
    print("=" * 80)
    print("DATABASE INTEGRITY VERIFICATION")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    all_passed = True
    for check in checks:
        print(check)
        if not check.passed:
            all_passed = False

    print("\n" + "=" * 80)

    passed_count = sum(1 for c in checks if c.passed)
    total_count = len(checks)

    if all_passed:
        print(f"✅ ALL CHECKS PASSED ({passed_count}/{total_count})")
        print("=" * 80)
        print("\n✓ Database integrity verified successfully")
        return True
    else:
        failed_count = total_count - passed_count
        print(f"❌ SOME CHECKS FAILED ({passed_count}/{total_count} passed, {failed_count} failed)")
        print("=" * 80)
        print("\n✗ Database integrity verification failed")
        print("  Please review the failed checks above and investigate any issues.")
        return False


async def main():
    """Main entry point."""
    checks = await verify_database_integrity()
    all_passed = print_results(checks)

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
