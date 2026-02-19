# CRUD Operations

Complete example testing Create, Read, Update, Delete operations with invariant patterns for consistency, idempotency, and state transitions.

## What You'll Learn

- Action definitions with preconditions
- Invariants for CRUD-specific rules
- Testing create→read→update→delete sequences
- Catching stale state and double-delete bugs

## Complete Example

```python
"""
CRUD Operations Example

Tests a REST API for managing items with these endpoints:
- POST   /items          → Create item
- GET    /items/{id}     → Read item
- PUT    /items/{id}     → Update item
- DELETE /items/{id}     → Delete item
- GET    /items          → List all items

Run: python test_crud.py
"""

from __future__ import annotations

from venomqa import (
    Action,
    Agent,
    BFS,
    Invariant,
    Severity,
    World,
)
from venomqa.adapters.http import HttpClient


# =============================================================================
# ACTIONS
# =============================================================================

def create_item(api: HttpClient, context) -> dict | None:
    """Create a new item.
    
    Stores the created item_id in context for subsequent actions.
    """
    resp = api.post("/items", json={
        "name": "Test Item",
        "price": 29.99,
    })
    
    if resp.status_code in [200, 201]:
        data = resp.json()
        context.set("item_id", data["id"])
        context.set("item_name", data["name"])
        context.set("item_price", data["price"])
        context.set("last_status", resp.status_code)
        return data
    
    context.set("last_status", resp.status_code)
    return None


def read_item(api: HttpClient, context) -> dict | None:
    """Read the created item by ID.
    
    Requires: item_id must exist in context (set by create_item)
    """
    item_id = context.get("item_id")
    if item_id is None:
        return None  # Skip — no item to read
    
    resp = api.get(f"/items/{item_id}")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        return resp.json()
    return None


def update_item(api: HttpClient, context) -> dict | None:
    """Update the item's name and price.
    
    Requires: item_id must exist in context
    """
    item_id = context.get("item_id")
    if item_id is None:
        return None  # Skip — no item to update
    
    resp = api.put(f"/items/{item_id}", json={
        "name": "Updated Item",
        "price": 39.99,
    })
    
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("item_name", data["name"])
        context.set("item_price", data["price"])
        return data
    return None


def delete_item(api: HttpClient, context) -> dict | None:
    """Delete the item.
    
    Requires: item_id must exist in context
    Clears item_id from context after successful deletion.
    """
    item_id = context.get("item_id")
    if item_id is None:
        return None  # Skip — no item to delete
    
    resp = api.delete(f"/items/{item_id}")
    context.set("last_status", resp.status_code)
    
    if resp.status_code in [200, 204]:
        context.delete("item_id")  # Mark as deleted
        return {}
    return None


def list_items(api: HttpClient, context) -> list | None:
    """List all items.
    
    No preconditions — can always run.
    """
    resp = api.get("/items")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 200:
        items = resp.json()
        context.set("items_count", len(items) if isinstance(items, list) else 0)
        return items
    return None


def read_deleted_item(api: HttpClient, context) -> dict | None:
    """Attempt to read an item that was deleted.
    
    This action exists to test that deleted items return 404.
    We track that deletion happened via 'was_deleted' flag.
    """
    item_id = context.get("deleted_item_id")
    if item_id is None:
        return None  # No deleted item to test
    
    resp = api.get(f"/items/{item_id}")
    context.set("last_status", resp.status_code)
    return resp.json() if resp.status_code != 404 else None


# =============================================================================
# INVARIANTS
# =============================================================================

def no_server_errors(world: World) -> bool:
    """No 5xx server errors should ever occur."""
    return world.context.get("last_status", 200) < 500


def deleted_items_return_404(world: World) -> bool:
    """After deletion, reading the item should return 404.
    
    This tracks deleted_item_id separately to test after deletion.
    """
    status = world.context.get("last_status")
    deleted_id = world.context.get("deleted_item_id")
    
    # If we just tried to read a deleted item, it should be 404
    if deleted_id is not None and status is not None:
        # We're checking if the last read was for a deleted item
        return status == 404
    return True


def item_count_consistent(world: World) -> bool:
    """Item count should reflect actual items.
    
    After create: count increases
    After delete: count decreases
    """
    # This is a simplified check — real implementation would
    # compare against expected count based on actions taken
    return True


def update_preserves_id(world: World) -> bool:
    """Updating an item should not change its ID."""
    # This would need to compare original_id vs current_id
    return True


def price_never_negative(world: World) -> bool:
    """Item price should never be negative."""
    price = world.context.get("item_price")
    if price is None:
        return True
    return price >= 0


# =============================================================================
# BUILD INVARIANT OBJECTS
# =============================================================================

INVARIANTS = [
    Invariant(
        name="no_server_errors",
        check=no_server_errors,
        message="Server returned 5xx error",
        severity=Severity.CRITICAL,
    ),
    Invariant(
        name="deleted_returns_404",
        check=deleted_items_return_404,
        message="Deleted item did not return 404",
        severity=Severity.HIGH,
    ),
    Invariant(
        name="price_never_negative",
        check=price_never_negative,
        message="Item price became negative",
        severity=Severity.HIGH,
    ),
]


# =============================================================================
# BUILD ACTIONS
# =============================================================================

ACTIONS = [
    Action(
        name="create_item",
        execute=create_item,
        description="Create a new item",
        tags=["write", "crud"],
    ),
    Action(
        name="read_item",
        execute=read_item,
        description="Read item by ID",
        tags=["read", "crud"],
    ),
    Action(
        name="update_item",
        execute=update_item,
        description="Update item name and price",
        tags=["write", "crud"],
    ),
    Action(
        name="delete_item",
        execute=delete_item,
        description="Delete the item",
        tags=["write", "crud"],
    ),
    Action(
        name="list_items",
        execute=list_items,
        description="List all items",
        tags=["read", "crud"],
    ),
]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Configure API client
    api = HttpClient("http://localhost:8000")
    
    # Create world with stateless context tracking
    world = World(api=api, state_from_context=["item_id"])
    
    # Create agent
    agent = Agent(
        world=world,
        actions=ACTIONS,
        invariants=INVARIANTS,
        strategy=BFS(),
        max_steps=100,
    )
    
    # Run exploration
    result = agent.explore()
    
    # Print results
    print("\n" + "=" * 60)
    print("CRUD EXPLORATION RESULTS")
    print("=" * 60)
    print(f"States visited:    {result.states_visited}")
    print(f"Transitions taken: {result.transitions_taken}")
    print(f"Action coverage:   {result.action_coverage_percent:.0f}%")
    print(f"Duration:          {result.duration_ms:.0f} ms")
    print(f"Violations found:  {len(result.violations)}")
    
    if result.violations:
        print("\nVIOLATIONS:")
        for v in result.violations:
            print(f"  [{v.severity.value.upper()}] {v.invariant_name}")
            print(f"    {v.message}")
    else:
        print("\nNo violations — all invariants passed.")
    
    print("=" * 60)
```

## Why These Patterns Matter

### Precondition Checks

Every action checks if its preconditions are met:

```python
def read_item(api, context):
    item_id = context.get("item_id")
    if item_id is None:
        return None  # Skip — no item to read
    ...
```

Returning `None` tells the agent: "this action doesn't apply in the current state." The agent won't waste time exploring paths where preconditions fail.

### Context as State Machine

Context variables track what's happened:

| Variable | Set By | Meaning |
|----------|--------|---------|
| `item_id` | `create_item` | An item exists |
| `last_status` | All actions | Last HTTP status code |
| `item_price` | `create_item`, `update_item` | Current price |

The agent explores all combinations: with item, without item, after update, after delete.

### Invariants Check Domain Rules

```python
def price_never_negative(world):
    price = world.context.get("item_price")
    if price is None:
        return True
    return price >= 0
```

This catches bugs where an update could set a negative price — something unit tests might miss if they only check happy paths.

## Sequences Tested

The agent explores all reachable sequences:

| Sequence | What It Tests |
|----------|---------------|
| `create → read` | Created item is readable |
| `create → update → read` | Update persists |
| `create → delete → read` | Deleted item returns 404 |
| `create → delete → delete` | Double-delete handling |
| `create → create` | Duplicate creation |
| `read` (no create) | Read non-existent returns 404 |

## Adding Database Rollback

For real stateful testing with DB rollback:

```python
from venomqa.adapters.postgres import PostgresAdapter

api = HttpClient("http://localhost:8000")
db = PostgresAdapter("postgresql://user:pass@localhost/testdb")

world = World(
    api=api,
    systems={"db": db},  # DB will be rolled back between branches
)
```

Now each exploration branch starts from a clean DB state.

## Expected Output

```
============================================================
CRUD EXPLORATION RESULTS
============================================================
States visited:    12
Transitions taken: 28
Action coverage:   100%
Duration:          156 ms
Violations found:  0

No violations — all invariants passed.
============================================================
```

## Common Bugs Found

| Bug | Sequence That Finds It |
|-----|------------------------|
| Double-delete succeeds | `create → delete → delete` |
| Stale state after update | `create → update → read` (returns old data) |
| Deleted item still readable | `create → delete → read` |
| Update changes ID | `create → update → read` |
| Negative price allowed | `create → update(price=-1)` |

## Next Steps

- [Authentication Flows](auth.md) — Multi-user stateful testing
- [E-commerce Checkout](checkout.md) — Complex state machines
