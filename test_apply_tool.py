#!/usr/bin/env python3
"""
Simple test to verify the apply_device_assignments tool is properly registered.
"""

import sys
sys.path.insert(0, '.')

def test_tool_registration():
    """Test that the tool is registered with FastMCP."""
    from server import mcp

    # Check if the tool manager has our tool
    if hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, '_tools'):
        tools = mcp._tool_manager._tools

        if 'apply_device_assignments' not in tools:
            print("❌ FAILED: apply_device_assignments tool not found")
            print(f"   Available tools: {list(tools.keys())[:5]}...")
            return False

        tool = tools['apply_device_assignments']

        # Verify tool properties
        print("✓ Tool registered successfully")
        print(f"  Name: apply_device_assignments")
        print(f"  Total tools: {len(tools)}")
        print(f"  Has description: {bool(tool.description)}")
        print(f"  Has function: {bool(tool.fn)}")

        # Check annotations
        if hasattr(tool, 'annotations'):
            print(f"  Annotations: {tool.annotations}")
            if hasattr(tool.annotations, 'readOnlyHint'):
                if tool.annotations.readOnlyHint == False:
                    print("  ✓ Correctly marked as write tool (readOnlyHint=False)")
                else:
                    print("  ⚠️  WARNING: Should be readOnlyHint=False for write tool")

        return True
    else:
        print("❌ FAILED: Tool manager not accessible")
        return False


def test_tool_signature():
    """Test that the tool has the correct signature."""
    from server import apply_device_assignments
    import inspect

    sig = inspect.signature(apply_device_assignments)
    params = list(sig.parameters.keys())

    print("\n✓ Tool signature:")
    print(f"  Parameters: {params}")

    expected_params = ['ctx', 'assignments', 'wait_for_completion']
    if params == expected_params:
        print("  ✓ Parameters match expected signature")
        return True
    else:
        print(f"  ❌ FAILED: Expected {expected_params}, got {params}")
        return False


if __name__ == "__main__":
    print("Testing apply_device_assignments MCP tool\n")
    print("=" * 60)

    success = True

    # Test 1: Tool registration
    print("\n[Test 1] Tool Registration")
    if not test_tool_registration():
        success = False

    # Test 2: Tool signature
    print("\n[Test 2] Tool Signature")
    if not test_tool_signature():
        success = False

    print("\n" + "=" * 60)
    if success:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)
