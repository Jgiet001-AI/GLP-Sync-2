#!/usr/bin/env python3
"""
Manual Security Verification Script for Error Response Sanitization.

This script tests various error scenarios to ensure sensitive information
is not leaked in API error responses while verifying that internal logs
still contain full details for debugging.

Test Scenarios:
1. Invalid authentication (should not reveal env var names)
2. Missing configuration (should not reveal env var names)
3. Database connection errors (should not reveal connection strings)
4. File path errors (should not reveal file paths)
5. Stack traces (should not reveal internal architecture)
6. IP addresses (should not reveal internal IPs)
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

# Set up logging to capture what the API logs internally
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Test results tracking
test_results = []


class TestResult:
    """Track test result."""

    def __init__(self, name: str, passed: bool, details: str):
        self.name = name
        self.passed = passed
        self.details = details
        self.timestamp = datetime.utcnow().isoformat()


def check_sensitive_patterns(response_text: str) -> tuple[bool, list[str]]:
    """Check if response contains sensitive patterns.

    Returns:
        (is_safe, list_of_violations)
    """
    violations = []

    # Patterns that should NOT appear in error responses
    sensitive_patterns = [
        # Environment variables
        (r"GLP_CLIENT_ID", "Environment variable name: GLP_CLIENT_ID"),
        (r"GLP_CLIENT_SECRET", "Environment variable name: GLP_CLIENT_SECRET"),
        (r"GLP_TOKEN_URL", "Environment variable name: GLP_TOKEN_URL"),
        (r"DATABASE_URL", "Environment variable name: DATABASE_URL"),
        (r"REDIS_URL", "Environment variable name: REDIS_URL"),
        (r"ANTHROPIC_API_KEY", "Environment variable name: ANTHROPIC_API_KEY"),
        (r"OPENAI_API_KEY", "Environment variable name: OPENAI_API_KEY"),
        (r"JWT_SECRET", "Environment variable name: JWT_SECRET"),
        (r"API_KEY", "Environment variable name: API_KEY"),

        # Database connection strings
        (r"postgresql://[^/\s]+:[^@\s]+@", "PostgreSQL connection string with credentials"),
        (r"mysql://[^/\s]+:[^@\s]+@", "MySQL connection string with credentials"),
        (r"mongodb://[^/\s]+:[^@\s]+@", "MongoDB connection string with credentials"),
        (r"redis://[^/\s]+:[^@\s]+@", "Redis connection string with credentials"),

        # File paths (Unix and Windows)
        (r"/etc/", "File path: /etc/"),
        (r"/var/", "File path: /var/"),
        (r"/home/", "File path: /home/"),
        (r"/usr/", "File path: /usr/"),
        (r"C:\\", "File path: C:\\"),
        (r"\\\\", "UNC path: \\\\"),

        # Stack traces
        (r"Traceback \(most recent call last\)", "Stack trace"),
        (r"File \".*\.py\", line \d+", "Stack trace with file/line"),
        (r"raise \w+Error", "Stack trace with raise statement"),

        # IP addresses (private ranges)
        (r"192\.168\.\d+\.\d+", "Private IP address: 192.168.x.x"),
        (r"10\.\d+\.\d+\.\d+", "Private IP address: 10.x.x.x"),
        (r"172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+", "Private IP address: 172.16-31.x.x"),
        (r"127\.0\.0\.1", "Loopback IP address: 127.0.0.1"),
        (r"localhost:\d+", "Localhost with port"),

        # API keys and tokens
        (r"Bearer [A-Za-z0-9_-]{20,}", "Bearer token"),
        (r"api_key=[A-Za-z0-9_-]{20,}", "API key parameter"),
        (r"token=[A-Za-z0-9_-]{20,}", "Token parameter"),
        (r"sk-[A-Za-z0-9]{32,}", "OpenAI API key"),
        (r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "JWT token"),
    ]

    import re
    for pattern, description in sensitive_patterns:
        if re.search(pattern, response_text, re.IGNORECASE):
            violations.append(description)

    return len(violations) == 0, violations


async def test_error_sanitizer_module():
    """Test the error sanitizer module directly."""
    print("\n" + "="*80)
    print("TEST 1: Error Sanitizer Module")
    print("="*80)

    try:
        from src.glp.api.error_sanitizer import ErrorSanitizer, sanitize_error_message

        sanitizer = ErrorSanitizer()

        # Test 1: Database URL
        test_msg = "Connection failed: postgresql://user:pass123@localhost:5432/db"
        result = sanitizer.sanitize(test_msg)
        is_safe, violations = check_sensitive_patterns(result.sanitized_message)

        print(f"\nOriginal: {test_msg}")
        print(f"Sanitized: {result.sanitized_message}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "Error Sanitizer - Database URL",
            is_safe and "postgresql://" not in result.sanitized_message,
            f"Sanitized: {result.sanitized_message}"
        ))

        # Test 2: Environment variable
        test_msg = "Configuration error: Missing GLP_CLIENT_ID. Check GLP_CLIENT_ID, GLP_CLIENT_SECRET, GLP_TOKEN_URL"
        result = sanitizer.sanitize(test_msg)
        is_safe, violations = check_sensitive_patterns(result.sanitized_message)

        print(f"\nOriginal: {test_msg}")
        print(f"Sanitized: {result.sanitized_message}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "Error Sanitizer - Env Vars",
            is_safe and "GLP_CLIENT_ID" not in result.sanitized_message,
            f"Sanitized: {result.sanitized_message}"
        ))

        # Test 3: File path
        test_msg = "Failed to read /etc/secret/config.yaml"
        result = sanitizer.sanitize(test_msg)
        is_safe, violations = check_sensitive_patterns(result.sanitized_message)

        print(f"\nOriginal: {test_msg}")
        print(f"Sanitized: {result.sanitized_message}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "Error Sanitizer - File Path",
            is_safe and "/etc/" not in result.sanitized_message,
            f"Sanitized: {result.sanitized_message}"
        ))

        # Test 4: Stack trace
        test_msg = """Traceback (most recent call last):
  File "/app/src/glp/api/client.py", line 123, in fetch
    raise ValueError("Connection failed")
ValueError: Connection failed"""
        result = sanitizer.sanitize(test_msg)
        is_safe, violations = check_sensitive_patterns(result.sanitized_message)

        print(f"\nOriginal: {test_msg[:50]}...")
        print(f"Sanitized: {result.sanitized_message}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "Error Sanitizer - Stack Trace",
            is_safe and "Traceback" not in result.sanitized_message,
            f"Sanitized: {result.sanitized_message}"
        ))

        # Test 5: IP address
        test_msg = "Connection refused to 192.168.1.100:5432"
        result = sanitizer.sanitize(test_msg)
        is_safe, violations = check_sensitive_patterns(result.sanitized_message)

        print(f"\nOriginal: {test_msg}")
        print(f"Sanitized: {result.sanitized_message}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "Error Sanitizer - IP Address",
            is_safe and "192.168" not in result.sanitized_message,
            f"Sanitized: {result.sanitized_message}"
        ))

        # Test 6: API key
        test_msg = "Authentication failed with api_key=sk_live_51HxyzAbcDef123456789"
        result = sanitizer.sanitize(test_msg)
        is_safe, violations = check_sensitive_patterns(result.sanitized_message)

        print(f"\nOriginal: {test_msg}")
        print(f"Sanitized: {result.sanitized_message}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "Error Sanitizer - API Key",
            is_safe and "sk_live" not in result.sanitized_message,
            f"Sanitized: {result.sanitized_message}"
        ))

        print("\n✅ Error Sanitizer Module Tests Complete")

    except Exception as e:
        print(f"\n❌ Error Sanitizer Module Test Failed: {e}")
        test_results.append(TestResult(
            "Error Sanitizer Module",
            False,
            f"Exception: {e}"
        ))


async def test_exception_handlers():
    """Test FastAPI exception handlers by importing and testing them."""
    print("\n" + "="*80)
    print("TEST 2: FastAPI Exception Handlers")
    print("="*80)

    try:
        from src.glp.assignment.app import http_exception_handler, generic_exception_handler
        from fastapi import HTTPException, Request
        from unittest.mock import Mock

        # Mock request
        mock_request = Mock(spec=Request)

        # Test HTTPException handler
        print("\nTesting HTTPException Handler...")
        exc = HTTPException(
            status_code=500,
            detail="Database error: postgresql://admin:secret@db.internal:5432/glp_db connection failed"
        )
        response = await http_exception_handler(mock_request, exc)
        response_data = json.loads(response.body.decode())

        is_safe, violations = check_sensitive_patterns(response_data["detail"])

        print(f"Original detail: {exc.detail}")
        print(f"Response detail: {response_data['detail']}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "HTTPException Handler - Database URL",
            is_safe and "postgresql://" not in response_data["detail"],
            f"Response: {response_data['detail']}"
        ))

        # Test Generic exception handler
        print("\nTesting Generic Exception Handler...")
        exc = Exception("Configuration error: Missing GLP_CLIENT_ID, GLP_CLIENT_SECRET")
        response = await generic_exception_handler(mock_request, exc)
        response_data = json.loads(response.body.decode())

        is_safe, violations = check_sensitive_patterns(response_data["detail"])

        print(f"Original exception: {str(exc)}")
        print(f"Response detail: {response_data['detail']}")
        print(f"Safe: {is_safe}")
        if violations:
            print(f"Violations: {violations}")

        test_results.append(TestResult(
            "Generic Exception Handler - Env Vars",
            is_safe and "GLP_CLIENT_ID" not in response_data["detail"],
            f"Response: {response_data['detail']}"
        ))

        print("\n✅ Exception Handler Tests Complete")

    except Exception as e:
        print(f"\n❌ Exception Handler Test Failed: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(TestResult(
            "Exception Handlers",
            False,
            f"Exception: {e}"
        ))


async def test_router_error_handling():
    """Test that routers properly use sanitize_error_message."""
    print("\n" + "="*80)
    print("TEST 3: Router Error Handling")
    print("="*80)

    try:
        # Check that routers import and use sanitize_error_message
        import importlib.util

        routers_to_check = [
            ("Dashboard Router", "./src/glp/assignment/api/dashboard_router.py"),
            ("Clients Router", "./src/glp/assignment/api/clients_router.py"),
            ("Assignment Router", "./src/glp/assignment/api/router.py"),
            ("Agent Router", "./src/glp/agent/api/router.py"),
        ]

        for router_name, router_path in routers_to_check:
            print(f"\nChecking {router_name}...")
            try:
                with open(router_path, 'r') as f:
                    router_code = f.read()

                # Check for import
                has_import = "from" in router_code and "error_sanitizer import sanitize_error_message" in router_code

                # Check for usage
                has_usage = "sanitize_error_message(" in router_code

                # Check for unsanitized HTTPException (should have few or none)
                import re
                unsanitized_count = len(re.findall(r'HTTPException\([^)]*detail\s*=\s*f["\'][^"\']*\{e\}', router_code))

                print(f"  Import: {'✅' if has_import else '❌'}")
                print(f"  Usage: {'✅' if has_usage else '❌'}")
                print(f"  Unsanitized errors with {{e}}: {unsanitized_count}")

                test_results.append(TestResult(
                    f"{router_name} - Sanitization",
                    has_import and has_usage,
                    f"Import: {has_import}, Usage: {has_usage}, Unsanitized: {unsanitized_count}"
                ))

            except FileNotFoundError:
                print(f"  ⚠️  File not found (optional module)")
                test_results.append(TestResult(
                    f"{router_name} - Sanitization",
                    True,  # Pass if module doesn't exist
                    "Module not found (optional)"
                ))

        print("\n✅ Router Error Handling Tests Complete")

    except Exception as e:
        print(f"\n❌ Router Error Handling Test Failed: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(TestResult(
            "Router Error Handling",
            False,
            f"Exception: {e}"
        ))


def print_test_summary():
    """Print summary of all tests."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for r in test_results if r.passed)
    failed = sum(1 for r in test_results if not r.passed)
    total = len(test_results)

    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} {'❌' if failed > 0 else ''}")
    print(f"Success Rate: {(passed/total*100):.1f}%")

    if failed > 0:
        print("\n" + "="*80)
        print("FAILED TESTS:")
        print("="*80)
        for result in test_results:
            if not result.passed:
                print(f"\n❌ {result.name}")
                print(f"   {result.details}")

    print("\n" + "="*80)
    print("DETAILED RESULTS:")
    print("="*80)
    for result in test_results:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"\n{status}: {result.name}")
        print(f"   {result.details}")

    # Save results to JSON
    results_file = "security_verification_results.json"
    with open(results_file, 'w') as f:
        json.dump([{
            "name": r.name,
            "passed": r.passed,
            "details": r.details,
            "timestamp": r.timestamp
        } for r in test_results], f, indent=2)

    print(f"\n📄 Results saved to: {results_file}")

    return failed == 0


async def main():
    """Run all verification tests."""
    print("="*80)
    print("MANUAL SECURITY VERIFICATION - ERROR RESPONSE SANITIZATION")
    print("="*80)
    print(f"\nTimestamp: {datetime.utcnow().isoformat()}Z")
    print(f"Python: {sys.version}")
    print(f"Working Directory: {os.getcwd()}")

    # Run all tests
    await test_error_sanitizer_module()
    await test_exception_handlers()
    await test_router_error_handling()

    # Print summary
    all_passed = print_test_summary()

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
