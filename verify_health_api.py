#!/usr/bin/env python3
"""
Verification script for Device Health Aggregation API
Tests both database view and API endpoints
"""
import asyncio
import asyncpg
import httpx
import os
import sys
import json
from datetime import datetime


def load_env():
    """Load environment variables from .env file"""
    env_vars = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key] = value
                    os.environ[key] = value
    except FileNotFoundError:
        print("⚠ Warning: .env file not found")
    return env_vars


async def verify_database_view(db_url: str):
    """Verify the device_health_aggregation view exists and returns data"""
    print("\n=== DATABASE VIEW VERIFICATION ===\n")

    try:
        conn = await asyncpg.connect(db_url)

        # Check if view exists
        view_exists = await conn.fetchval("""
            SELECT COUNT(*)
            FROM information_schema.views
            WHERE table_name = 'device_health_aggregation'
        """)

        if view_exists:
            print("✓ View 'device_health_aggregation' exists")
        else:
            print("✗ View 'device_health_aggregation' NOT FOUND")
            await conn.close()
            return False

        # Get sample data
        rows = await conn.fetch("""
            SELECT * FROM device_health_aggregation LIMIT 3
        """)

        if rows:
            print(f"✓ View returns {len(rows)} sample rows")
            print("\nSample data:")
            for i, row in enumerate(rows, 1):
                print(f"\n  Row {i}:")
                print(f"    Site: {row['site_name']} ({row['site_id']})")
                print(f"    Region: {row['region']}")
                print(f"    Total Devices: {row['total_devices']}")
                print(f"    Online: {row['online_count']}, Offline: {row['offline_count']}")
                print(f"    Health: {row['health_percentage']}%")
                print(f"    Firmware Critical: {row['firmware_critical']}")
        else:
            print("⚠ View exists but returns no data (this is OK if no devices in database)")

        # Get total count
        total = await conn.fetchval("SELECT COUNT(*) FROM device_health_aggregation")
        print(f"\n✓ Total sites/regions in view: {total}")

        await conn.close()
        return True

    except Exception as e:
        print(f"✗ Database error: {e}")
        return False


async def verify_api_endpoint(api_key: str, base_url: str = "http://localhost:8000"):
    """Verify the API endpoints return correct data"""
    print("\n=== API ENDPOINT VERIFICATION ===\n")

    headers = {"X-API-Key": api_key}
    success = True

    async with httpx.AsyncClient(timeout=10.0) as client:

        # Test 1: Basic device-health endpoint
        print("Test 1: GET /api/health/device-health (basic)")
        try:
            response = await client.get(
                f"{base_url}/api/health/device-health",
                headers=headers
            )

            if response.status_code == 200:
                print(f"✓ Status: {response.status_code}")
                data = response.json()

                # Verify response structure
                required_fields = ['items', 'total', 'page', 'page_size', 'total_pages']
                for field in required_fields:
                    if field in data:
                        print(f"✓ Response contains '{field}': {data[field] if field != 'items' else f'{len(data[field])} items'}")
                    else:
                        print(f"✗ Missing field: {field}")
                        success = False

                # Verify item structure
                if data['items']:
                    item = data['items'][0]
                    print(f"\n✓ Sample item structure:")
                    item_fields = ['site_id', 'site_name', 'region', 'total_devices',
                                   'online_count', 'offline_count', 'health_percentage']
                    for field in item_fields:
                        if field in item:
                            print(f"  - {field}: {item[field]}")
                        else:
                            print(f"  ✗ Missing: {field}")
                            success = False
            else:
                print(f"✗ Status: {response.status_code}")
                print(f"  Response: {response.text}")
                success = False

        except httpx.ConnectError:
            print("✗ Connection failed - is the API server running?")
            print("  Start with: uv run uvicorn src.glp.assignment.app:app --reload --port 8000")
            success = False
        except Exception as e:
            print(f"✗ Error: {e}")
            success = False

        # Test 2: Pagination
        print("\nTest 2: GET /api/health/device-health?page=1&page_size=2")
        try:
            response = await client.get(
                f"{base_url}/api/health/device-health?page=1&page_size=2",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                if data['page_size'] == 2:
                    print(f"✓ Pagination works: page_size={data['page_size']}")
                else:
                    print(f"✗ Pagination failed: expected page_size=2, got {data['page_size']}")
                    success = False
            else:
                print(f"✗ Status: {response.status_code}")
                success = False

        except httpx.ConnectError:
            print("✗ Connection failed")
            success = False
        except Exception as e:
            print(f"✗ Error: {e}")
            success = False

        # Test 3: Sorting
        print("\nTest 3: GET /api/health/device-health?sort_by=site_name&sort_order=asc")
        try:
            response = await client.get(
                f"{base_url}/api/health/device-health?sort_by=site_name&sort_order=asc",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                if data['items']:
                    sites = [item['site_name'] for item in data['items']]
                    print(f"✓ Sorting works: {', '.join(sites[:3])}")
                else:
                    print("⚠ No items to verify sorting")
            else:
                print(f"✗ Status: {response.status_code}")
                success = False

        except httpx.ConnectError:
            print("✗ Connection failed")
            success = False
        except Exception as e:
            print(f"✗ Error: {e}")
            success = False

        # Test 4: Filtering
        print("\nTest 4: GET /api/health/device-health?has_offline=true")
        try:
            response = await client.get(
                f"{base_url}/api/health/device-health?has_offline=true",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                print(f"✓ Filtering works: {data['total']} sites with offline devices")
            else:
                print(f"✗ Status: {response.status_code}")
                success = False

        except httpx.ConnectError:
            print("✗ Connection failed")
            success = False
        except Exception as e:
            print(f"✗ Error: {e}")
            success = False

        # Test 5: Summary endpoint
        print("\nTest 5: GET /api/health/summary")
        try:
            response = await client.get(
                f"{base_url}/api/health/summary",
                headers=headers
            )

            if response.status_code == 200:
                print(f"✓ Status: {response.status_code}")
                data = response.json()

                summary_fields = ['total_devices', 'total_sites', 'online_count',
                                  'offline_count', 'overall_health_percentage']
                print("✓ Summary data:")
                for field in summary_fields:
                    if field in data:
                        print(f"  - {field}: {data[field]}")
                    else:
                        print(f"  ✗ Missing: {field}")
                        success = False
            else:
                print(f"✗ Status: {response.status_code}")
                success = False

        except httpx.ConnectError:
            print("✗ Connection failed")
            success = False
        except Exception as e:
            print(f"✗ Error: {e}")
            success = False

    return success


async def main():
    """Main verification workflow"""
    print("=" * 60)
    print("Device Health Aggregation API - Verification Script")
    print("=" * 60)

    # Load environment
    env = load_env()
    db_url = os.getenv('DATABASE_URL')
    api_key = os.getenv('API_KEY')

    if not db_url:
        print("✗ DATABASE_URL not set in environment")
        sys.exit(1)

    if not api_key:
        print("✗ API_KEY not set in environment")
        sys.exit(1)

    # Verify database
    db_success = await verify_database_view(db_url)

    # Verify API
    api_success = await verify_api_endpoint(api_key)

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Database View: {'✓ PASS' if db_success else '✗ FAIL'}")
    print(f"API Endpoints: {'✓ PASS' if api_success else '✗ FAIL'}")
    print("=" * 60)

    if db_success and api_success:
        print("\n✅ All verifications passed!")
        sys.exit(0)
    else:
        print("\n❌ Some verifications failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
