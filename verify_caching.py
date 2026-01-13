#!/usr/bin/env python3
"""
Verification script for HTTP caching headers on dashboard endpoints.

This script verifies that:
1. /api/dashboard/filters returns Cache-Control: public, max-age=300
2. /api/dashboard returns Cache-Control: public, max-age=30
"""

import asyncio
import sys
from datetime import datetime

import httpx


async def verify_endpoint(client: httpx.AsyncClient, endpoint: str, expected_max_age: int, description: str):
    """Verify Cache-Control header on an endpoint."""
    print(f"\n{'='*70}")
    print(f"Testing: {description}")
    print(f"Endpoint: {endpoint}")
    print(f"Expected: Cache-Control: public, max-age={expected_max_age}")
    print('-'*70)

    try:
        response = await client.get(endpoint, headers={"X-API-Key": "test"})

        print(f"Status: {response.status_code}")

        cache_control = response.headers.get("Cache-Control")
        if cache_control:
            print(f"✓ Cache-Control header found: {cache_control}")

            expected_value = f"public, max-age={expected_max_age}"
            if cache_control == expected_value:
                print(f"✓ Cache-Control matches expected value")
                return True
            else:
                print(f"✗ Cache-Control does not match expected value")
                print(f"  Expected: {expected_value}")
                print(f"  Got:      {cache_control}")
                return False
        else:
            print("✗ Cache-Control header NOT found")
            print("Available headers:")
            for key, value in response.headers.items():
                print(f"  {key}: {value}")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def main():
    """Main verification function."""
    print("="*70)
    print("HTTP CACHING VERIFICATION")
    print("="*70)
    print(f"Time: {datetime.now().isoformat()}")

    base_url = "http://localhost:8000"

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        # Test 1: Filter options endpoint (5 minute cache)
        test1 = await verify_endpoint(
            client,
            "/api/dashboard/filters",
            300,
            "Filter Options Endpoint (5 minute cache)"
        )

        # Test 2: Dashboard endpoint (30 second cache)
        test2 = await verify_endpoint(
            client,
            "/api/dashboard?expiring_days=90",
            30,
            "Dashboard Endpoint (30 second cache)"
        )

        # Summary
        print(f"\n{'='*70}")
        print("VERIFICATION SUMMARY")
        print('='*70)
        print(f"Filter Options (/api/dashboard/filters): {'✓ PASS' if test1 else '✗ FAIL'}")
        print(f"Dashboard (/api/dashboard):              {'✓ PASS' if test2 else '✗ FAIL'}")
        print('='*70)

        if test1 and test2:
            print("✓ All tests passed!")
            return 0
        else:
            print("✗ Some tests failed")
            return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
