#!/usr/bin/env python3
"""Runner script for VenomQA stress test scenarios.

This script provides a convenient way to run individual or all
stress test scenarios against a running application.

Usage:
    # Run all scenarios
    python run_scenarios.py --all

    # Run specific scenario
    python run_scenarios.py --scenario deep_branching

    # Run with custom base URL
    python run_scenarios.py --base-url http://localhost:3000 --scenario concurrent_checkout

    # Run with verbose output
    python run_scenarios.py --verbose --scenario file_operations

    # Generate HTML report
    python run_scenarios.py --all --report html

Available scenarios:
    - deep_branching: Tests nested checkpoints and state isolation
    - concurrent_checkout: Tests race conditions with 10 concurrent users
    - long_running: Tests 50+ step journey with memory tracking
    - failure_recovery: Tests retry logic and partial results
    - websocket_recovery: Tests WebSocket connection and recovery
    - notification: Tests real-time notification delivery
    - file_operations: Tests file upload, verification, cleanup
    - cart_expiration: Tests time-based cart expiration
    - session_timeout: Tests session timeout handling
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from venomqa import Client, JourneyRunner
from venomqa.reporters import HTMLReporter, JSONReporter, MarkdownReporter
from venomqa.state import InMemoryStateManager

# Import all scenarios
from tests.scenarios.scenario_concurrent_users import (
    concurrent_checkout_journey,
    inventory_stress_journey,
)
from tests.scenarios.scenario_deep_branching import (
    deep_branching_journey,
    triple_nested_journey,
)
from tests.scenarios.scenario_failure_recovery import (
    failure_recovery_journey,
    partial_save_journey,
)
from tests.scenarios.scenario_file_operations import (
    file_cleanup_journey,
    file_operations_journey,
)
from tests.scenarios.scenario_long_running import (
    long_running_journey,
    memory_intensive_journey,
)
from tests.scenarios.scenario_realtime import (
    notification_journey,
    websocket_recovery_journey,
)
from tests.scenarios.scenario_time_based import (
    cart_expiration_journey,
    session_timeout_journey,
)

# Scenario registry
SCENARIOS = {
    # Deep branching
    "deep_branching": deep_branching_journey,
    "triple_nested": triple_nested_journey,
    # Concurrent users
    "concurrent_checkout": concurrent_checkout_journey,
    "inventory_stress": inventory_stress_journey,
    # Long running
    "long_running": long_running_journey,
    "memory_intensive": memory_intensive_journey,
    # Failure recovery
    "failure_recovery": failure_recovery_journey,
    "partial_save": partial_save_journey,
    # Real-time
    "websocket_recovery": websocket_recovery_journey,
    "notification": notification_journey,
    # File operations
    "file_operations": file_operations_journey,
    "file_cleanup": file_cleanup_journey,
    # Time-based
    "cart_expiration": cart_expiration_journey,
    "session_timeout": session_timeout_journey,
}

# Scenario categories for grouped execution
SCENARIO_CATEGORIES = {
    "branching": ["deep_branching", "triple_nested"],
    "concurrency": ["concurrent_checkout", "inventory_stress"],
    "performance": ["long_running", "memory_intensive"],
    "resilience": ["failure_recovery", "partial_save"],
    "realtime": ["websocket_recovery", "notification"],
    "files": ["file_operations", "file_cleanup"],
    "time": ["cart_expiration", "session_timeout"],
}


def run_scenario(
    scenario_name: str,
    base_url: str,
    verbose: bool = False,
    fail_fast: bool = False,
    parallel_paths: int = 1,
) -> dict[str, Any]:
    """Run a single scenario and return results."""
    journey = SCENARIOS.get(scenario_name)
    if not journey:
        return {
            "scenario": scenario_name,
            "success": False,
            "error": f"Unknown scenario: {scenario_name}",
        }

    print(f"\n{'='*60}")
    print(f"Running scenario: {scenario_name}")
    print(f"Journey: {journey.name}")
    print(f"Description: {journey.description}")
    print(f"Tags: {', '.join(journey.tags)}")
    print(f"{'='*60}\n")

    client = Client(base_url=base_url)
    state_manager = InMemoryStateManager()

    runner = JourneyRunner(
        client=client,
        state_manager=state_manager,
        parallel_paths=parallel_paths,
        fail_fast=fail_fast,
        capture_logs=True,
    )

    start_time = time.time()

    try:
        result = runner.run(journey)
        elapsed = time.time() - start_time

        # Print summary
        if verbose:
            print(f"\nResult: {'PASSED' if result.success else 'FAILED'}")
            print(f"Duration: {elapsed:.2f}s")
            print(f"Steps: {result.passed_steps}/{result.total_steps} passed")
            print(f"Paths: {result.passed_paths}/{result.total_paths} passed")

            if result.issues:
                print(f"\nIssues ({len(result.issues)}):")
                for issue in result.issues[:5]:  # Show first 5
                    print(f"  - [{issue.severity.value}] {issue.step}: {issue.error}")

        return {
            "scenario": scenario_name,
            "journey_name": journey.name,
            "success": result.success,
            "duration_seconds": elapsed,
            "total_steps": result.total_steps,
            "passed_steps": result.passed_steps,
            "failed_steps": result.failed_steps,
            "total_paths": result.total_paths,
            "passed_paths": result.passed_paths,
            "failed_paths": result.failed_paths,
            "issues_count": len(result.issues),
            "result": result,
        }

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\nScenario failed with exception: {e}")

        return {
            "scenario": scenario_name,
            "journey_name": journey.name,
            "success": False,
            "duration_seconds": elapsed,
            "error": str(e),
        }


def run_all_scenarios(
    base_url: str,
    verbose: bool = False,
    fail_fast: bool = False,
    parallel_paths: int = 1,
) -> list[dict[str, Any]]:
    """Run all scenarios and return results."""
    results = []

    for name in SCENARIOS.keys():
        result = run_scenario(
            name,
            base_url=base_url,
            verbose=verbose,
            fail_fast=fail_fast,
            parallel_paths=parallel_paths,
        )
        results.append(result)

    return results


def run_category(
    category: str,
    base_url: str,
    verbose: bool = False,
    fail_fast: bool = False,
    parallel_paths: int = 1,
) -> list[dict[str, Any]]:
    """Run all scenarios in a category."""
    scenario_names = SCENARIO_CATEGORIES.get(category, [])

    if not scenario_names:
        print(f"Unknown category: {category}")
        print(f"Available categories: {', '.join(SCENARIO_CATEGORIES.keys())}")
        return []

    results = []
    for name in scenario_names:
        result = run_scenario(
            name,
            base_url=base_url,
            verbose=verbose,
            fail_fast=fail_fast,
            parallel_paths=parallel_paths,
        )
        results.append(result)

    return results


def generate_report(
    results: list[dict[str, Any]],
    report_type: str,
    output_dir: str = "reports",
) -> str:
    """Generate a report from results."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Combine results into a summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_scenarios": len(results),
        "passed": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "total_duration": sum(r.get("duration_seconds", 0) for r in results),
        "scenarios": results,
    }

    if report_type == "json":
        import json

        report_path = output_path / f"stress_test_report_{timestamp}.json"
        with open(report_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

    elif report_type == "html":
        report_path = output_path / f"stress_test_report_{timestamp}.html"
        # Generate simple HTML report
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>VenomQA Stress Test Report - {timestamp}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .passed {{ color: #28a745; }}
        .failed {{ color: #dc3545; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background: #333; color: white; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
    </style>
</head>
<body>
    <h1>VenomQA Stress Test Report</h1>
    <div class="summary">
        <p><strong>Generated:</strong> {summary['timestamp']}</p>
        <p><strong>Total Scenarios:</strong> {summary['total_scenarios']}</p>
        <p><strong>Passed:</strong> <span class="passed">{summary['passed']}</span></p>
        <p><strong>Failed:</strong> <span class="failed">{summary['failed']}</span></p>
        <p><strong>Total Duration:</strong> {summary['total_duration']:.2f}s</p>
    </div>
    <h2>Scenario Results</h2>
    <table>
        <tr>
            <th>Scenario</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Steps</th>
            <th>Issues</th>
        </tr>
"""
        for r in results:
            status_class = "passed" if r.get("success") else "failed"
            status_text = "PASSED" if r.get("success") else "FAILED"
            html += f"""        <tr>
            <td>{r.get('scenario', 'N/A')}</td>
            <td class="{status_class}">{status_text}</td>
            <td>{r.get('duration_seconds', 0):.2f}s</td>
            <td>{r.get('passed_steps', 0)}/{r.get('total_steps', 0)}</td>
            <td>{r.get('issues_count', r.get('error', 'N/A'))}</td>
        </tr>
"""
        html += """    </table>
</body>
</html>
"""
        with open(report_path, "w") as f:
            f.write(html)

    elif report_type == "markdown":
        report_path = output_path / f"stress_test_report_{timestamp}.md"
        md = f"""# VenomQA Stress Test Report

**Generated:** {summary['timestamp']}

## Summary

| Metric | Value |
|--------|-------|
| Total Scenarios | {summary['total_scenarios']} |
| Passed | {summary['passed']} |
| Failed | {summary['failed']} |
| Total Duration | {summary['total_duration']:.2f}s |

## Scenario Results

| Scenario | Status | Duration | Steps | Issues |
|----------|--------|----------|-------|--------|
"""
        for r in results:
            status = "PASSED" if r.get("success") else "FAILED"
            md += f"| {r.get('scenario', 'N/A')} | {status} | {r.get('duration_seconds', 0):.2f}s | {r.get('passed_steps', 0)}/{r.get('total_steps', 0)} | {r.get('issues_count', r.get('error', 'N/A'))} |\n"

        with open(report_path, "w") as f:
            f.write(md)

    else:
        report_path = output_path / f"report_{timestamp}.txt"
        with open(report_path, "w") as f:
            f.write(str(summary))

    print(f"\nReport generated: {report_path}")
    return str(report_path)


def print_summary(results: list[dict[str, Any]]) -> None:
    """Print a summary of all results."""
    print("\n" + "=" * 60)
    print("STRESS TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r.get("success"))
    failed = len(results) - passed
    total_time = sum(r.get("duration_seconds", 0) for r in results)

    print(f"\nTotal Scenarios: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total Duration: {total_time:.2f}s")

    if failed > 0:
        print("\nFailed Scenarios:")
        for r in results:
            if not r.get("success"):
                error = r.get("error", f"{r.get('issues_count', 0)} issues")
                print(f"  - {r.get('scenario')}: {error}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Run VenomQA stress test scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the application to test",
    )

    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        help="Run a specific scenario",
    )

    parser.add_argument(
        "--category",
        choices=list(SCENARIO_CATEGORIES.keys()),
        help="Run all scenarios in a category",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all scenarios",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scenarios",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure",
    )

    parser.add_argument(
        "--parallel-paths",
        type=int,
        default=1,
        help="Number of parallel paths to execute",
    )

    parser.add_argument(
        "--report",
        choices=["json", "html", "markdown"],
        help="Generate a report in the specified format",
    )

    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory for report output",
    )

    args = parser.parse_args()

    if args.list:
        print("Available Scenarios:")
        print("-" * 40)
        for name, journey in SCENARIOS.items():
            print(f"  {name}")
            print(f"    {journey.description}")
            print(f"    Tags: {', '.join(journey.tags)}")
            print()

        print("\nCategories:")
        print("-" * 40)
        for cat, scenarios in SCENARIO_CATEGORIES.items():
            print(f"  {cat}: {', '.join(scenarios)}")

        return

    results = []

    if args.scenario:
        result = run_scenario(
            args.scenario,
            base_url=args.base_url,
            verbose=args.verbose,
            fail_fast=args.fail_fast,
            parallel_paths=args.parallel_paths,
        )
        results.append(result)

    elif args.category:
        results = run_category(
            args.category,
            base_url=args.base_url,
            verbose=args.verbose,
            fail_fast=args.fail_fast,
            parallel_paths=args.parallel_paths,
        )

    elif args.all:
        results = run_all_scenarios(
            base_url=args.base_url,
            verbose=args.verbose,
            fail_fast=args.fail_fast,
            parallel_paths=args.parallel_paths,
        )

    else:
        parser.print_help()
        return

    if results:
        print_summary(results)

        if args.report:
            generate_report(results, args.report, args.output_dir)

        # Exit with error code if any failed
        failed = sum(1 for r in results if not r.get("success"))
        sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
