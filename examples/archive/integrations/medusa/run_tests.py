#!/usr/bin/env python3
"""Run Medusa E-commerce VenomQA Test Suite.

This script runs the Medusa checkout flow tests using VenomQA.

Usage:
    python run_tests.py [--base-url URL] [--region-id ID] [--api-key KEY]

Example:
    python run_tests.py --base-url http://localhost:9000 --region-id reg_01
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from venomqa import Client, JourneyRunner
from venomqa.reporters.json_report import JSONReporter
from venomqa.reporters.markdown import MarkdownReporter

from qa.journeys.checkout_flow import (
    checkout_journey,
    express_checkout_journey,
    guest_checkout_journey,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Medusa E-commerce VenomQA Test Suite",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MEDUSA_BASE_URL", "http://localhost:9000"),
        help="Medusa API base URL (default: http://localhost:9000)",
    )
    parser.add_argument(
        "--region-id",
        default=os.environ.get("MEDUSA_REGION_ID", "reg_01"),
        help="Medusa region ID for testing",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MEDUSA_PUBLISHABLE_KEY", "pk_test_key"),
        help="Medusa publishable API key",
    )
    parser.add_argument(
        "--journey",
        choices=["checkout", "guest", "express", "all"],
        default="checkout",
        help="Which journey to run (default: checkout)",
    )
    parser.add_argument(
        "--output-dir",
        default="./reports",
        help="Directory for test reports (default: ./reports)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )
    return parser.parse_args()


def create_context(args: argparse.Namespace) -> dict:
    """Create initial execution context from arguments.

    Args:
        args: Parsed command line arguments.

    Returns:
        Initial context dictionary.
    """
    return {
        "region_id": args.region_id,
        "publishable_api_key": args.api_key,
        "base_url": args.base_url,
    }


def run_journey(
    journey,
    client: Client,
    args: argparse.Namespace,
    context: dict,
) -> bool:
    """Run a single journey and report results.

    Args:
        journey: The journey to run.
        client: VenomQA HTTP client.
        args: Command line arguments.
        context: Initial context.

    Returns:
        True if journey passed, False otherwise.
    """
    logger.info(f"Running journey: {journey.name}")
    logger.info(f"Description: {journey.description}")
    logger.info("-" * 60)

    # Create runner
    runner = JourneyRunner(
        client=client,
        fail_fast=args.fail_fast,
        capture_logs=True,
    )

    # Inject context into the runner
    # Note: In actual execution, context is created by the runner
    # This shows how to pre-populate context values
    for key, value in context.items():
        pass  # Context will be passed to steps

    # Run the journey
    result = runner.run(journey)

    # Report results
    logger.info("-" * 60)
    logger.info(f"Journey: {result.journey_name}")
    logger.info(f"Status: {'PASSED' if result.success else 'FAILED'}")
    logger.info(f"Duration: {result.duration_ms:.2f}ms")
    logger.info(f"Steps: {result.passed_steps}/{result.total_steps} passed")
    logger.info(f"Paths: {result.passed_paths}/{result.total_paths} passed")

    if result.issues:
        logger.warning(f"Issues: {len(result.issues)}")
        for issue in result.issues:
            logger.warning(f"  - [{issue.severity.value}] {issue.step}: {issue.error}")

    # Save reports
    os.makedirs(args.output_dir, exist_ok=True)

    # JSON report
    json_reporter = JSONReporter(
        output_path=os.path.join(args.output_dir, f"{journey.name}_results.json")
    )
    json_reporter.report([result])

    # Markdown report
    md_reporter = MarkdownReporter(
        output_path=os.path.join(args.output_dir, f"{journey.name}_report.md")
    )
    md_reporter.report([result])

    return result.success


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Medusa E-commerce VenomQA Test Suite")
    logger.info("=" * 60)
    logger.info(f"Base URL: {args.base_url}")
    logger.info(f"Region ID: {args.region_id}")
    logger.info(f"Journey: {args.journey}")
    logger.info("=" * 60)

    # Create client
    client = Client(
        base_url=args.base_url,
        timeout=30.0,
        retry_count=3,
        retry_delay=1.0,
    )

    # Create initial context
    context = create_context(args)

    # Select journeys to run
    journeys = []
    if args.journey == "checkout" or args.journey == "all":
        journeys.append(checkout_journey)
    if args.journey == "guest" or args.journey == "all":
        journeys.append(guest_checkout_journey)
    if args.journey == "express" or args.journey == "all":
        journeys.append(express_checkout_journey)

    # Run journeys
    all_passed = True
    for journey in journeys:
        try:
            passed = run_journey(journey, client, args, context)
            if not passed:
                all_passed = False
                if args.fail_fast:
                    break
        except Exception as e:
            logger.error(f"Journey {journey.name} failed with exception: {e}")
            all_passed = False
            if args.fail_fast:
                break
        finally:
            client.clear_history()

    # Summary
    logger.info("=" * 60)
    logger.info("Test Suite Summary")
    logger.info("=" * 60)
    logger.info(f"Journeys run: {len(journeys)}")
    logger.info(f"Overall status: {'PASSED' if all_passed else 'FAILED'}")
    logger.info(f"Reports saved to: {args.output_dir}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
