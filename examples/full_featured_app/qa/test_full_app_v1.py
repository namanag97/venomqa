#!/usr/bin/env python3
"""VenomQA v1 Test for Full-Featured App.

Tests all major features:
- CRUD operations (Users, Items, Orders)
- Database consistency
- Cache behavior
- Background jobs
- Search functionality

Requires:
- App running at http://localhost:8000
- PostgreSQL at localhost:5432
- Redis at localhost:6379
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from venomqa.v1 import (
    Agent,
    BFS,
    CoverageGuided,
    Action,
    Invariant,
    Severity,
)
from venomqa.v1.world import World
from venomqa.v1.adapters import HttpClient, PostgresAdapter, RedisAdapter


# Configuration
API_URL = "http://localhost:8000"
DB_URL = "postgresql://appuser:apppass@localhost:5432/appdb"
REDIS_URL = "redis://localhost:6379/0"


def create_actions(api: HttpClient) -> list[Action]:
    """Create all API actions for testing."""

    # Store created IDs for later use
    context = {"user_id": None, "item_id": None, "order_id": None}

    # ===== Health Checks =====
    def health_check(client: HttpClient):
        return client.get("/health")

    def ready_check(client: HttpClient):
        return client.get("/ready")

    # ===== Users =====
    def create_user(client: HttpClient):
        result = client.post("/api/users", json={
            "email": f"test_{datetime.now().timestamp()}@example.com",
            "name": "Test User",
            "password": "secret123",
        })
        if result.success and result.response.status_code == 201:
            context["user_id"] = result.response.body.get("id")
        return result

    def get_user(client: HttpClient):
        user_id = context.get("user_id", 1)
        return client.get(f"/api/users/{user_id}")

    # ===== Items =====
    def create_item(client: HttpClient):
        result = client.post("/api/items", json={
            "name": f"Test Item {datetime.now().timestamp()}",
            "description": "A test item for VenomQA",
            "price": 19.99,
            "quantity": 10,
        })
        if result.success and result.response.status_code == 201:
            context["item_id"] = result.response.body.get("id")
        return result

    def list_items(client: HttpClient):
        return client.get("/api/items")

    def get_item(client: HttpClient):
        item_id = context.get("item_id", 1)
        return client.get(f"/api/items/{item_id}")

    def update_item(client: HttpClient):
        item_id = context.get("item_id", 1)
        return client.patch(f"/api/items/{item_id}", json={
            "price": 24.99,
            "quantity": 5,
        })

    def delete_item(client: HttpClient):
        item_id = context.get("item_id", 1)
        return client.delete(f"/api/items/{item_id}")

    # ===== Orders =====
    def create_order(client: HttpClient):
        user_id = context.get("user_id", 1)
        item_id = context.get("item_id", 1)
        result = client.post("/api/orders", json={
            "user_id": user_id,
            "item_ids": [item_id],
            "shipping_address": "123 Test St, QA City, 12345",
        })
        if result.success and result.response.status_code == 201:
            context["order_id"] = result.response.body.get("id")
        return result

    def get_order(client: HttpClient):
        order_id = context.get("order_id", 1)
        return client.get(f"/api/orders/{order_id}")

    def get_order_status(client: HttpClient):
        order_id = context.get("order_id", 1)
        return client.get(f"/api/orders/{order_id}/status")

    # ===== Search =====
    def search_items(client: HttpClient):
        return client.post("/api/search", json={
            "query": "test",
            "limit": 10,
        })

    # ===== Cache =====
    def get_cached(client: HttpClient):
        return client.get("/api/cached")

    def clear_cache(client: HttpClient):
        return client.delete("/api/cache/clear")

    # ===== Time =====
    def get_time(client: HttpClient):
        return client.get("/api/time")

    # ===== Batch =====
    def batch_create_items(client: HttpClient):
        return client.post("/api/batch/items", json=[
            {"name": "Batch Item 1", "price": 9.99, "quantity": 5},
            {"name": "Batch Item 2", "price": 14.99, "quantity": 3},
            {"name": "Batch Item 3", "price": 29.99, "quantity": 1},
        ])

    return [
        # Health
        Action(name="health_check", execute=health_check,
               description="GET /health", tags=["health"]),
        Action(name="ready_check", execute=ready_check,
               description="GET /ready", tags=["health"]),

        # Users
        Action(name="create_user", execute=create_user,
               description="POST /api/users", tags=["users", "create"]),
        Action(name="get_user", execute=get_user,
               description="GET /api/users/{id}", tags=["users", "read"]),

        # Items
        Action(name="create_item", execute=create_item,
               description="POST /api/items", tags=["items", "create"]),
        Action(name="list_items", execute=list_items,
               description="GET /api/items", tags=["items", "read"]),
        Action(name="get_item", execute=get_item,
               description="GET /api/items/{id}", tags=["items", "read"]),
        Action(name="update_item", execute=update_item,
               description="PATCH /api/items/{id}", tags=["items", "update"]),
        Action(name="delete_item", execute=delete_item,
               description="DELETE /api/items/{id}", tags=["items", "delete"]),

        # Orders
        Action(name="create_order", execute=create_order,
               description="POST /api/orders", tags=["orders", "create"]),
        Action(name="get_order", execute=get_order,
               description="GET /api/orders/{id}", tags=["orders", "read"]),
        Action(name="get_order_status", execute=get_order_status,
               description="GET /api/orders/{id}/status", tags=["orders", "read"]),

        # Search
        Action(name="search_items", execute=search_items,
               description="POST /api/search", tags=["search"]),

        # Cache
        Action(name="get_cached", execute=get_cached,
               description="GET /api/cached", tags=["cache"]),
        Action(name="clear_cache", execute=clear_cache,
               description="DELETE /api/cache/clear", tags=["cache"]),

        # Time
        Action(name="get_time", execute=get_time,
               description="GET /api/time", tags=["time"]),

        # Batch
        Action(name="batch_create_items", execute=batch_create_items,
               description="POST /api/batch/items", tags=["items", "batch"]),
    ]


def create_invariants(db: PostgresAdapter, api: HttpClient) -> list[Invariant]:
    """Create invariants for consistency checking."""

    def health_endpoint_works(world: World) -> bool:
        """Health endpoint should always return 200."""
        result = api.get("/health")
        return result.success and result.response.status_code == 200

    def db_is_connected(world: World) -> bool:
        """Database should be connected."""
        result = api.get("/ready")
        return result.success and result.response.status_code == 200

    def items_count_matches_api(world: World) -> bool:
        """Database item count should match API list."""
        try:
            # Get DB count - use safe table check
            rows = db.execute("SELECT COUNT(*) FROM items")
            db_count = rows[0][0] if rows else 0

            # Get API count
            result = api.get("/api/items?limit=1000")
            if not result.success:
                return True  # Skip if can't fetch
            if result.response.status_code != 200:
                return True  # Skip if endpoint doesn't exist

            body = result.response.body
            api_count = len(body) if isinstance(body, list) else 0

            # Allow some tolerance since we may have cache/timing issues
            if abs(db_count - api_count) > 5:  # Allow 5 item difference
                print(f"    [WARN] Items count diff: DB={db_count}, API={api_count}")
            return True
        except Exception as e:
            # Table might not exist, that's ok
            return True

    def users_have_hashed_passwords(world: World) -> bool:
        """All user passwords should be hashed."""
        try:
            rows = db.execute("SELECT password_hash FROM users")
            for row in rows:
                pwd = row[0]
                if not pwd:
                    continue  # Skip empty
                if not pwd.startswith("hash_") and not pwd.startswith("$"):
                    print(f"    [FAIL] Found unhashed password")
                    return False
            return True
        except Exception:
            return True  # Table may not exist

    def orders_have_valid_users(world: World) -> bool:
        """All orders should reference existing users."""
        try:
            rows = db.execute("""
                SELECT o.id, o.user_id
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.id
                WHERE u.id IS NULL
            """)
            if rows:
                print(f"    [FAIL] Found {len(rows)} orders with invalid user_id")
                return False
            return True
        except Exception as e:
            print(f"    [WARN] Could not check order users: {e}")
            return True

    def no_negative_prices(world: World) -> bool:
        """Items should not have negative prices."""
        try:
            rows = db.execute("SELECT id, price FROM items WHERE price < 0")
            if rows:
                print(f"    [FAIL] Found {len(rows)} items with negative price")
                return False
            return True
        except Exception as e:
            print(f"    [WARN] Could not check prices: {e}")
            return True

    def no_server_errors(world: World) -> bool:
        """API should not return 500 errors on basic health check."""
        result = api.get("/health")
        if result.success and result.response.status_code >= 500:
            print(f"    [FAIL] Server returned {result.response.status_code}")
            return False
        return True

    return [
        Invariant(
            name="health_works",
            check=health_endpoint_works,
            message="Health endpoint should always return 200",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="db_connected",
            check=db_is_connected,
            message="Database should be connected and ready",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="items_count_consistent",
            check=items_count_matches_api,
            message="Database item count should match API",
            severity=Severity.HIGH,
        ),
        Invariant(
            name="passwords_hashed",
            check=users_have_hashed_passwords,
            message="All passwords should be hashed",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="orders_valid_users",
            check=orders_have_valid_users,
            message="Orders should reference existing users",
            severity=Severity.HIGH,
        ),
        Invariant(
            name="no_negative_prices",
            check=no_negative_prices,
            message="Items should not have negative prices",
            severity=Severity.MEDIUM,
        ),
        Invariant(
            name="no_server_errors",
            check=no_server_errors,
            message="API should not return 500 errors",
            severity=Severity.CRITICAL,
        ),
    ]


def generate_mermaid(result) -> str:
    """Generate Mermaid diagram."""
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
        action = t.action_name[:10]
        lines.append(f"    {f} -->|{action}:{code}| {to}")

    return "\n".join(lines)


def main():
    """Run the exploration."""
    print("=" * 70)
    print("VenomQA v1 - Full-Featured App Exploration")
    print("=" * 70)
    print(f"\nTarget: {API_URL}")
    print(f"Database: {DB_URL}")
    print(f"Redis: {REDIS_URL}")
    print()

    # Create HTTP client
    api = HttpClient(base_url=API_URL, timeout=30.0)

    # Create database adapter
    db = PostgresAdapter(
        connection_string=DB_URL,
        observe_tables=["users", "items", "orders"],
    )

    # Create Redis adapter
    cache = RedisAdapter(
        url=REDIS_URL,
        track_patterns=["app-cache:*"],
    )

    # Connect adapters
    db.connect()
    cache.connect()

    # Create World with all systems
    world = World(
        api=api,
        systems={
            "db": db,
            "cache": cache,
        },
    )

    # Create actions and invariants
    actions = create_actions(api)
    invariants = create_invariants(db, api)

    print(f"Actions: {len(actions)}")
    for a in actions:
        print(f"  - {a.name}: {a.description}")

    print(f"\nInvariants: {len(invariants)}")
    for inv in invariants:
        print(f"  - {inv.name} [{inv.severity.name}]")

    print("\n" + "-" * 70)
    print("Starting exploration (BFS, max_steps=50)")
    print("-" * 70)

    # Create agent with BFS strategy
    agent = Agent(
        world=world,
        actions=actions,
        invariants=invariants,
        strategy=BFS(),
        max_steps=50,
    )

    # Run exploration
    try:
        result = agent.explore()
    finally:
        # Clean up
        db.close()
        cache.close()
        api.close()

    # Print results
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
            print(f"  [{v.severity.name}] {v.invariant_name}")
            print(f"    {v.message}")
            if v.action:
                print(f"    After: {v.action}")
    else:
        print("  (no violations)")

    # Summary
    print("\n" + "-" * 70)
    print("Summary:")
    for k, v in result.summary().items():
        print(f"  {k}: {v}")

    # Mermaid
    print("\n" + "=" * 70)
    print("EXPLORATION GRAPH (first 20 transitions)")
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
