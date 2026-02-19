# Examples

Real-world VenomQA examples using the exploration API.

## Example Categories

<div class="grid cards" markdown>

-   :material-database:{ .lg .middle } __CRUD Operations__

    ---

    Complete create→read→update→delete testing with invariants for idempotency, consistency, and state transitions.

    [:octicons-arrow-right-24: CRUD Example](crud.md)

-   :material-shield-account:{ .lg .middle } __Authentication Flows__

    ---

    Login, logout, token refresh, session management, multi-user scenarios, and permission boundary testing.

    [:octicons-arrow-right-24: Auth Example](auth.md)

-   :material-cart:{ .lg .middle } __E-commerce Checkout__

    ---

    Cart management, payment processing, refunds, order state transitions, and inventory validation.

    [:octicons-arrow-right-24: Checkout Example](checkout.md)

</div>

## Core Pattern

All examples follow the same structure:

```
┌─────────────────────────────────────────────────────────────┐
│  1. Define Actions    →  What API calls can be made        │
│  2. Define Invariants →  What rules must always hold       │
│  3. Create World      →  API client + state management     │
│  4. Run Agent         →  Autonomous exploration            │
└─────────────────────────────────────────────────────────────┘
```

## Minimal Example

The simplest exploration setup:

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

def create_item(api, context):
    resp = api.post("/items", json={"name": "test"})
    context.set("item_id", resp.json()["id"])
    return resp

def delete_item(api, context):
    item_id = context.get("item_id")
    if item_id is None:
        return None  # Skip — no item to delete
    return api.delete(f"/items/{item_id}")

api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["item_id"])

agent = Agent(
    world=world,
    actions=[
        Action("create_item", create_item),
        Action("delete_item", delete_item),
    ],
    invariants=[
        Invariant("no_500s", lambda w: w.context.get("last_status", 200) < 500, Severity.CRITICAL),
    ],
    strategy=BFS(),
    max_steps=50,
)

result = agent.explore()
print(f"States: {result.states_visited}, Violations: {len(result.violations)}")
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Action** | One API operation: `(api, context) -> response` |
| **Invariant** | Rule checked after every action: `(world) -> bool` |
| **World** | Sandbox with `api` client and `context` store |
| **Agent** | Orchestrates exploration with a strategy |
| **BFS()** | Breadth-first exploration of all sequences |

## Why These Patterns Work

### Actions Are Stateless Functions

Each action is a pure function of the current state. It receives `api` to make calls and `context` to read/write shared data:

```python
def update_item(api, context):
    item_id = context.get("item_id")
    if item_id is None:
        return None  # Precondition not met — skip this action
    return api.put(f"/items/{item_id}", json={"name": "updated"})
```

Returning `None` tells the agent to skip — the precondition wasn't met.

### Invariants Are Checked After Every Step

Unlike unit tests that assert at the end, VenomQA invariants run after *every single action*:

```python
def no_negative_balance(world):
    balance = world.context.get("balance", 0)
    return balance >= 0

invariant = Invariant("positive_balance", no_negative_balance, Severity.CRITICAL)
```

If `create → refund → refund` makes the balance negative, the invariant fires after the second refund.

### Context Tracks State Between Actions

Use `context.set()` to save values and `context.get()` to retrieve them:

```python
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])
    context.set("order_amount", resp.json()["amount"])
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")
    amount = context.get("order_amount", 0)
    return api.post(f"/orders/{order_id}/refund", json={"amount": amount})
```

### Exploration Tries All Sequences

With BFS, the agent explores:

- `create → read → delete`
- `create → delete → read` (should fail)
- `create → update → delete`
- `create → update → update → delete`

Every path through the state graph gets tested.

## Running Examples

Each example page includes a complete, runnable Python file. To run:

```bash
# 1. Start your API server (or use the mock servers included)
python -m your_api_server

# 2. Run the example
python examples/crud/test_crud.py

# 3. Or use the CLI
venomqa run examples/crud/
```

## Project Structure

Recommended layout for your QA suite:

```
qa/
├── actions/
│   ├── __init__.py
│   ├── items.py      # Item CRUD actions
│   └── users.py      # User management actions
├── invariants/
│   ├── __init__.py
│   └── rules.py      # Domain invariants
├── test_items.py     # Item exploration
├── test_users.py     # User exploration
└── test_checkout.py  # Checkout flow exploration
```

## Next Steps

- [CRUD Operations](crud.md) — Learn the fundamental patterns
- [Authentication Flows](auth.md) — Multi-user stateful testing
- [E-commerce Checkout](checkout.md) — Complex state machines
