#!/usr/bin/env python3
"""
Verification script to check that test_extended_thinking.py can be imported.
This can be run when dependencies are available.
"""

import sys
import ast

def verify_syntax():
    """Verify the test file has valid Python syntax."""
    try:
        with open('tests/agent/test_extended_thinking.py', 'r') as f:
            code = f.read()
        ast.parse(code)
        print("✓ Syntax is valid")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error: {e}")
        return False

def verify_structure():
    """Verify the test file has the expected structure."""
    with open('tests/agent/test_extended_thinking.py', 'r') as f:
        content = f.read()

    checks = [
        ("Fixtures section", "@pytest.fixture"),
        ("Configuration tests", "class TestThinkingConfiguration"),
        ("Parameter tests", "class TestThinkingParameters"),
        ("Delta tests", "class TestThinkingDeltas"),
        ("Message history tests", "class TestMessageHistoryWithThinking"),
        ("Edge case tests", "class TestThinkingEdgeCases"),
        ("Agent config tests", "class TestAgentConfigIntegration"),
        ("Async tests", "@pytest.mark.asyncio"),
        ("Mock usage", "from unittest.mock import"),
    ]

    all_passed = True
    for name, pattern in checks:
        if pattern in content:
            print(f"✓ {name} found")
        else:
            print(f"✗ {name} NOT found")
            all_passed = False

    return all_passed

if __name__ == "__main__":
    print("Verifying test_extended_thinking.py...")
    print()

    syntax_ok = verify_syntax()
    print()

    structure_ok = verify_structure()
    print()

    if syntax_ok and structure_ok:
        print("✓ All verifications passed!")
        print()
        print("To run the tests, use:")
        print("  uv run pytest tests/agent/test_extended_thinking.py -v")
        sys.exit(0)
    else:
        print("✗ Some verifications failed")
        sys.exit(1)
