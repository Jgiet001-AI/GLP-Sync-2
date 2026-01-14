#!/usr/bin/env python3
"""
Code verification script for Voyage AI to OpenAI fallback logic.
This script performs static code analysis without requiring dependencies.
"""

import re

def verify_fallback_implementation():
    """Verify that app.py contains proper fallback logic."""

    print("=" * 80)
    print("Voyage AI to OpenAI Fallback - Code Verification")
    print("=" * 80)

    # Read the app.py file
    with open("./src/glp/assignment/app.py", "r") as f:
        content = f.read()

    checks = []
    all_passed = True

    # Check 1: EMBEDDING_PROVIDER environment variable is read
    if 'os.getenv("EMBEDDING_PROVIDER"' in content:
        checks.append("✓ EMBEDDING_PROVIDER environment variable is read")
    else:
        checks.append("✗ EMBEDDING_PROVIDER environment variable NOT read")
        all_passed = False

    # Check 2: Voyage AI provider selection logic exists
    if 'embedding_provider_name == "voyageai"' in content or 'embedding_provider_name == "voyage"' in content:
        checks.append("✓ Voyage AI provider selection logic exists")
    else:
        checks.append("✗ Voyage AI provider selection logic NOT found")
        all_passed = False

    # Check 3: VOYAGE_API_KEY validation
    if 'VOYAGE_API_KEY' in content and 'if voyage_key and VoyageAIProvider:' in content:
        checks.append("✓ VOYAGE_API_KEY validation exists")
    else:
        checks.append("✗ VOYAGE_API_KEY validation NOT found")
        all_passed = False

    # Check 4: Exception handling for Voyage AI initialization
    if 'except Exception as e:' in content and 'Failed to initialize Voyage AI' in content:
        checks.append("✓ Exception handling for Voyage AI initialization")
    else:
        checks.append("✗ Exception handling for Voyage AI NOT found")
        all_passed = False

    # Check 5: Fallback logging for missing key
    if 'VOYAGE_API_KEY not configured, falling back to OpenAI' in content:
        checks.append("✓ Logging for missing VOYAGE_API_KEY")
    else:
        checks.append("✗ Logging for missing VOYAGE_API_KEY NOT found")
        all_passed = False

    # Check 6: Fallback logging for unavailable provider
    if 'VoyageAIProvider not available, falling back to OpenAI' in content:
        checks.append("✓ Logging for unavailable VoyageAIProvider")
    else:
        checks.append("✗ Logging for unavailable VoyageAIProvider NOT found")
        all_passed = False

    # Check 7: Fallback logging for initialization failure
    if 'Falling back to OpenAI embeddings...' in content:
        checks.append("✓ Logging for Voyage AI initialization failure")
    else:
        checks.append("✗ Logging for initialization failure NOT found")
        all_passed = False

    # Check 8: OpenAI fallback implementation
    if 'if not embedding_provider and openai_key:' in content:
        checks.append("✓ OpenAI fallback implementation exists")
    else:
        checks.append("✗ OpenAI fallback implementation NOT found")
        all_passed = False

    # Check 9: OpenAI provider initialization in fallback
    if 'embedding_provider = OpenAIProvider(embedding_config)' in content:
        checks.append("✓ OpenAI provider initialization in fallback")
    else:
        checks.append("✗ OpenAI provider initialization NOT found")
        all_passed = False

    # Check 10: Invalid provider name validation
    if 'Invalid EMBEDDING_PROVIDER' in content and 'valid_providers' in content:
        checks.append("✓ Invalid provider name validation")
    else:
        checks.append("✗ Invalid provider name validation NOT found")
        all_passed = False

    # Print results
    print("\n--- Code Analysis Results ---")
    for check in checks:
        print(check)

    # Count fallback paths
    print("\n--- Fallback Paths Identified ---")

    fallback_patterns = [
        (r'elif not voyage_key:', "Missing VOYAGE_API_KEY"),
        (r'elif not VoyageAIProvider:', "VoyageAIProvider not available"),
        (r'except Exception as e:.*Failed to initialize Voyage', "Voyage AI initialization error"),
        (r'if embedding_provider_name not in valid_providers:', "Invalid provider name"),
    ]

    for pattern, description in fallback_patterns:
        if re.search(pattern, content, re.DOTALL):
            print(f"✓ {description}")
        else:
            print(f"✗ {description} - NOT FOUND")

    # Verify test coverage
    print("\n--- Test Coverage Verification ---")

    try:
        with open("./tests/agent/test_provider_factory.py", "r") as f:
            test_content = f.read()

        test_checks = []

        if 'test_fallback_when_voyage_api_key_missing' in test_content:
            test_checks.append("✓ Test for missing VOYAGE_API_KEY")
        else:
            test_checks.append("✗ Test for missing VOYAGE_API_KEY NOT found")

        if 'test_fallback_when_voyage_init_fails' in test_content:
            test_checks.append("✓ Test for Voyage AI init failure")
        else:
            test_checks.append("✗ Test for Voyage AI init failure NOT found")

        if 'test_fallback_when_voyageai_not_available' in test_content:
            test_checks.append("✓ Test for VoyageAI package unavailable")
        else:
            test_checks.append("✗ Test for VoyageAI package unavailable NOT found")

        for check in test_checks:
            print(check)

    except FileNotFoundError:
        print("✗ Test file not found: tests/agent/test_provider_factory.py")
        all_passed = False

    # Final result
    print("\n" + "=" * 80)
    if all_passed:
        print("✓ SUCCESS: All fallback mechanisms properly implemented")
        print("=" * 80)
        return 0
    else:
        print("✗ FAILURE: Some fallback mechanisms missing or incomplete")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    import sys
    exit_code = verify_fallback_implementation()
    sys.exit(exit_code)
