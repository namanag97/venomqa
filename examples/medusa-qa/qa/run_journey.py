#!/usr/bin/env python3
"""
Run VenomQA journeys for Medusa E-commerce.

This script runs the predefined journeys against the Medusa API.
"""

import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from venomqa.runner import JourneyRunner
from venomqa.config.settings import Settings

# Import journeys
sys.path.insert(0, str(Path(__file__).parent))
from journeys.auth_journey import admin_auth_journey, customer_auth_journey
from journeys.products_journey import product_crud_journey, product_browsing_journey
from journeys.cart_journey import cart_operations_journey
from journeys.orders_journey import complete_order_journey, order_management_journey


def main():
    """Run all journeys."""
    print("=" * 80)
    print("VenomQA - Medusa E-commerce Test Suite")
    print("=" * 80)
    print()

    # Check if API is running
    import httpx

    try:
        response = httpx.get("http://localhost:9000/health", timeout=5.0)
        print(f"Medusa API health check: {response.status_code}")
        print()
    except Exception as e:
        print("ERROR: Cannot connect to Medusa API at http://localhost:9000")
        print("Please start the API first:")
        print("  cd examples/medusa-qa")
        print("  docker compose up -d")
        print()
        return 1

    # Configure VenomQA
    settings = Settings(base_url="http://localhost:9000")

    # Create runner
    runner = JourneyRunner(settings)

    # List of all journeys to run
    journeys = [
        admin_auth_journey,
        customer_auth_journey,
        product_crud_journey,
        product_browsing_journey,
        cart_operations_journey,
        complete_order_journey,
        order_management_journey,
    ]

    print(f"Running {len(journeys)} journeys...")
    print("-" * 80)
    print()

    # Run each journey
    results = []
    for journey in journeys:
        print(f"Running: {journey.name}")
        print(f"  {journey.description}")

        try:
            result = runner.run_journey(journey)
            results.append(result)

            if result.success:
                print(f"  ✓ PASSED ({len(result.steps)} steps)")
            else:
                print(f"  ✗ FAILED")
                if result.error:
                    print(f"    Error: {result.error}")

        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append(None)

        print()

    # Summary
    print("=" * 80)
    print("Test Summary")
    print("=" * 80)

    passed = sum(1 for r in results if r and r.success)
    failed = sum(1 for r in results if r and not r.success)
    errors = sum(1 for r in results if r is None)

    print(f"Total: {len(journeys)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Errors: {errors}")
    print()

    if passed == len(journeys):
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
