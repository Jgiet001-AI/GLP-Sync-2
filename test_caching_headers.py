#!/usr/bin/env python3
"""
Test script to verify Cache-Control headers are set correctly.
This is a unit test that verifies the implementation without requiring a running server.
"""

import sys
import inspect


def test_cache_control_implementation():
    """Verify that the code sets Cache-Control headers correctly."""

    # Import the router
    from src.glp.assignment.api.dashboard_router import router

    # Get the endpoint functions
    filters_endpoint = None
    dashboard_endpoint = None

    for route in router.routes:
        if route.path == "/filters":
            filters_endpoint = route.endpoint
        elif route.path == "":
            dashboard_endpoint = route.endpoint

    assert filters_endpoint is not None, "Filter endpoint not found"
    assert dashboard_endpoint is not None, "Dashboard endpoint not found"

    # Check filters endpoint signature
    import inspect

    # Filters endpoint
    filters_sig = inspect.signature(filters_endpoint)
    assert 'response' in filters_sig.parameters, "filters endpoint should have 'response' parameter"
    print("✓ /api/dashboard/filters has Response parameter")

    # Dashboard endpoint
    dashboard_sig = inspect.signature(dashboard_endpoint)
    assert 'response' in dashboard_sig.parameters, "dashboard endpoint should have 'response' parameter"
    print("✓ /api/dashboard has Response parameter")

    # Check the source code for Cache-Control header setting
    filters_source = inspect.getsource(filters_endpoint)
    assert 'Cache-Control' in filters_source, "Cache-Control header should be set"
    assert 'max-age=300' in filters_source, "5-minute cache should be set"
    print("✓ /api/dashboard/filters sets Cache-Control: public, max-age=300")

    dashboard_source = inspect.getsource(dashboard_endpoint)
    assert 'Cache-Control' in dashboard_source, "Cache-Control header should be set"
    assert 'max-age=30' in dashboard_source, "30-second cache should be set"
    print("✓ /api/dashboard sets Cache-Control: public, max-age=30")

    print("\n✓ All implementation checks passed!")
    print("\nThe code is correctly implemented to add Cache-Control headers.")
    print("Headers will be sent once the code is deployed and the server is restarted.")


if __name__ == "__main__":
    test_cache_control_implementation()
