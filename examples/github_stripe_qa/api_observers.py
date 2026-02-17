"""HTTP-backed Rollbackable observers for the mock GitHub and Stripe servers.

VenomQA's state graph is built from observations. When the World's systems
all return unchanged observations, VenomQA sees only one state and terminates.

These observers solve the problem by fetching LIVE state from the mock HTTP
servers on every observe() call. As users, repos, issues and payments are
created/deleted, the observations change, creating new distinct states in the
exploration graph.

Because real HTTP servers don't support SAVEPOINT-style rollback, checkpoint()
and rollback() are no-ops here. The trade-off: exploration is sequential (no
branching), but invariants are still checked after every action.
"""

from __future__ import annotations

import httpx

from venomqa.v1.core.state import Observation


class GitHubObserver:
    """Observes mock GitHub API state for VenomQA."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=5.0)
        self._checkpoints: dict[str, dict] = {}

    # ------------------------------------------------------------------ observe
    def observe(self) -> Observation:
        """Fetch current state from the GitHub mock server."""
        try:
            repos_resp = self._client.get("/repos")
            repos = repos_resp.json() if repos_resp.status_code == 200 else []
        except Exception:
            repos = []

        open_issues_total = sum(r.get("open_issues_count", 0) for r in repos)

        return Observation(
            system="github",
            data={
                "repo_count": len(repos),
                "open_issues_total": open_issues_total,
            },
        )

    # ------------------------------------------------------------------ checkpoint / rollback
    def checkpoint(self, name: str) -> dict:
        """Save current observation as a checkpoint (HTTP servers don't rollback)."""
        snap = self.observe().data
        self._checkpoints[name] = snap
        return snap

    def rollback(self, checkpoint: dict) -> None:
        """No-op: HTTP server state cannot be rolled back via savepoints."""
        pass  # Accepted limitation for external HTTP services

    # ------------------------------------------------------------------ cleanup
    def close(self) -> None:
        self._client.close()


class StripeObserver:
    """Observes mock Stripe API state for VenomQA."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=5.0)
        self._checkpoints: dict[str, dict] = {}

    # ------------------------------------------------------------------ observe
    def observe(self) -> Observation:
        """Fetch current state from the Stripe mock server."""
        try:
            pis_resp = self._client.get("/payment_intents")
            pis = pis_resp.json() if pis_resp.status_code == 200 else []
        except Exception:
            pis = []

        total_charged = sum(pi.get("amount", 0) for pi in pis if pi.get("status") == "succeeded")
        total_refunded = sum(pi.get("refunded_amount", 0) for pi in pis)

        return Observation(
            system="stripe",
            data={
                "payment_intent_count": len(pis),
                "total_charged": total_charged,
                "total_refunded": total_refunded,
            },
        )

    # ------------------------------------------------------------------ checkpoint / rollback
    def checkpoint(self, name: str) -> dict:
        snap = self.observe().data
        self._checkpoints[name] = snap
        return snap

    def rollback(self, checkpoint: dict) -> None:
        pass  # No-op

    # ------------------------------------------------------------------ cleanup
    def close(self) -> None:
        self._client.close()
