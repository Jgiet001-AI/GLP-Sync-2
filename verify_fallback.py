#!/usr/bin/env python3
"""
Verification script for Voyage AI to OpenAI fallback behavior.
Tests that when EMBEDDING_PROVIDER=voyageai with invalid key, system falls back to OpenAI.
"""

import os
import sys
import logging
from io import StringIO

# Configure logging to capture all messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s',
    stream=sys.stdout
)

def test_fallback_with_invalid_key():
    """Test fallback when Voyage AI key is invalid"""
    print("=" * 80)
    print("TEST: Fallback from Voyage AI (invalid key) to OpenAI")
    print("=" * 80)

    # Set up environment for the test
    os.environ["EMBEDDING_PROVIDER"] = "voyageai"
    os.environ["VOYAGE_API_KEY"] = "invalid-key-12345"  # Invalid key
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "dummy-openai-key")  # Use real or dummy

    # Capture logs
    log_capture = StringIO()
    log_handler = logging.StreamHandler(log_capture)
    log_handler.setLevel(logging.DEBUG)

    # Get the root logger and add our handler
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    # Import after setting env vars
    from src.glp.assignment.app import _init_agent_orchestrator

    try:
        # Initialize the agent orchestrator (this should trigger fallback)
        _init_agent_orchestrator()

        # Get captured logs
        log_output = log_capture.getvalue()

        # Print all logs for visibility
        print("\n--- Captured Logs ---")
        print(log_output)
        print("--- End Logs ---\n")

        # Verify expected log messages
        success = True
        checks = []

        # Check 1: Should try Voyage AI first
        if "voyage" in log_output.lower() or "VOYAGE_API_KEY" in log_output:
            checks.append("✓ Attempted to use Voyage AI provider")
        else:
            checks.append("✗ Did NOT attempt Voyage AI provider")
            success = False

        # Check 2: Should log fallback
        if "falling back" in log_output.lower() or "fallback" in log_output.lower():
            checks.append("✓ Logged fallback to OpenAI")
        else:
            checks.append("✗ Did NOT log fallback")
            success = False

        # Check 3: Should end up using OpenAI
        if "Using OpenAI embedding provider" in log_output or "openai" in log_output.lower():
            checks.append("✓ Fell back to OpenAI provider")
        else:
            checks.append("✗ Did NOT fall back to OpenAI")
            success = False

        # Print results
        print("\n--- Verification Results ---")
        for check in checks:
            print(check)

        if success:
            print("\n✓ SUCCESS: Fallback behavior verified correctly")
            return 0
        else:
            print("\n✗ FAILURE: Some checks failed")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR during test: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Clean up
        root_logger.removeHandler(log_handler)
        log_capture.close()


def test_fallback_with_missing_key():
    """Test fallback when Voyage AI key is missing"""
    print("\n" + "=" * 80)
    print("TEST: Fallback from Voyage AI (missing key) to OpenAI")
    print("=" * 80)

    # Set up environment for the test
    os.environ["EMBEDDING_PROVIDER"] = "voyageai"
    if "VOYAGE_API_KEY" in os.environ:
        del os.environ["VOYAGE_API_KEY"]  # Remove key
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "dummy-openai-key")

    # Capture logs
    log_capture = StringIO()
    log_handler = logging.StreamHandler(log_capture)
    log_handler.setLevel(logging.DEBUG)

    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    # Need to reload the module to pick up new env vars
    import importlib
    import src.glp.assignment.app as app_module
    importlib.reload(app_module)

    try:
        # Initialize the agent orchestrator
        app_module._init_agent_orchestrator()

        # Get captured logs
        log_output = log_capture.getvalue()

        # Print all logs for visibility
        print("\n--- Captured Logs ---")
        print(log_output)
        print("--- End Logs ---\n")

        # Verify expected log messages
        success = True
        checks = []

        # Check 1: Should mention missing VOYAGE_API_KEY
        if "VOYAGE_API_KEY not configured" in log_output:
            checks.append("✓ Detected missing VOYAGE_API_KEY")
        else:
            checks.append("✗ Did NOT detect missing VOYAGE_API_KEY")
            success = False

        # Check 2: Should log fallback
        if "falling back" in log_output.lower():
            checks.append("✓ Logged fallback to OpenAI")
        else:
            checks.append("✗ Did NOT log fallback")
            success = False

        # Check 3: Should end up using OpenAI
        if "Using OpenAI embedding provider" in log_output:
            checks.append("✓ Fell back to OpenAI provider")
        else:
            checks.append("✗ Did NOT fall back to OpenAI")
            success = False

        # Print results
        print("\n--- Verification Results ---")
        for check in checks:
            print(check)

        if success:
            print("\n✓ SUCCESS: Fallback behavior verified correctly")
            return 0
        else:
            print("\n✗ FAILURE: Some checks failed")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR during test: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Clean up
        root_logger.removeHandler(log_handler)
        log_capture.close()


if __name__ == "__main__":
    print("Voyage AI to OpenAI Fallback Verification")
    print("=" * 80)

    # Run both tests
    result1 = test_fallback_with_invalid_key()
    result2 = test_fallback_with_missing_key()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Test 1 (Invalid Key): {'PASS' if result1 == 0 else 'FAIL'}")
    print(f"Test 2 (Missing Key): {'PASS' if result2 == 0 else 'FAIL'}")

    if result1 == 0 and result2 == 0:
        print("\n✓ All fallback tests PASSED")
        sys.exit(0)
    else:
        print("\n✗ Some fallback tests FAILED")
        sys.exit(1)
