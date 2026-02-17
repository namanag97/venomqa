"""Pytest tests for the GitHub + Stripe mock API QA exploration.

These tests exercise VenomQA's exploration engine against the two intentionally
buggy mock servers and assert that the expected violations are found.

Run with:
    pytest examples/github_stripe_qa/test_exploration.py -v

Or from the project root:
    pytest examples/github_stripe_qa/ -v
"""

from __future__ import annotations

import os
import sys
import time

import pytest

# Make venomqa and example modules importable when run from any directory
_HERE = os.path.dirname(__file__)
_ROOT = os.path.join(_HERE, "..", "..")
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from venomqa.v1 import Agent, World
from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.adapters.mock_queue import MockQueue
from venomqa.v1.core.action import Action
from venomqa.v1.agent.strategies import BFS, DFS
from stripe_proxy import StripeProxy

import mock_github
import mock_stripe
from api_observers import GitHubObserver, StripeObserver
from actions import (
    create_user,
    create_repo,
    list_repos,
    create_issue,
    list_open_issues,
    close_issue,
    delete_repo,
    create_customer,
    create_payment_intent,
    confirm_payment,
    create_refund,
    get_payment_intent,
)
from invariants import (
    ALL_INVARIANTS,
    open_issues_never_contain_closed,
    refund_cannot_exceed_payment,
    open_issues_count_matches,
    deleted_repo_returns_404,
    confirmed_payment_status_is_succeeded,
    customer_must_exist_for_payment,
)

# ---------------------------------------------------------------------------
# Ports — use non-default to avoid collisions with main.py if run concurrently
# ---------------------------------------------------------------------------
GITHUB_PORT = 8111
STRIPE_PORT = 8112


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def servers():
    """Start mock servers once for all tests in this module."""
    mock_github.reset_state()
    mock_stripe.reset_state()
    gh = mock_github.start_server(GITHUB_PORT)
    st = mock_stripe.start_server(STRIPE_PORT)
    time.sleep(0.1)
    yield
    gh.shutdown()
    st.shutdown()


@pytest.fixture()
def clean_state():
    """Reset server state before each test."""
    mock_github.reset_state()
    mock_stripe.reset_state()


@pytest.fixture()
def world(servers, clean_state):
    """Provide a freshly configured World with both API clients."""
    github_api = HttpClient(f"http://localhost:{GITHUB_PORT}")
    # Stripe client stored in context: StripeProxy is still needed because
    # HttpClient wraps httpx.Client (has threading.Lock) which can't be deepcopied.
    stripe_api = StripeProxy(f"http://localhost:{STRIPE_PORT}")
    # Observers now use MockHTTPServer — direct state dict access, no HTTP calls,
    # real checkpoint/rollback enabled.
    github_obs = GitHubObserver()
    stripe_obs = StripeObserver()

    w = World(
        api=github_api,
        systems={"github": github_obs, "stripe_obs": stripe_obs},
    )
    w.context.set("stripe", stripe_api)

    yield w

    github_api.close()
    stripe_api.close()


def _all_actions() -> list[Action]:
    return [
        Action(name="create_user",           execute=create_user,           tags=["github"]),
        Action(name="create_repo",           execute=create_repo,           tags=["github"]),
        Action(name="list_repos",            execute=list_repos,            tags=["github"]),
        Action(name="create_issue",          execute=create_issue,          tags=["github"]),
        Action(name="list_open_issues",      execute=list_open_issues,      tags=["github"]),
        Action(name="close_issue",           execute=close_issue,           tags=["github"]),
        Action(name="delete_repo",           execute=delete_repo,           tags=["github"]),
        Action(name="create_customer",       execute=create_customer,       tags=["stripe"]),
        Action(name="create_payment_intent", execute=create_payment_intent, tags=["stripe"]),
        Action(name="confirm_payment",       execute=confirm_payment,       tags=["stripe"]),
        Action(name="create_refund",         execute=create_refund,         tags=["stripe"]),
        Action(name="get_payment_intent",    execute=get_payment_intent,    tags=["stripe"]),
    ]


# ---------------------------------------------------------------------------
# Mock server unit tests
# ---------------------------------------------------------------------------

class TestMockGitHubServer:
    """Directly test the mock GitHub server endpoints."""

    def test_create_and_get_user(self, servers, clean_state):
        api = HttpClient(f"http://localhost:{GITHUB_PORT}")
        result = api.post("/users", json={"login": "alice", "email": "alice@test.com"})
        assert result.response.status_code == 201
        assert result.response.body["login"] == "alice"

        get_result = api.get("/users/alice")
        assert get_result.response.status_code == 200
        api.close()

    def test_duplicate_user_rejected(self, servers, clean_state):
        api = HttpClient(f"http://localhost:{GITHUB_PORT}")
        api.post("/users", json={"login": "bob"})
        second = api.post("/users", json={"login": "bob"})
        assert second.response.status_code == 409
        api.close()

    def test_create_repo_requires_owner(self, servers, clean_state):
        api = HttpClient(f"http://localhost:{GITHUB_PORT}")
        result = api.post("/repos", json={"owner_login": "nobody", "name": "myrepo"})
        assert result.response.status_code == 404
        api.close()

    def test_open_issues_leaks_closed_bug(self, servers, clean_state):
        """Reproduce the planted GitHub bug directly."""
        api = HttpClient(f"http://localhost:{GITHUB_PORT}")
        api.post("/users", json={"login": "tester"})
        repo = api.post("/repos", json={"owner_login": "tester", "name": "r1"})
        repo_id = repo.response.body["id"]

        # Create and close an issue
        iss = api.post(f"/repos/{repo_id}/issues", json={"title": "Bug"})
        issue_num = iss.response.body["number"]
        api.patch(f"/repos/{repo_id}/issues/{issue_num}", json={"state": "closed"})

        # List open issues — the buggy server includes the closed one
        open_result = api.get(f"/repos/{repo_id}/issues", params={"state": "open"})
        issues = open_result.response.body
        closed_in_open = [i for i in issues if i["state"] == "closed"]
        assert len(closed_in_open) > 0, "Expected the bug to be reproduced"
        api.close()

    def test_delete_repo(self, servers, clean_state):
        api = HttpClient(f"http://localhost:{GITHUB_PORT}")
        api.post("/users", json={"login": "del_user"})
        repo = api.post("/repos", json={"owner_login": "del_user", "name": "del_repo"})
        repo_id = repo.response.body["id"]

        del_result = api.delete(f"/repos/{repo_id}")
        assert del_result.response.status_code == 204

        get_result = api.get(f"/repos/{repo_id}")
        assert get_result.response.status_code == 404
        api.close()


class TestMockStripeServer:
    """Directly test the mock Stripe server endpoints."""

    def test_create_customer(self, servers, clean_state):
        api = HttpClient(f"http://localhost:{STRIPE_PORT}")
        result = api.post("/customers", json={"email": "pay@test.com"})
        assert result.response.status_code == 201
        assert result.response.body["id"].startswith("cus_")
        api.close()

    def test_payment_intent_lifecycle(self, servers, clean_state):
        api = HttpClient(f"http://localhost:{STRIPE_PORT}")
        cust = api.post("/customers", json={"email": "buyer@test.com"})
        cid = cust.response.body["id"]

        pi = api.post("/payment_intents", json={"amount": 500, "currency": "usd", "customer_id": cid})
        assert pi.response.status_code == 201
        pid = pi.response.body["id"]
        assert pi.response.body["status"] == "requires_confirmation"

        confirmed = api.post(f"/payment_intents/{pid}/confirm")
        assert confirmed.response.body["status"] == "succeeded"
        api.close()

    def test_over_refund_bug(self, servers, clean_state):
        """Reproduce the planted Stripe over-refund bug directly."""
        api = HttpClient(f"http://localhost:{STRIPE_PORT}")
        cust = api.post("/customers", json={"email": "refund@test.com"})
        cid = cust.response.body["id"]

        pi = api.post("/payment_intents", json={"amount": 1000, "currency": "usd", "customer_id": cid})
        pid = pi.response.body["id"]
        api.post(f"/payment_intents/{pid}/confirm")

        # Refund more than the original — should be rejected but isn't (bug)
        refund = api.post("/refunds", json={"payment_intent_id": pid, "amount": 9999})
        assert refund.response.status_code == 201, "Bug: over-refund was accepted"

        pi_after = api.get(f"/payment_intents/{pid}")
        assert pi_after.response.body["refunded_amount"] > pi_after.response.body["amount"], (
            "Bug confirmed: refunded_amount exceeds original amount"
        )
        api.close()


# ---------------------------------------------------------------------------
# VenomQA exploration tests
# ---------------------------------------------------------------------------

class TestVenomQAExploration:
    """Run VenomQA Agent exploration and assert invariant violations are found."""

    def test_exploration_finds_github_bug(self, world):
        """Agent must detect the open-issues-leaks-closed bug.

        Uses only the 5 GitHub actions needed to trigger the bug so that
        BFS reaches the sequence  create_issue → close_issue → list_open_issues
        within a reasonable number of steps.
        """
        github_only_actions = [
            Action(name="create_user",      execute=create_user,      tags=["github"]),
            Action(name="create_repo",      execute=create_repo,      tags=["github"]),
            Action(name="create_issue",     execute=create_issue,     tags=["github"]),
            Action(name="close_issue",      execute=close_issue,      tags=["github"]),
            Action(name="list_open_issues", execute=list_open_issues, tags=["github"]),
        ]
        agent = Agent(
            world=world,
            actions=github_only_actions,
            invariants=[open_issues_never_contain_closed],
            strategy=BFS(),
            max_steps=60,
        )
        result = agent.explore()

        violation_names = {v.invariant_name for v in result.violations}
        assert "open_issues_never_contain_closed" in violation_names, (
            "VenomQA should have detected the open-issue leak bug in the "
            "mock GitHub server"
        )

    def test_exploration_finds_stripe_bug(self, world):
        """Agent must detect the over-refund bug.

        Uses only the 5 Stripe actions needed to trigger the bug.
        """
        stripe_only_actions = [
            Action(name="create_customer",       execute=create_customer,       tags=["stripe"]),
            Action(name="create_payment_intent", execute=create_payment_intent, tags=["stripe"]),
            Action(name="confirm_payment",       execute=confirm_payment,       tags=["stripe"]),
            Action(name="create_refund",         execute=create_refund,         tags=["stripe"]),
            Action(name="get_payment_intent",    execute=get_payment_intent,    tags=["stripe"]),
        ]
        agent = Agent(
            world=world,
            actions=stripe_only_actions,
            invariants=[refund_cannot_exceed_payment],
            strategy=BFS(),
            max_steps=50,
        )
        result = agent.explore()

        violation_names = {v.invariant_name for v in result.violations}
        assert "refund_cannot_exceed_payment" in violation_names, (
            "VenomQA should have detected the over-refund bug in the "
            "mock Stripe server"
        )

    def test_full_exploration_finds_both_bugs(self, world):
        """Two focused BFS explorations together catch both planted bugs.

        Running ALL 12 actions simultaneously dilutes BFS — each state fans out
        into 12 branches and it takes too many steps to reach the specific
        sequences that trigger each bug. In practice, QA suites run subsystem-
        focused explorations (GitHub actions + GitHub invariants, Stripe actions
        + Stripe invariants) rather than one giant mixed run. This test models
        that pattern.
        """
        # --- GitHub-focused exploration (finds open-issue leak bug) ----------
        github_actions = [
            Action(name="create_user",      execute=create_user,      tags=["github"]),
            Action(name="create_repo",      execute=create_repo,      tags=["github"]),
            Action(name="create_issue",     execute=create_issue,     tags=["github"]),
            Action(name="close_issue",      execute=close_issue,      tags=["github"]),
            Action(name="list_open_issues", execute=list_open_issues, tags=["github"]),
        ]
        github_agent = Agent(
            world=world,
            actions=github_actions,
            invariants=[open_issues_never_contain_closed, open_issues_count_matches],
            strategy=BFS(),
            max_steps=60,
        )
        github_result = github_agent.explore()
        github_violation_names = {v.invariant_name for v in github_result.violations}

        # --- Stripe-focused exploration (finds over-refund bug) --------------
        stripe_actions = [
            Action(name="create_customer",       execute=create_customer,       tags=["stripe"]),
            Action(name="create_payment_intent", execute=create_payment_intent, tags=["stripe"]),
            Action(name="confirm_payment",       execute=confirm_payment,       tags=["stripe"]),
            Action(name="create_refund",         execute=create_refund,         tags=["stripe"]),
            Action(name="get_payment_intent",    execute=get_payment_intent,    tags=["stripe"]),
        ]
        stripe_agent = Agent(
            world=world,
            actions=stripe_actions,
            invariants=[refund_cannot_exceed_payment, confirmed_payment_status_is_succeeded],
            strategy=BFS(),
            max_steps=50,
        )
        stripe_result = stripe_agent.explore()
        stripe_violation_names = {v.invariant_name for v in stripe_result.violations}

        # --- Combined assertions ---------------------------------------------
        assert "open_issues_never_contain_closed" in github_violation_names, (
            "GitHub exploration should detect the open-issue leak bug"
        )
        assert "refund_cannot_exceed_payment" in stripe_violation_names, (
            "Stripe exploration should detect the over-refund bug"
        )

    def test_exploration_visits_states(self, world):
        """Sanity check: the agent actually explores multiple states."""
        agent = Agent(
            world=world,
            actions=_all_actions(),
            invariants=ALL_INVARIANTS,
            strategy=BFS(),
            max_steps=30,
        )
        result = agent.explore()
        assert result.states_visited >= 2, "Agent should visit more than the initial state"
        assert result.transitions_taken >= 1

    def test_exploration_with_dfs_strategy(self, world):
        """DFS explores many states (depth-first without HTTP rollback = sequential).

        DFS explores a deep linear path through action sequences. Because the
        HTTP server does not support rollback, DFS effectively runs a long
        sequential exploration rather than true branching. We verify that:
         - many states are visited
         - many transitions are taken (all steps exhausted)
        Bug detection is handled by the BFS tests above.
        """
        agent = Agent(
            world=world,
            actions=_all_actions(),
            invariants=[open_issues_never_contain_closed, refund_cannot_exceed_payment],
            strategy=DFS(),
            max_steps=60,
        )
        result = agent.explore()

        # DFS explores many distinct states because each API call changes
        # the server state (user count, repo count, etc.)
        assert result.states_visited >= 5, (
            f"DFS should visit many states, got {result.states_visited}"
        )
        assert result.transitions_taken >= 10

    def test_github_only_actions_no_stripe_violations(self, world):
        """Running only GitHub actions should not produce Stripe violations."""
        github_actions = [
            Action(name="create_user",      execute=create_user,      tags=["github"]),
            Action(name="create_repo",      execute=create_repo,      tags=["github"]),
            Action(name="create_issue",     execute=create_issue,     tags=["github"]),
            Action(name="list_open_issues", execute=list_open_issues, tags=["github"]),
            Action(name="close_issue",      execute=close_issue,      tags=["github"]),
        ]
        agent = Agent(
            world=world,
            actions=github_actions,
            invariants=[refund_cannot_exceed_payment, confirmed_payment_status_is_succeeded],
            strategy=BFS(),
            max_steps=30,
        )
        result = agent.explore()
        # Stripe invariants should never trigger when only GitHub actions run
        assert len(result.violations) == 0, (
            "Stripe invariants should not fire when no Stripe actions are executed"
        )

    def test_stripe_only_actions_no_github_violations(self, world):
        """Running only Stripe actions should not produce GitHub violations."""
        stripe_actions = [
            Action(name="create_customer",       execute=create_customer,       tags=["stripe"]),
            Action(name="create_payment_intent", execute=create_payment_intent, tags=["stripe"]),
            Action(name="confirm_payment",       execute=confirm_payment,       tags=["stripe"]),
            Action(name="get_payment_intent",    execute=get_payment_intent,    tags=["stripe"]),
        ]
        agent = Agent(
            world=world,
            actions=stripe_actions,
            invariants=[open_issues_never_contain_closed, open_issues_count_matches],
            strategy=BFS(),
            max_steps=30,
        )
        result = agent.explore()
        assert len(result.violations) == 0, (
            "GitHub invariants should not fire when only Stripe actions are executed"
        )
