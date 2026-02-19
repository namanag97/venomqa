#!/usr/bin/env python3
"""Run all VenomQA journeys and generate comprehensive reports."""

import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from venomqa import Client, JourneyRunner
from venomqa.reporters.html import HTMLReporter
from venomqa.reporters.markdown import MarkdownReporter
from venomqa.reporters.json_report import JSONReporter

# Import all journeys
from journeys.crud_journey import crud_journey, crud_with_branches_journey
from journeys.error_handling_journey import (
    error_handling_journey,
    validation_errors_journey,
    pagination_journey,
)
from journeys.file_upload_journey import file_upload_journey, multiple_uploads_journey
from journeys.comprehensive_journey import (
    comprehensive_journey,
    search_filter_journey,
    lifecycle_journey,
)

# Configuration
BASE_URL = os.environ.get("VENOMQA_BASE_URL", "http://localhost:5001")
REPORTS_DIR = Path(__file__).parent / "reports"


def main():
    """Run all journeys and generate reports."""
    print("=" * 70)
    print("VenomQA Comprehensive Test Suite")
    print("=" * 70)
    print(f"Target API: {BASE_URL}")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 70)
    print()

    # Create reports directory
    REPORTS_DIR.mkdir(exist_ok=True)

    # Initialize client
    client = Client(base_url=BASE_URL)

    # Check API health
    try:
        response = client.get("/health")
        if response.status_code != 200:
            print(f"ERROR: API health check failed with status {response.status_code}")
            sys.exit(1)
        print(f"API Health: OK ({response.json()})")
    except Exception as e:
        print(f"ERROR: Cannot reach API at {BASE_URL}: {e}")
        sys.exit(1)

    print()

    # Define all journeys to run
    journeys = [
        ("CRUD Operations", crud_journey),
        ("CRUD with Branches", crud_with_branches_journey),
        ("Error Handling", error_handling_journey),
        ("Validation Errors", validation_errors_journey),
        ("Pagination Tests", pagination_journey),
        ("File Upload Operations", file_upload_journey),
        ("Multiple File Uploads", multiple_uploads_journey),
        ("Comprehensive API Test", comprehensive_journey),
        ("Search and Filter", search_filter_journey),
        ("Todo Lifecycle", lifecycle_journey),
    ]

    # Run all journeys
    results = []
    passed = 0
    failed = 0

    for name, journey in journeys:
        print(f"Running: {name} ({journey.name})")
        print("-" * 50)

        try:
            # Create fresh client for each journey to reset state
            journey_client = Client(base_url=BASE_URL)
            runner = JourneyRunner(client=journey_client)
            result = runner.run(journey)
            results.append(result)

            if result.success:
                passed += 1
                status = "PASSED"
            else:
                failed += 1
                status = "FAILED"

            print(f"  Status: {status}")
            print(f"  Duration: {result.duration_ms:.2f}ms")
            print(f"  Steps: {result.passed_steps}/{result.total_steps} passed")
            if result.total_paths > 0:
                print(f"  Paths: {result.passed_paths}/{result.total_paths} passed")
            if result.issues:
                print(f"  Issues: {len(result.issues)}")
                for issue in result.issues[:3]:  # Show first 3 issues
                    print(f"    - {issue.step}: {issue.error}")

        except Exception as e:
            failed += 1
            print(f"  Status: ERROR")
            print(f"  Error: {e}")

        print()

    # Print summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total Journeys: {len(journeys)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass Rate: {passed / len(journeys) * 100:.1f}%")
    print()

    # Generate reports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # HTML Report
    html_path = REPORTS_DIR / f"test_results_{timestamp}.html"
    html_reporter = HTMLReporter(title="VenomQA Todo App Test Results")
    html_content = html_reporter.generate(results)
    html_path.write_text(html_content)
    print(f"HTML Report: {html_path}")

    # Markdown Report
    md_path = REPORTS_DIR / f"test_results_{timestamp}.md"
    md_reporter = MarkdownReporter()
    md_content = md_reporter.generate(results)
    md_path.write_text(md_content)
    print(f"Markdown Report: {md_path}")

    # JSON Report
    json_path = REPORTS_DIR / f"test_results_{timestamp}.json"
    json_reporter = JSONReporter()
    json_content = json_reporter.generate(results)
    json_path.write_text(json_content)
    print(f"JSON Report: {json_path}")

    print()
    print("=" * 70)
    print(f"Finished at: {datetime.now().isoformat()}")
    print("=" * 70)

    # Return exit code based on results
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
