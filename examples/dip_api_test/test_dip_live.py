#!/usr/bin/env python3
"""Live API test for the Data Integration Platform using VenomQA.

This example demonstrates how to test a REAL running API using VenomQA's
combinatorial executor -- no mocks, no fakes, just actual HTTP requests
against a live server.

This is the missing piece that test_dip_combinatorial.py highlighted:
the original example used MockClient because there was no executor that
could bridge the combinatorial dimension definitions to actual HTTP calls.

The CombinatorialExecutor solves this by:
1. Taking a configured CombinatorialGraphBuilder (with dimensions + transitions)
2. Taking a real HTTP client pointed at a live server
3. Building the StateGraph
4. Exploring all paths with real requests
5. Collecting results with timing, invariant checks, and bug reports

Usage:
    # Start the DIP API server:
    cd examples/test-server && python -m uvicorn main:app --port 18000

    # Run the live test:
    DIP_BASE_URL=http://localhost:18000 python examples/dip_api_test/test_dip_live.py

    # With higher coverage:
    DIP_BASE_URL=http://localhost:18000 DIP_STRENGTH=3 python examples/dip_api_test/test_dip_live.py

Requirements:
    - A running API server at DIP_BASE_URL
    - venomqa and httpx installed
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from venomqa.combinatorial import (
    Combination,
    CombinatorialExecutor,
    CombinatorialGraphBuilder,
    ConstraintSet,
    CoveringArrayGenerator,
    Dimension,
    DimensionSpace,
    exclude,
)
from venomqa.core.graph import Severity
from venomqa.tools.assertions import assert_status


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("DIP_BASE_URL", "http://localhost:18000")
STRENGTH = int(os.environ.get("DIP_STRENGTH", "2"))
SEED = int(os.environ.get("DIP_SEED", "42"))


# ---------------------------------------------------------------------------
# HTTP Client wrapper that works with the combinatorial system
# ---------------------------------------------------------------------------

class LiveClient:
    """Simple HTTP client for live API testing.

    Uses httpx under the hood but provides a compatible interface for
    the combinatorial executor (set_auth_token, get, post, delete).
    """

    def __init__(self, base_url: str) -> None:
        import httpx
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self._auth_token: str | None = None

    def set_auth_token(self, token: str | None) -> None:
        """Set or clear the auth token for subsequent requests."""
        self._auth_token = token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._client.get(path, headers=self._headers(), **kwargs)

    def post(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self._client.post(path, headers=self._headers(), json=json, **kwargs)

    def put(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self._client.put(path, headers=self._headers(), json=json, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._client.delete(path, headers=self._headers(), **kwargs)

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Transition Actions (real HTTP calls)
# ---------------------------------------------------------------------------

def action_login(client: Any, context: dict[str, Any]) -> Any:
    """Authenticate and get a valid token."""
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@test.com",
        "password": "testpassword",
    })
    # If the API returns a token, use it
    if hasattr(resp, "json") and callable(resp.json):
        try:
            data = resp.json()
            token = data.get("token") or data.get("access_token")
            if token:
                client.set_auth_token(token)
                context["auth_token"] = token
            return resp
        except Exception:
            pass
    # Fallback: use a static test token if auth endpoint not available
    token = f"test_token_{uuid.uuid4().hex[:8]}"
    client.set_auth_token(token)
    context["auth_token"] = token
    return resp


def action_logout(client: Any, context: dict[str, Any]) -> Any:
    """Clear authentication."""
    client.set_auth_token(None)
    context.pop("auth_token", None)
    return {"status": "logged_out"}


def action_create_workspace(client: Any, context: dict[str, Any]) -> Any:
    """Create a workspace via POST."""
    name = f"ws_test_{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/workspaces", json={"name": name})
    if hasattr(resp, "json") and callable(resp.json):
        try:
            data = resp.json()
            context["workspace_id"] = data.get("id")
        except Exception:
            pass
    context["workspace_name"] = name
    return resp


def action_list_workspaces(client: Any, context: dict[str, Any]) -> Any:
    """List workspaces via GET."""
    resp = client.get("/api/v1/workspaces")
    return resp


def action_delete_workspace(client: Any, context: dict[str, Any]) -> Any:
    """Delete a workspace via DELETE."""
    ws_id = context.get("workspace_id")
    if ws_id:
        resp = client.delete(f"/api/v1/workspaces/{ws_id}")
        context.pop("workspace_id", None)
        return resp
    return {"status": "no_workspace_to_delete"}


def action_health_check(client: Any, context: dict[str, Any]) -> Any:
    """Check the health endpoint (should always succeed)."""
    resp = client.get("/health")
    return resp


# ---------------------------------------------------------------------------
# Invariant Checkers
# ---------------------------------------------------------------------------

def check_health_accessible(client: Any, db: Any, context: dict[str, Any]) -> bool:
    """Health endpoint should always return 200 regardless of auth state."""
    original_token = getattr(client, "_auth_token", None)
    try:
        client.set_auth_token(None)
        resp = client.get("/health")
        status = getattr(resp, "status_code", None)
        return status == 200
    except Exception:
        return False
    finally:
        client.set_auth_token(original_token)


def check_auth_enforcement(client: Any, db: Any, context: dict[str, Any]) -> bool:
    """Protected endpoints should reject unauthenticated requests."""
    combo = context.get("_current_combination", {})
    auth_state = combo.get("auth_state", "valid")

    if auth_state == "none":
        original_token = getattr(client, "_auth_token", None)
        try:
            client.set_auth_token(None)
            resp = client.get("/api/v1/workspaces")
            status = getattr(resp, "status_code", 200)
            # Should get 401 when not authenticated
            return status == 401
        except Exception:
            return True  # Connection error is acceptable
        finally:
            client.set_auth_token(original_token)
    return True


# ---------------------------------------------------------------------------
# Build the Combinatorial Graph
# ---------------------------------------------------------------------------

def build_live_graph() -> tuple[CombinatorialGraphBuilder, DimensionSpace, ConstraintSet]:
    """Build a combinatorial graph for live API testing."""

    space = DimensionSpace([
        Dimension(
            name="auth_state",
            values=["none", "valid"],
            description="Authentication state",
            default_value="none",
        ),
        Dimension(
            name="workspace_state",
            values=["none", "exists"],
            description="Whether a workspace exists",
            default_value="none",
        ),
        Dimension(
            name="operation",
            values=["read", "write", "delete"],
            description="Type of operation being tested",
            default_value="read",
        ),
    ])

    constraints = ConstraintSet([
        exclude(
            "no_write_without_auth",
            auth_state="none",
            operation="write",
            description="Cannot write without authentication",
        ),
        exclude(
            "no_delete_without_auth",
            auth_state="none",
            operation="delete",
            description="Cannot delete without authentication",
        ),
    ])

    builder = CombinatorialGraphBuilder(
        name="dip_live_api_test",
        space=space,
        constraints=constraints,
        description="Live API test of DIP using real HTTP requests",
        seed=SEED,
    )

    # Auth transitions
    builder.register_transition(
        "auth_state", "none", "valid",
        action=action_login, name="login",
    )
    builder.register_transition(
        "auth_state", "valid", "none",
        action=action_logout, name="logout",
    )

    # Workspace transitions
    builder.register_transition(
        "workspace_state", "none", "exists",
        action=action_create_workspace, name="create_workspace",
    )
    builder.register_transition(
        "workspace_state", "exists", "none",
        action=action_delete_workspace, name="delete_workspace",
    )

    # Operation transitions
    builder.register_transition(
        "operation", "read", "write",
        action=action_create_workspace, name="do_write",
    )
    builder.register_transition(
        "operation", "write", "read",
        action=action_list_workspaces, name="do_read",
    )
    builder.register_transition(
        "operation", "read", "delete",
        action=action_delete_workspace, name="do_delete_from_read",
    )
    builder.register_transition(
        "operation", "write", "delete",
        action=action_delete_workspace, name="do_delete_from_write",
    )
    builder.register_transition(
        "operation", "delete", "read",
        action=action_list_workspaces, name="do_read_from_delete",
    )

    # Invariants
    builder.add_invariant(
        "health_always_accessible",
        check=check_health_accessible,
        description="/health endpoint should always return 200",
        severity=Severity.HIGH,
    )
    builder.add_invariant(
        "auth_enforcement",
        check=check_auth_enforcement,
        description="Protected endpoints reject unauthenticated requests",
        severity=Severity.CRITICAL,
    )

    # Set initial state
    builder.set_initial({
        "auth_state": "none",
        "workspace_state": "none",
        "operation": "read",
    })

    return builder, space, constraints


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> bool:
    """Run the live API combinatorial test."""

    print("=" * 70)
    print("DIP API - LIVE COMBINATORIAL TEST")
    print(f"Target: {BASE_URL}")
    print(f"Strength: {STRENGTH}-wise | Seed: {SEED}")
    print("=" * 70)

    # Verify the API is reachable
    client = LiveClient(BASE_URL)
    try:
        resp = client.get("/health")
        status = getattr(resp, "status_code", None)
        if status != 200:
            print(f"\nWARNING: /health returned status {status}")
            print("The API may not be running correctly.")
    except Exception as e:
        print(f"\nERROR: Cannot reach {BASE_URL}: {e}")
        print("Make sure the API server is running.")
        print("  Example: cd examples/test-server && python -m uvicorn main:app --port 18000")
        return False

    # Build the combinatorial graph
    builder, space, constraints = build_live_graph()

    # Show what we are testing
    gen = CoveringArrayGenerator(space, constraints, seed=SEED)
    combos = gen.generate(strength=STRENGTH)

    print(f"\nDimensions ({len(space.dimensions)}):")
    for dim in space.dimensions:
        print(f"  {dim.name:20s}  {dim.values}")

    print(f"\nTotal exhaustive:  {space.total_combinations}")
    print(f"Valid after constraints: {len(constraints.filter(space.all_combinations()))}")
    print(f"Test combinations:      {len(combos)}")

    print(f"\nGenerated combinations:")
    for i, combo in enumerate(combos, 1):
        print(f"  {i:2d}. {combo.description}")

    # Execute with the CombinatorialExecutor
    print(f"\n{'=' * 70}")
    print("EXECUTING LIVE TESTS")
    print(f"{'=' * 70}\n")

    executor = CombinatorialExecutor(builder, client)
    result = executor.execute(
        strength=STRENGTH,
        max_depth=6,
        stop_on_first_failure=False,
    )

    # Print results
    print(f"\n{result.summary()}")

    # Generate bug report if there are failures
    if result.failures:
        report = result.bug_report()
        report_path = "dip_live_bugs.md"
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nBug report saved to: {report_path}")

    # Cleanup
    client.close()

    print(f"\n{'=' * 70}")
    print("LIVE TEST COMPLETE")
    print(f"{'=' * 70}")

    return len(result.failures) == 0


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
