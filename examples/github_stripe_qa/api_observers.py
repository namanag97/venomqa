"""State observers for the mock GitHub and Stripe servers.

Both observers extend MockHTTPServer (from venomqa.v1.adapters.mock_http_server)
which gives them REAL checkpoint/rollback support by directly snapshotting and
restoring the module-level _state dicts — no HTTP round-trips required.

Improvements over the old HTTPObserver approach:
  - observe()      reads state dict directly — O(1), no network calls
  - checkpoint()   deepcopies the state dict — fast, exact
  - rollback()     restores state dict — enables TRUE branching exploration
  - No StripeProxy needed — state dict is fully picklable
"""

from __future__ import annotations

from typing import Any

import mock_github
import mock_stripe

from venomqa.v1.adapters.mock_http_server import MockHTTPServer
from venomqa.v1.core.state import Observation


class GitHubObserver(MockHTTPServer):
    """Observes and rolls back mock GitHub server state without HTTP calls."""

    def __init__(self) -> None:
        super().__init__("github")

    @staticmethod
    def get_state_snapshot() -> dict[str, Any]:
        return mock_github.get_state_snapshot()

    @staticmethod
    def rollback_from_snapshot(snapshot: dict[str, Any]) -> None:
        with mock_github._lock:
            mock_github._state["users"].clear()
            mock_github._state["users"].update(snapshot.get("users", {}))
            mock_github._state["repos"].clear()
            mock_github._state["repos"].update(snapshot.get("repos", {}))
            mock_github._state["issues"].clear()
            mock_github._state["issues"].update(snapshot.get("issues", {}))
            mock_github._state["_issue_counters"].clear()
            mock_github._state["_issue_counters"].update(snapshot.get("_issue_counters", {}))

    def observe_from_state(self, state: dict[str, Any]) -> Observation:
        users = state.get("users", {})
        repos = state.get("repos", {})
        issues_by_repo = state.get("issues", {})

        open_count = sum(
            1 for issues in issues_by_repo.values()
            for i in issues if i.get("state") == "open"
        )
        closed_count = sum(
            1 for issues in issues_by_repo.values()
            for i in issues if i.get("state") == "closed"
        )

        return Observation(
            system="github",
            data={
                "user_count": len(users),
                "repo_count": len(repos),
                "open_issues_total": open_count,
                "closed_issues_total": closed_count,
            },
        )


class StripeObserver(MockHTTPServer):
    """Observes and rolls back mock Stripe server state without HTTP calls."""

    def __init__(self) -> None:
        super().__init__("stripe")

    @staticmethod
    def get_state_snapshot() -> dict[str, Any]:
        return mock_stripe.get_state_snapshot()

    @staticmethod
    def rollback_from_snapshot(snapshot: dict[str, Any]) -> None:
        with mock_stripe._lock:
            mock_stripe._state["customers"].clear()
            mock_stripe._state["customers"].update(snapshot.get("customers", {}))
            mock_stripe._state["payment_intents"].clear()
            mock_stripe._state["payment_intents"].update(snapshot.get("payment_intents", {}))
            mock_stripe._state["refunds"].clear()
            mock_stripe._state["refunds"].update(snapshot.get("refunds", {}))

    def observe_from_state(self, state: dict[str, Any]) -> Observation:
        pis = state.get("payment_intents", {}).values()
        total_charged = sum(
            pi.get("amount", 0) for pi in pis if pi.get("status") == "succeeded"
        )
        total_refunded = sum(pi.get("refunded_amount", 0) for pi in pis)

        return Observation(
            system="stripe",
            data={
                "payment_intent_count": len(list(pis)),
                "total_charged": total_charged,
                "total_refunded": total_refunded,
            },
        )
