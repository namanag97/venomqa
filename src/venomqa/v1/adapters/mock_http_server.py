"""MockHTTPServer — base class for in-process mock HTTP servers with checkpoint/rollback.

This class bridges the gap between an in-process mock server (which has a state
dict accessible directly in-process) and VenomQA's Rollbackable protocol.

Key improvements over the HTTPObserver approach:
  - observe() reads state directly from memory — no HTTP round-trips
  - checkpoint() deepcopies the state dict — O(1), not O(n_repos)
  - rollback() restores the dict — enables TRUE branching exploration
  - StripeProxy workaround is eliminated (state dict is picklable)

Usage pattern:

    # In your mock server module (e.g. mock_github.py):

    _state: dict[str, Any] = {"users": {}, "repos": {}, "issues": {}}
    _lock = threading.Lock()

    class GitHubObserver(MockHTTPServer):
        def __init__(self): super().__init__("github")

        @staticmethod
        def reset_state():
            with _lock: _state["users"].clear(); ...

        @staticmethod
        def get_state_snapshot() -> dict:
            with _lock: return {"users": dict(_state["users"]), ...}

        @staticmethod
        def rollback_from_snapshot(snap: dict) -> None:
            with _lock: _state["users"].clear(); _state["users"].update(snap["users"]); ...

        def observe_from_state(self, state: dict) -> Observation:
            return Observation(system="github", data={"user_count": len(state["users"]), ...})

    # In your QA setup:
    github_obs = GitHubObserver()
    world = World(api=github_api, systems={"github": github_obs})
    # No StripeProxy needed — state dict is picklable!
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Any

from venomqa.v1.core.state import Observation


class MockHTTPServer(ABC):
    """Abstract base for in-process mock HTTP servers with real checkpoint/rollback.

    Implements the Rollbackable protocol so VenomQA can do true branching
    exploration — trying action A from state S, rolling back, then trying action B.

    The tradeoff: only works for in-process mock servers (where you can access
    the module-level state dict directly). For real external HTTP services, use
    HTTPObserver (no-op rollback, sequential exploration only).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._saved_checkpoints: dict[str, dict[str, Any]] = {}

    # ---------------------------------------------------------------- abstract

    @staticmethod
    @abstractmethod
    def get_state_snapshot() -> dict[str, Any]:
        """Return a deep-copyable snapshot of the current module-level state.

        Must hold the server's threading.Lock while reading. The returned dict
        must contain only picklable values (str, int, list, dict — no threading
        objects).
        """
        ...

    @staticmethod
    @abstractmethod
    def rollback_from_snapshot(snapshot: dict[str, Any]) -> None:
        """Restore the module-level state dict from a snapshot.

        Must hold the server's threading.Lock while restoring.
        """
        ...

    @abstractmethod
    def observe_from_state(self, state: dict[str, Any]) -> Observation:
        """Convert a state snapshot to a VenomQA Observation.

        This is called with the result of get_state_snapshot(). Compute
        observation metrics (counts, totals, etc.) from the dict — no HTTP calls.
        """
        ...

    # ---------------------------------------------------------------- Rollbackable protocol

    def checkpoint(self, name: str) -> dict[str, Any]:
        """Deepcopy the current server state and store it under name."""
        snap = copy.deepcopy(self.get_state_snapshot())
        self._saved_checkpoints[name] = snap
        return snap

    def rollback(self, checkpoint: dict[str, Any] | None) -> None:
        """Restore the server state from a checkpoint dict.

        Unlike HTTPObserver (which makes this a no-op), MockHTTPServer performs
        a real restore — the module-level _state dict is overwritten with the
        snapshot data. This enables branching exploration.
        """
        if checkpoint and isinstance(checkpoint, dict):
            self.rollback_from_snapshot(checkpoint)

    def observe(self) -> Observation:
        """Read current server state and return as Observation (no HTTP calls)."""
        state = self.get_state_snapshot()
        return self.observe_from_state(state)

    # ---------------------------------------------------------------- compat

    def close(self) -> None:
        """No-op — no HTTP client to close."""
        pass
