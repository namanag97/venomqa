# Quickstart

Find your first sequence bug in 30 seconds. No setup required.

## Run the Demo

```bash
pip install venomqa
venomqa demo
```

## What You'll See

```
  Unit Tests:  3/3 PASS ✓

  VenomQA Exploration ────────────────────────
  States visited:     8
  Transitions:        20
  Invariants checked: 40

  ╭─ CRITICAL VIOLATION ──────────────────────╮
  │ Sequence: create_order → refund → refund  │
  │ Bug:      refunded $200 on a $100 order   │
  ╰───────────────────────────────────────────╯

  Summary: 3 tests passed. 1 sequence bug found.
  Your tests passed. VenomQA found the bug.
```

The demo runs against a mock API with a planted bug. It demonstrates the core value proposition: **unit tests pass, but sequences fail.**

## What Just Happened

1. **Actions defined**: `create_order`, `refund_order`, `cancel_order`
2. **Invariant defined**: "Total refunds cannot exceed order amount"
3. **Exploration ran**: BFS traversal through all reachable sequences
4. **Bug found**: `create → refund → refund` violated the invariant

The mock API accepts both refunds. Each individual call returns `200 OK`. The bug only surfaces when you call refund twice on the same order.

## Your First Real Test

Create a file `qa/test_api.py`:

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["resource_id"])

def create_item(api, context):
    resp = api.post("/items", json={"name": "test"})
    context.set("resource_id", resp.json()["id"])
    return resp

def delete_item(api, context):
    resource_id = context.get("resource_id")
    if resource_id is None:
        return None
    return api.delete(f"/items/{resource_id}")

no_500s = Invariant(
    "no_server_errors",
    lambda world: world.context.get("last_status", 200) < 500,
    Severity.CRITICAL,
)

result = Agent(
    world=world,
    actions=[
        Action("create_item", create_item),
        Action("delete_item", delete_item),
    ],
    invariants=[no_500s],
    strategy=BFS(),
    max_steps=50,
).explore()

print(f"States: {result.states_visited}, Violations: {result.violations}")
```

Run it:

```bash
python qa/test_api.py
```

## Key Concepts in 60 Seconds

| Concept | What it is | Example |
|---------|------------|---------|
| **Action** | One API call | `create_order`, `refund_order` |
| **Invariant** | Rule that must always hold | `refunds <= order_total` |
| **World** | The sandbox with rollback | `World(api=api, state_from_context=[...])` |
| **Agent** | Orchestrates exploration | `Agent(world, actions, invariants, strategy)` |
| **Strategy** | How to traverse states | `BFS()`, `DFS()`, `CoverageGuided()` |

## Common Patterns

### Skip When Precondition Not Met

```python
def delete_item(api, context):
    resource_id = context.get("resource_id")
    if resource_id is None:
        return None  # Skip - nothing to delete
    return api.delete(f"/items/{resource_id}")
```

### Context Flows Between Actions

```python
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])  # Store for later
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")  # Retrieved automatically
    return api.post(f"/orders/{order_id}/refund")
```

### Invariant Checks State

```python
no_over_refund = Invariant(
    "no_over_refund",
    lambda world: get_total_refunded() <= get_order_total(),
    Severity.CRITICAL,
)
```

## Next Steps

- [Installation](installation.md) - Full setup with database adapters
- [Configuration](configuration.md) - Auth, timeouts, environment
- [Concepts: The Theory](../concepts/theory.md) - Why sequences matter
