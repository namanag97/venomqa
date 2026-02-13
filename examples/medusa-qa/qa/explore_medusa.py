#!/usr/bin/env python3
"""
State Chain Exploration for Medusa E-commerce API.

This script demonstrates VenomQA's context-aware state exploration capabilities
by automatically discovering and testing the Medusa e-commerce API endpoints.

It will:
1. Discover available API endpoints from OpenAPI spec (or manual definition)
2. Execute actions and extract context (IDs, tokens) from responses
3. Use extracted context in subsequent requests (no placeholder errors!)
4. Build a deep state graph showing all possible paths
5. Generate visualizations and reports
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from venomqa.explorer import (
    StateExplorer,
    ExplorationConfig,
    ExplorationStrategy,
    Action,
)
from venomqa.explorer.context import ExplorationContext


async def explore_medusa():
    """Run context-aware exploration of Medusa API."""

    print("=" * 80)
    print("VenomQA State Chain Exploration - Medusa E-commerce")
    print("=" * 80)
    print()

    # Configure exploration
    config = ExplorationConfig(
        base_url="http://localhost:9000",
        max_depth=8,
        max_states=100,
        strategy=ExplorationStrategy.BFS,
        request_timeout=10.0,
        request_delay_ms=200,  # Be nice to the server
    )

    # Define initial actions manually (since we may not have OpenAPI spec)
    # These are the entry points for exploration
    initial_actions = [
        # Health check
        Action(
            method="GET",
            endpoint="/health",
            description="Health Check",
        ),
        # Store endpoints (public)
        Action(
            method="GET",
            endpoint="/store/products",
            description="List Products",
        ),
        Action(
            method="POST",
            endpoint="/store/carts",
            body={},
            description="Create Cart",
        ),
        # Admin auth
        Action(
            method="POST",
            endpoint="/admin/auth",
            body={
                "email": "admin@test.com",
                "password": "supersecret"
            },
            description="Admin Login",
        ),
    ]

    # Create explorer
    explorer = StateExplorer(
        base_url=config.base_url,
        config=config,
        strategy=config.strategy,
    )

    print(f"Base URL: {config.base_url}")
    print(f"Strategy: {config.strategy}")
    print(f"Max Depth: {config.max_depth}")
    print(f"Initial Actions: {len(initial_actions)}")
    print()
    print("Starting exploration...")
    print("-" * 80)

    try:
        # Run exploration with initial actions
        result = await explorer.explore(initial_actions=initial_actions)

        print()
        print("=" * 80)
        print("Exploration Complete!")
        print("=" * 80)
        print()

        # Print summary
        print("SUMMARY:")
        print(f"  States Discovered: {len(result.states)}")
        print(f"  Transitions: {len(result.transitions)}")
        print(f"  Duration: {result.duration}")
        print(f"  Total Requests: {result.total_requests}")
        print(f"  Failed Requests: {result.failed_requests}")
        print(f"  Success Rate: {result.success_rate:.1f}%")
        print()

        # Print coverage
        if result.coverage:
            print("COVERAGE:")
            print(f"  Endpoint Coverage: {result.coverage.endpoint_coverage_percent:.1f}%")
            print(f"  States Found: {result.coverage.total_states}")
            print()

        # Print issues
        if result.issues:
            print(f"ISSUES FOUND: {len(result.issues)}")
            critical_issues = result.get_critical_issues()
            if critical_issues:
                print(f"  Critical/High: {len(critical_issues)}")
                for issue in critical_issues[:5]:  # Show first 5
                    print(f"    - {issue.title}")
            print()

        # Print some interesting states
        print("STATE GRAPH SAMPLE:")
        for i, state in enumerate(result.states[:10]):  # First 10 states
            print(f"  [{i+1}] {state.name}")
            if state.context:
                context_summary = ", ".join(
                    f"{k}={v}" for k, v in list(state.context.items())[:3]
                )
                print(f"      Context: {context_summary}")
        print()

        # Generate outputs
        output_dir = Path(__file__).parent / "exploration_results"
        output_dir.mkdir(exist_ok=True)

        # Save JSON result
        json_path = output_dir / "exploration_result.json"
        result.to_json(str(json_path))
        print(f"Saved JSON: {json_path}")

        # Generate visualization
        try:
            graph_path = output_dir / "state_graph.png"
            result.visualize(str(graph_path), format="png")
            print(f"Saved Graph: {graph_path}")
        except Exception as e:
            print(f"Could not generate visualization: {e}")
            print("(Install graphviz to enable: pip install graphviz)")

        # Generate HTML visualization
        try:
            html_path = output_dir / "state_graph.html"
            result.visualize(str(html_path), format="html")
            print(f"Saved HTML: {html_path}")
        except Exception as e:
            print(f"Could not generate HTML: {e}")

        print()
        print("=" * 80)
        print("Exploration artifacts saved to:", output_dir)
        print("=" * 80)

        return result

    except Exception as e:
        print()
        print("=" * 80)
        print(f"ERROR: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return None


def main():
    """Entry point."""
    # Check if Medusa is running
    import httpx

    try:
        response = httpx.get("http://localhost:9000/health", timeout=5.0)
        print(f"Medusa health check: {response.status_code}")
    except Exception as e:
        print("ERROR: Cannot connect to Medusa at http://localhost:9000")
        print("Please start Medusa first:")
        print("  cd examples/medusa-qa")
        print("  docker compose up -d")
        print()
        return 1

    # Run exploration
    result = asyncio.run(explore_medusa())

    if result:
        print()
        print("Exploration completed successfully!")
        return 0
    else:
        print()
        print("Exploration failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
