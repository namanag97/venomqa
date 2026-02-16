#!/usr/bin/env python3
"""VenomQA v1 API-only Test for Full-Featured App.

Tests all major API endpoints without database adapter.
This is simpler and demonstrates the core v1 API.

Requires:
- App running at http://localhost:8000
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from venomqa.v1 import (
    Agent,
    BFS,
    Action,
    Invariant,
    Severity,
)
from venomqa.v1.world import World
from venomqa.v1.adapters import HttpClient
from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import Rollbackable


# Configuration
API_URL = "http://localhost:8000"


class ApiStateTracker(Rollbackable):
    """Tracks API state for observation and rollback.

    Since API operations are not truly rollbackable in production,
    this tracks what we've observed and allows "soft" rollback
    for testing purposes.
    """

    def __init__(self):
        self._context: dict = {}
        self._checkpoints: dict = {}

    def set(self, key: str, value):
        self._context[key] = value

    def get(self, key: str, default=None):
        return self._context.get(key, default)

    def checkpoint(self, name: str):
        """Save current context state."""
        return dict(self._context)

    def rollback(self, checkpoint):
        """Restore context from checkpoint."""
        self._context = dict(checkpoint)

    def observe(self) -> Observation:
        return Observation(
            system="api_tracker",
            data={
                "keys": list(self._context.keys()),
                "user_id": self._context.get("user_id"),
                "item_id": self._context.get("item_id"),
                "order_id": self._context.get("order_id"),
            },
        )


def create_actions(api: HttpClient, tracker: ApiStateTracker) -> list[Action]:
    """Create all API actions."""

    # Health checks
    def health_check(client: HttpClient):
        return client.get("/health")

    def ready_check(client: HttpClient):
        return client.get("/ready")

    # Users
    def create_user(client: HttpClient):
        result = client.post("/api/users", json={
            "email": f"test_{datetime.now().timestamp()}@example.com",
            "name": "Test User",
            "password": "secret123",
        })
        if result.success and result.response and result.response.status_code == 201:
            tracker.set("user_id", result.response.body.get("id"))
        return result

    def get_user(client: HttpClient):
        user_id = tracker.get("user_id", 1)
        return client.get(f"/api/users/{user_id}")

    # Items
    def create_item(client: HttpClient):
        result = client.post("/api/items", json={
            "name": f"Test Item {datetime.now().timestamp()}",
            "description": "A test item",
            "price": 19.99,
            "quantity": 10,
        })
        if result.success and result.response and result.response.status_code == 201:
            tracker.set("item_id", result.response.body.get("id"))
        return result

    def list_items(client: HttpClient):
        return client.get("/api/items")

    def get_item(client: HttpClient):
        item_id = tracker.get("item_id", 1)
        return client.get(f"/api/items/{item_id}")

    def update_item(client: HttpClient):
        item_id = tracker.get("item_id", 1)
        return client.patch(f"/api/items/{item_id}", json={"price": 24.99})

    # Orders
    def create_order(client: HttpClient):
        user_id = tracker.get("user_id", 1)
        item_id = tracker.get("item_id", 1)
        result = client.post("/api/orders", json={
            "user_id": user_id,
            "item_ids": [item_id],
            "shipping_address": "123 Test St",
        })
        if result.success and result.response and result.response.status_code == 201:
            tracker.set("order_id", result.response.body.get("id"))
        return result

    def get_order(client: HttpClient):
        order_id = tracker.get("order_id", 1)
        return client.get(f"/api/orders/{order_id}")

    # Search
    def search_items(client: HttpClient):
        return client.post("/api/search", json={"query": "test", "limit": 10})

    # Cache
    def get_cached(client: HttpClient):
        return client.get("/api/cached")

    # Time
    def get_time(client: HttpClient):
        return client.get("/api/time")

    # Batch
    def batch_create_items(client: HttpClient):
        return client.post("/api/batch/items", json=[
            {"name": "Batch 1", "price": 9.99, "quantity": 5},
            {"name": "Batch 2", "price": 14.99, "quantity": 3},
        ])

    return [
        Action(name="health_check", execute=health_check, description="GET /health"),
        Action(name="ready_check", execute=ready_check, description="GET /ready"),
        Action(name="create_user", execute=create_user, description="POST /api/users"),
        Action(name="get_user", execute=get_user, description="GET /api/users/{id}"),
        Action(name="create_item", execute=create_item, description="POST /api/items"),
        Action(name="list_items", execute=list_items, description="GET /api/items"),
        Action(name="get_item", execute=get_item, description="GET /api/items/{id}"),
        Action(name="update_item", execute=update_item, description="PATCH /api/items/{id}"),
        Action(name="create_order", execute=create_order, description="POST /api/orders"),
        Action(name="get_order", execute=get_order, description="GET /api/orders/{id}"),
        Action(name="search_items", execute=search_items, description="POST /api/search"),
        Action(name="get_cached", execute=get_cached, description="GET /api/cached"),
        Action(name="get_time", execute=get_time, description="GET /api/time"),
        Action(name="batch_create_items", execute=batch_create_items, description="POST /api/batch/items"),
    ]


def create_invariants(api: HttpClient) -> list[Invariant]:
    """Create API invariants."""

    def health_works(world: World) -> bool:
        result = api.get("/health")
        return result.success and result.response.status_code == 200

    def no_500_errors(world: World) -> bool:
        result = api.get("/health")
        if result.response and result.response.status_code >= 500:
            print(f"    [FAIL] Server error: {result.response.status_code}")
            return False
        return True

    def api_returns_json(world: World) -> bool:
        result = api.get("/health")
        if result.response and result.response.body:
            return isinstance(result.response.body, dict)
        return True

    return [
        Invariant(name="health_works", check=health_works,
                  message="Health endpoint should return 200", severity=Severity.CRITICAL),
        Invariant(name="no_500_errors", check=no_500_errors,
                  message="API should not return 500 errors", severity=Severity.CRITICAL),
        Invariant(name="api_returns_json", check=api_returns_json,
                  message="API should return JSON", severity=Severity.HIGH),
    ]


def generate_mermaid(result) -> str:
    lines = ["graph TD"]
    state_map = {}

    for i, state in enumerate(result.graph.iter_states()):
        label = f"S{i}"
        state_map[state.id] = label
        lines.append(f"    {label}[{label}]")

    for t in result.graph.iter_transitions():
        f = state_map.get(t.from_state_id, "?")
        to = state_map.get(t.to_state_id, "?")
        code = t.result.response.status_code if t.result.response else "err"
        action = t.action_name[:8]
        lines.append(f"    {f} -->|{action}:{code}| {to}")

    return "\n".join(lines)


def main():
    print("=" * 70)
    print("VenomQA v1 - API Exploration Test")
    print("=" * 70)
    print(f"\nTarget: {API_URL}")

    # Create components
    api = HttpClient(base_url=API_URL, timeout=30.0)
    tracker = ApiStateTracker()

    # Create World
    world = World(api=api, systems={"tracker": tracker})

    # Create actions and invariants
    actions = create_actions(api, tracker)
    invariants = create_invariants(api)

    print(f"\nActions: {len(actions)}")
    for a in actions:
        print(f"  - {a.name}: {a.description}")

    print(f"\nInvariants: {len(invariants)}")
    for inv in invariants:
        print(f"  - {inv.name} [{inv.severity.name}]")

    print("\n" + "-" * 70)
    print("Starting exploration (BFS, max_steps=50)")
    print("-" * 70)

    agent = Agent(
        world=world,
        actions=actions,
        invariants=invariants,
        strategy=BFS(),
        max_steps=50,
    )

    try:
        result = agent.explore()
    finally:
        api.close()

    # Results
    print("\n" + "=" * 70)
    print("EXPLORATION RESULTS")
    print("=" * 70)

    print(f"\nStates visited: {result.states_visited}")
    print(f"Transitions taken: {result.transitions_taken}")
    print(f"Coverage: {result.coverage_percent:.1f}%")
    print(f"Duration: {result.duration_ms:.0f}ms")
    print(f"Success: {result.success}")

    print(f"\nViolations: {len(result.violations)}")
    if result.violations:
        for v in result.violations:
            print(f"  [{v.severity.name}] {v.invariant_name}: {v.message}")
    else:
        print("  (no violations)")

    print("\n" + "-" * 70)
    print("Summary:")
    for k, v in result.summary().items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("EXPLORATION GRAPH")
    print("=" * 70)
    print("```mermaid")
    print(generate_mermaid(result))
    print("```")

    print("\n" + "=" * 70)
    if result.success:
        print("ALL INVARIANTS PASSED")
    else:
        print(f"FOUND {len(result.violations)} VIOLATIONS")
    print("=" * 70)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
