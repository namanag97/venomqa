"""GitHub + Stripe QA exploration entry point.

Starts in-process mock servers for GitHub and Stripe, then runs a VenomQA v1
Agent that exhaustively explores actions and checks invariants.

Two bugs are deliberately planted in the mock servers:

  BUG 1 (GitHub) — Open issues list leaks closed issues
    The GET /repos/{id}/issues?state=open endpoint returns any closed issue
    that exists, in addition to the open ones. Detected by:
      → invariant "open_issues_never_contain_closed" (CRITICAL)

  BUG 2 (Stripe) — Over-refund not validated
    The POST /refunds endpoint accepts a refund amount greater than the
    original PaymentIntent amount. Detected by:
      → invariant "refund_cannot_exceed_payment" (CRITICAL)

Usage:
    python main.py
"""

from __future__ import annotations

import sys
import time

# ---------------------------------------------------------------------------
# Add project root to path so venomqa imports work from this directory
# ---------------------------------------------------------------------------
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from venomqa import Agent, World
from venomqa.adapters.http import HttpClient
from venomqa.core.action import Action
from venomqa.agent.strategies import BFS
from stripe_proxy import StripeProxy
from api_observers import GitHubObserver, StripeObserver

from mock_github import start_server as start_github, reset_state as reset_github
from mock_stripe import start_server as start_stripe, reset_state as reset_stripe
from actions import (
    # GitHub
    create_user,
    create_repo,
    list_repos,
    create_issue,
    list_open_issues,
    close_issue,
    delete_repo,
    # Stripe
    create_customer,
    create_payment_intent,
    confirm_payment,
    create_refund,
    get_payment_intent,
)
from invariants import ALL_INVARIANTS

GITHUB_PORT = 8101
STRIPE_PORT = 8102


def build_actions() -> list[Action]:
    """Wrap bare functions as VenomQA Action objects.

    Note: preconditions define action ordering constraints.
    VenomQA only runs an action if ALL its preconditions have succeeded.
    """
    return [
        # --- GitHub ---------------------------------------------------------
        # Dependency chain: create_user -> create_repo -> create_issue -> close_issue
        Action(
            name="create_user",
            execute=create_user,
            description="Register a new GitHub user",
            tags=["github", "write"],
            expected_status=[201],
        ),
        Action(
            name="create_repo",
            execute=create_repo,
            description="Create a repository owned by the current user",
            tags=["github", "write"],
            preconditions=["create_user"],  # Must have a user first
        ),
        Action(
            name="list_repos",
            execute=list_repos,
            description="List repositories for the current user",
            tags=["github", "read"],
            expected_status=[200],
            preconditions=["create_user"],
        ),
        Action(
            name="create_issue",
            execute=create_issue,
            description="Open a new issue in the current repo",
            tags=["github", "write"],
            preconditions=["create_repo"],  # Must have a repo first
        ),
        Action(
            name="list_open_issues",
            execute=list_open_issues,
            description="List open issues for the current repo",
            tags=["github", "read"],
            preconditions=["create_repo"],
        ),
        Action(
            name="close_issue",
            execute=close_issue,
            description="Close the most recently created issue",
            tags=["github", "write"],
            preconditions=["create_issue"],  # Must have an issue first
        ),
        Action(
            name="delete_repo",
            execute=delete_repo,
            description="Delete the current repo",
            tags=["github", "write"],
            preconditions=["create_repo"],
        ),
        # --- Stripe ---------------------------------------------------------
        # Dependency chain: create_customer -> create_payment_intent -> confirm -> refund
        Action(
            name="create_customer",
            execute=create_customer,
            description="Create a Stripe customer",
            tags=["stripe", "write"],
            expected_status=[201],
        ),
        Action(
            name="create_payment_intent",
            execute=create_payment_intent,
            description="Create a $10 PaymentIntent for the current customer",
            tags=["stripe", "write"],
            expected_status=[201],
            preconditions=["create_customer"],
        ),
        Action(
            name="confirm_payment",
            execute=confirm_payment,
            description="Confirm the current PaymentIntent",
            tags=["stripe", "write"],
            preconditions=["create_payment_intent"],
        ),
        Action(
            name="create_refund",
            execute=create_refund,
            description="Issue a refund (2× original amount) — probes over-refund bug",
            tags=["stripe", "write"],
            preconditions=["confirm_payment"],  # Must confirm before refund
        ),
        Action(
            name="get_payment_intent",
            execute=get_payment_intent,
            description="Retrieve the current PaymentIntent state",
            tags=["stripe", "read"],
            preconditions=["create_payment_intent"],
        ),
    ]


def run_exploration(max_steps: int = 50) -> bool:
    """Start mock servers, explore, print results.  Returns True if no violations."""
    # ---------------------------------------------------------------- servers
    print("Starting mock servers...")
    reset_github()
    reset_stripe()
    github_server = start_github(GITHUB_PORT)
    stripe_server = start_stripe(STRIPE_PORT)
    time.sleep(0.1)  # Give servers a moment to bind
    print(f"  GitHub mock : http://localhost:{GITHUB_PORT}")
    print(f"  Stripe mock : http://localhost:{STRIPE_PORT}")

    # ---------------------------------------------------------------- clients
    github_api = HttpClient(f"http://localhost:{GITHUB_PORT}")
    stripe_api = StripeProxy(f"http://localhost:{STRIPE_PORT}")

    # ---------------------------------------------------------------- world
    # Direct-state observers (MockHTTPServer): no HTTP calls, real rollback
    github_obs = GitHubObserver()
    stripe_obs = StripeObserver()
    world = World(
        api=github_api,
        systems={"github": github_obs, "stripe_obs": stripe_obs},
    )
    # Pass Stripe client through context so Stripe actions can reach it
    world.context.set("stripe", stripe_api)

    # ---------------------------------------------------------------- agent
    actions = build_actions()
    agent = Agent(
        world=world,
        actions=actions,
        invariants=ALL_INVARIANTS,
        strategy=BFS(),
        max_steps=max_steps,
    )

    # ---------------------------------------------------------------- explore
    print(f"\nRunning exploration (max_steps={max_steps})...")
    print("-" * 60)
    result = agent.explore()

    # ---------------------------------------------------------------- report
    print("\n" + "=" * 60)
    print("EXPLORATION RESULTS")
    print("=" * 60)
    print(f"  States visited    : {result.states_visited}")
    print(f"  Transitions taken : {result.transitions_taken}")
    used = result.graph.used_action_count
    total = result.actions_total
    print(f"  Actions used      : {used}/{total} ({result.action_coverage_percent:.0f}%)")
    print(f"  Duration          : {result.duration_ms:.0f} ms")
    print(f"  Violations found  : {len(result.violations)}")

    if result.violations:
        print("\nVIOLATIONS DETECTED:")
        for v in result.violations:
            sev_label = f"[{v.severity.value.upper()}]"
            print(f"\n  {sev_label} {v.invariant_name}")
            print(f"    {v.message}")
    else:
        print("\nNo invariant violations — all checks passed.")

    print("\n" + "=" * 60)

    # ---------------------------------------------------------------- cleanup
    github_server.shutdown()
    stripe_server.shutdown()
    github_api.close()
    stripe_api.close()
    # MockHTTPServer observers have no HTTP client to close (no-op close)

    return len(result.violations) == 0


if __name__ == "__main__":
    clean = run_exploration(max_steps=60)
    # We EXPECT violations because we planted bugs — exit 0 means exploration
    # ran successfully even though violations were found.
    sys.exit(0)
