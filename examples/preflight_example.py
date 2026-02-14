"""Example: Using VenomQA preflight smoke tests.

This example shows how to run quick validation checks against an API
before investing time in full test suites. The smoke test catches
common showstoppers like:

- Server not running
- Authentication broken (JWT user missing from DB)
- Database FK violations on basic operations
- Endpoints returning 500 errors

Usage:
    python examples/preflight_example.py

    # With a real server:
    API_URL=http://localhost:8000 API_TOKEN=eyJ... python examples/preflight_example.py
"""

from __future__ import annotations

import os
import sys


def basic_smoke_test() -> None:
    """Run a basic smoke test with explicit configuration."""
    from venomqa.preflight import SmokeTest, APINotReadyError

    base_url = os.environ.get("API_URL", "http://localhost:8000")
    token = os.environ.get("API_TOKEN")

    print(f"Running smoke test against {base_url}")
    print()

    smoke = SmokeTest(base_url, token=token)

    # Run all checks and get a report
    report = smoke.run_all(
        health_path="/health",
        auth_path="/api/v1/workspaces",
        create_path="/api/v1/items",
        create_payload={"name": "smoke-test-item", "description": "Created by preflight"},
        list_path="/api/v1/items",
    )

    # Print a formatted report
    report.print_report()

    # Inspect individual results
    for result in report.results:
        if not result.passed:
            print(f"  FAILED: {result.name}")
            print(f"    Status: {result.status_code}")
            print(f"    Error:  {result.error}")
            if result.suggestion:
                print(f"    Fix:    {result.suggestion}")
            print()


def assert_ready_example() -> None:
    """Use assert_ready() to gate a test suite."""
    from venomqa.preflight import SmokeTest, APINotReadyError

    base_url = os.environ.get("API_URL", "http://localhost:8000")
    token = os.environ.get("API_TOKEN")

    smoke = SmokeTest(base_url, token=token)

    try:
        smoke.assert_ready()
        print("API is ready! Proceeding with full test suite...")
    except APINotReadyError as e:
        print(f"API not ready: {e.report.summary}")
        print()
        for result in e.report.results:
            if not result.passed:
                print(f"  - {result.name}: {result.error}")
                if result.suggestion:
                    print(f"    Suggestion: {result.suggestion}")
        sys.exit(1)


def auto_discovery_example() -> None:
    """Use AutoPreflight to discover checks from an OpenAPI spec."""
    from venomqa.preflight import AutoPreflight

    base_url = os.environ.get("API_URL", "http://localhost:8000")
    token = os.environ.get("API_TOKEN")
    spec_url = f"{base_url}/openapi.json"

    print(f"Auto-discovering checks from {spec_url}")
    print()

    try:
        auto = AutoPreflight.from_openapi(spec_url, token=token)

        # Show what was discovered
        health_eps = auto.discover_health_endpoints()
        print(f"Found {len(health_eps)} health endpoint(s): {health_eps}")

        crud_eps = auto.discover_crud_endpoints()
        print(f"Found {len(crud_eps)} CRUD endpoint(s)")
        for path, method, payload in crud_eps[:5]:
            print(f"  {method.upper()} {path} -> {payload}")

        list_eps = auto.discover_list_endpoints()
        print(f"Found {len(list_eps)} list endpoint(s): {list_eps[:5]}")
        print()

        # Run all discovered checks
        report = auto.run()
        report.print_report()

    except Exception as e:
        print(f"Could not auto-discover: {e}")
        print("Falling back to manual smoke test...")
        basic_smoke_test()


def individual_checks_example() -> None:
    """Run individual checks for fine-grained control."""
    from venomqa.preflight import SmokeTest

    base_url = os.environ.get("API_URL", "http://localhost:8000")
    token = os.environ.get("API_TOKEN")

    smoke = SmokeTest(base_url, token=token)

    # Run checks one at a time
    health = smoke.check_health("/health")
    print(f"Health: {'PASS' if health.passed else 'FAIL'} ({health.duration_ms:.0f}ms)")

    if token:
        auth = smoke.check_auth("/api/v1/workspaces")
        print(f"Auth:   {'PASS' if auth.passed else 'FAIL'} ({auth.duration_ms:.0f}ms)")
        if not auth.passed and auth.status_code == 500:
            print("  The JWT user likely doesn't exist in the database!")
            print(f"  Suggestion: {auth.suggestion}")


def conftest_integration_example() -> None:
    """Example of how to use preflight in a pytest conftest.py.

    This function is not meant to be run directly -- it shows what
    you would put in your conftest.py file.
    """
    print("Example conftest.py integration:")
    print()
    print('''
# conftest.py
import pytest
from venomqa.preflight import SmokeTest, APINotReadyError

@pytest.fixture(scope="session", autouse=True)
def preflight_check():
    """Fail the entire test session early if the API is broken."""
    smoke = SmokeTest(
        base_url="http://localhost:8000",
        token=os.environ.get("API_TOKEN"),
    )
    try:
        report = smoke.assert_ready(
            health_path="/health",
            auth_path="/api/v1/workspaces",
        )
        print(f"Preflight passed: {report.summary}")
    except APINotReadyError as e:
        e.report.print_report()
        pytest.exit(f"API not ready: {e.report.summary}", returncode=1)
''')


if __name__ == "__main__":
    print("=" * 60)
    print("VenomQA Preflight Smoke Test Examples")
    print("=" * 60)
    print()

    # Show all examples -- only basic_smoke_test tries to connect
    conftest_integration_example()
    print()
    print("-" * 60)
    print()
    print("To run a live smoke test, set API_URL and API_TOKEN:")
    print("  API_URL=http://localhost:8000 API_TOKEN=... python examples/preflight_example.py")
