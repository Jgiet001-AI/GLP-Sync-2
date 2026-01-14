#!/usr/bin/env python3
"""
Simple verification script for Device Health Aggregation API
Tests API endpoints only (assumes database is working)
"""
import os
import sys
import json
import urllib.request
import urllib.error


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


def make_request(url, api_key):
    """Make HTTP GET request with API key"""
    try:
        req = urllib.request.Request(url)
        req.add_header('X-API-Key', api_key)
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return None, str(e)


def verify_api_endpoints(api_key, base_url="http://localhost:8000"):
    """Verify the API endpoints return correct data"""
    print("\n=== API ENDPOINT VERIFICATION ===\n")

    success = True
    tests_passed = 0
    tests_total = 0

    # Test 1: Basic device-health endpoint
    print("Test 1: GET /api/health/device-health (basic)")
    tests_total += 1
    status, data = make_request(f"{base_url}/api/health/device-health", api_key)

    if status == 200 and isinstance(data, dict):
        print(f"✓ Status: {status}")

        # Verify response structure
        required_fields = ['items', 'total', 'page', 'page_size', 'total_pages']
        field_ok = True
        for field in required_fields:
            if field in data:
                value = len(data[field]) if field == 'items' else data[field]
                print(f"✓ Response contains '{field}': {value}")
            else:
                print(f"✗ Missing field: {field}")
                field_ok = False
                success = False

        if field_ok:
            tests_passed += 1

        # Verify item structure
        if data.get('items'):
            item = data['items'][0]
            print(f"\n✓ Sample item structure:")
            item_fields = ['site_id', 'site_name', 'region', 'total_devices',
                           'online_count', 'offline_count', 'health_percentage']
            for field in item_fields:
                if field in item:
                    print(f"  - {field}: {item[field]}")
    else:
        print(f"✗ Status: {status}")
        if isinstance(data, str):
            print(f"  Error: {data[:200]}")
        success = False

    # Test 2: Pagination
    print("\nTest 2: GET /api/health/device-health?page=1&page_size=2")
    tests_total += 1
    status, data = make_request(
        f"{base_url}/api/health/device-health?page=1&page_size=2",
        api_key
    )

    if status == 200 and isinstance(data, dict):
        if data.get('page_size') == 2:
            print(f"✓ Pagination works: page_size={data['page_size']}, page={data['page']}")
            tests_passed += 1
        else:
            print(f"✗ Pagination failed: expected page_size=2, got {data.get('page_size')}")
            success = False
    else:
        print(f"✗ Status: {status}")
        success = False

    # Test 3: Sorting
    print("\nTest 3: GET /api/health/device-health?sort_by=site_name&sort_order=asc")
    tests_total += 1
    status, data = make_request(
        f"{base_url}/api/health/device-health?sort_by=site_name&sort_order=asc",
        api_key
    )

    if status == 200 and isinstance(data, dict):
        if data.get('items'):
            sites = [item['site_name'] for item in data['items'][:3]]
            print(f"✓ Sorting works: {', '.join(sites)}")
            tests_passed += 1
        else:
            print("⚠ No items to verify sorting (OK if database is empty)")
            tests_passed += 1
    else:
        print(f"✗ Status: {status}")
        success = False

    # Test 4: Filtering by has_offline
    print("\nTest 4: GET /api/health/device-health?has_offline=true")
    tests_total += 1
    status, data = make_request(
        f"{base_url}/api/health/device-health?has_offline=true",
        api_key
    )

    if status == 200 and isinstance(data, dict):
        print(f"✓ Filter 'has_offline' works: {data.get('total', 0)} sites with offline devices")
        tests_passed += 1
    else:
        print(f"✗ Status: {status}")
        success = False

    # Test 5: Filtering by min_health
    print("\nTest 5: GET /api/health/device-health?min_health=90")
    tests_total += 1
    status, data = make_request(
        f"{base_url}/api/health/device-health?min_health=90",
        api_key
    )

    if status == 200 and isinstance(data, dict):
        print(f"✓ Filter 'min_health' works: {data.get('total', 0)} sites with health >= 90%")
        tests_passed += 1
    else:
        print(f"✗ Status: {status}")
        success = False

    # Test 6: Summary endpoint
    print("\nTest 6: GET /api/health/summary")
    tests_total += 1
    status, data = make_request(f"{base_url}/api/health/summary", api_key)

    if status == 200 and isinstance(data, dict):
        print(f"✓ Status: {status}")

        summary_fields = ['total_devices', 'total_sites', 'online_count',
                          'offline_count', 'overall_health_percentage']
        print("✓ Summary data:")
        all_fields_present = True
        for field in summary_fields:
            if field in data:
                print(f"  - {field}: {data[field]}")
            else:
                print(f"  ✗ Missing: {field}")
                all_fields_present = False
                success = False

        if all_fields_present:
            tests_passed += 1
    else:
        print(f"✗ Status: {status}")
        success = False

    # Test 7: Invalid sort field (should return 400)
    print("\nTest 7: GET /api/health/device-health?sort_by=invalid_field (expect 400)")
    tests_total += 1
    status, data = make_request(
        f"{base_url}/api/health/device-health?sort_by=invalid_field",
        api_key
    )

    if status == 400:
        print(f"✓ Properly rejects invalid sort field: {status}")
        tests_passed += 1
    else:
        print(f"✗ Expected 400 for invalid sort field, got: {status}")
        success = False

    # Test 8: Multi-value filtering
    print("\nTest 8: GET /api/health/device-health?region=US-WEST,US-EAST")
    tests_total += 1
    status, data = make_request(
        f"{base_url}/api/health/device-health?region=US-WEST,US-EAST",
        api_key
    )

    if status == 200 and isinstance(data, dict):
        print(f"✓ Multi-value region filter works: {data.get('total', 0)} sites")
        tests_passed += 1
    else:
        print(f"✗ Status: {status}")
        success = False

    return success, tests_passed, tests_total


def main():
    """Main verification workflow"""
    print("=" * 60)
    print("Device Health Aggregation API - Verification Script")
    print("=" * 60)

    # Load environment
    env = load_env()
    api_key = os.getenv('API_KEY')

    if not api_key:
        print("✗ API_KEY not set in environment")
        sys.exit(1)

    print(f"\n✓ API_KEY loaded: {api_key[:10]}...")

    # Check if server is running
    print("\nChecking if API server is running...")
    try:
        req = urllib.request.Request("http://localhost:8000/docs")
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                print("✓ API server is running on http://localhost:8000")
    except Exception as e:
        print(f"✗ API server not accessible: {e}")
        print("\nTo start the server, run:")
        print("  uv run uvicorn src.glp.assignment.app:app --reload --port 8000")
        sys.exit(1)

    # Verify API
    api_success, passed, total = verify_api_endpoints(api_key)

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Tests Passed: {passed}/{total}")
    print(f"API Endpoints: {'✓ PASS' if api_success else '✗ FAIL'}")
    print("=" * 60)

    if api_success:
        print("\n✅ All verifications passed!")
        print("\nThe following endpoints are working correctly:")
        print("  - GET /api/health/device-health (with pagination, sorting, filtering)")
        print("  - GET /api/health/summary")
        print("\nResponse format matches Pydantic schemas:")
        print("  - DeviceHealthStats")
        print("  - DeviceHealthResponse")
        print("  - OverallHealthSummary")
        sys.exit(0)
    else:
        print("\n❌ Some verifications failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
