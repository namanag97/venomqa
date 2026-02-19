"""Sample VenomQA exploration (v1 API).

Demonstrates basic CRUD exploration -- VenomQA tries every sequence of
actions and checks the invariants after each step.

CRITICAL: VenomQA needs database rollback to explore state graphs.
Without it, VenomQA can only test ONE linear path. See options below.

Run with: python3 journeys/sample_journey.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so 'from actions...' imports work when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from venomqa import Action, Invariant, Agent, World, BFS, DFS, Severity
from venomqa.adapters.http import HttpClient

from actions.sample_actions import (
    health_check, list_items, create_item, get_item, delete_item
)


# --- Invariants: rules that must always hold -----------------------------------

def list_always_returns_array(world):
    """GET /api/items must always return a JSON array.

    GOOD PATTERN: Make a live API call to verify server state.
    Don't just check context - the server might be inconsistent.
    """
    resp = world.api.get("/api/items")
    if resp.status_code != 200:
        return False  # Invariant failed: API is broken
    data = resp.json()
    return isinstance(data, list)


def item_count_matches_server(world):
    """Context item_count must match actual server count.

    GOOD PATTERN: Cross-check client state against server state.
    This catches bugs where the client thinks something happened but it didn't.
    """
    expected = world.context.get("item_count")
    if expected is None:
        return True  # list_items hasn't run yet

    resp = world.api.get("/api/items")
    if resp.status_code != 200:
        return False
    actual = len(resp.json())
    return actual == expected


def deleted_item_not_retrievable(world):
    """After delete, the item should return 404.

    GOOD PATTERN: Test negative conditions, not just positive.
    """
    # Only check if we just deleted something
    if world.context.has("item_id"):
        return True  # Item still exists, nothing to check

    # If we had an item_id but it's now gone, verify server agrees
    deleted_id = world.context.get("_last_deleted_id")
    if deleted_id is None:
        return True

    resp = world.api.get(f"/api/items/{deleted_id}")
    return resp.status_code == 404


# --- Database setup ------------------------------------------------------------
#
# VenomQA explores state graphs by ROLLING BACK the database after each branch.
# You MUST connect to the SAME database your API uses.
#
# Choose ONE of these options:

def setup_with_postgres():
    """Option 1: PostgreSQL (most common for production APIs)"""
    from venomqa.adapters.postgres import PostgresAdapter

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: Set DATABASE_URL to your PostgreSQL connection string")
        print("  export DATABASE_URL='postgresql://user:pass@localhost:5432/yourdb'")
        sys.exit(1)

    api = HttpClient("http://localhost:8000")
    db = PostgresAdapter(db_url)

    # CRITICAL: use DFS() with PostgreSQL (BFS doesn't work with PG savepoints)
    return World(api=api, systems={"db": db}), DFS()


def setup_with_sqlite():
    """Option 2: SQLite (simpler, works with BFS)"""
    from venomqa.adapters.sqlite import SQLiteAdapter

    db_path = os.environ.get("SQLITE_PATH", "/path/to/your/api.db")

    api = HttpClient("http://localhost:8000")
    db = SQLiteAdapter(db_path)

    return World(api=api, systems={"db": db}), BFS()


def setup_with_context_only():
    """Option 3: No database - uses context for state identity.

    WARNING: This is a LIMITED mode for APIs that don't have a database.
    State exploration is based on context values only, not actual DB state.
    Use this only if your API is stateless or you're just testing the basics.
    """
    api = HttpClient("http://localhost:8000")

    # Track these context keys to distinguish states
    # Each unique combination = a different state
    return World(
        api=api,
        state_from_context=["item_id", "item_count"],  # context-based state
    ), BFS()


# --- Run exploration -----------------------------------------------------------

if __name__ == "__main__":
    # CHANGE THIS: Pick your setup based on your database
    # world, strategy = setup_with_postgres()
    # world, strategy = setup_with_sqlite()
    world, strategy = setup_with_context_only()  # Default: limited mode

    # Check if API is reachable before starting
    print("Checking API connectivity...")
    try:
        resp = world.api.get("/health")
        if resp.status_code >= 500:
            print()
            print("ERROR: API is not healthy")
            print(f"  GET /health returned {resp.status_code}")
            print()
            print("This sample expects a running API at http://localhost:8000")
            print()
            print("To customize for YOUR API:")
            print("  1. Edit actions/sample_actions.py - change endpoints")
            print("  2. Edit this file - update action list")
            print()
            sys.exit(1)
    except Exception as e:
        print()
        print("ERROR: Cannot connect to API at http://localhost:8000")
        print(f"  {e}")
        print()
        print("Either:")
        print("  1. Start your API: docker compose up")
        print("  2. Or customize actions/sample_actions.py for your API")
        print()
        sys.exit(1)

    print("API is reachable. Starting exploration...")
    print()

    agent = Agent(
        world=world,
        actions=[
            Action(name="health_check", execute=health_check, expected_status=[200]),
            Action(name="list_items",   execute=list_items,   expected_status=[200]),
            Action(name="create_item",  execute=create_item,  expected_status=[200, 201]),
            Action(
                name="get_item",
                execute=get_item,
                expected_status=[200],
                preconditions=["create_item"],  # Only run after create_item
            ),
            Action(
                name="delete_item",
                execute=delete_item,
                preconditions=["create_item"],  # Only run after create_item
            ),
        ],
        invariants=[
            Invariant(
                name="list_returns_array",
                check=list_always_returns_array,
                message="GET /api/items must return JSON array",
                severity=Severity.CRITICAL,
            ),
            Invariant(
                name="count_matches_server",
                check=item_count_matches_server,
                message="Client item_count must match server",
                severity=Severity.HIGH,
            ),
            Invariant(
                name="deleted_is_404",
                check=deleted_item_not_retrievable,
                message="Deleted items must return 404",
                severity=Severity.HIGH,
            ),
        ],
        strategy=strategy,
        max_steps=200,
        progress_every=20,  # Print progress every 20 steps
    )

    print("Starting exploration...")
    print(f"  Strategy: {type(strategy).__name__}")
    print(f"  Max steps: {agent.max_steps}")
    print()

    result = agent.explore()

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  States visited    : {result.states_visited}")
    print(f"  Transitions       : {result.transitions_taken}")
    print(f"  Action coverage   : {result.action_coverage_percent:.0f}%")
    print(f"  Duration          : {result.duration_ms:.0f}ms")
    print(f"  Violations        : {len(result.violations)}")

    if result.violations:
        print()
        print("VIOLATIONS FOUND:")
        for v in result.violations:
            print(f"  [{v.severity.value.upper()}] {v.invariant_name}")
            print(f"      {v.message}")
    else:
        print()
        print("All invariants passed.")

    # Exit with error if violations found (useful for CI)
    sys.exit(1 if result.violations else 0)
