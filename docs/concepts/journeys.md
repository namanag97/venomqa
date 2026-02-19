# Journeys

Chain actions together with automatic context flow.

## What Is a Journey?

A **journey** is a sequence of actions that represents a user flow through your application:

```
Login → Create Cart → Add Item → Checkout → Pay
```

In VenomQA, journeys emerge naturally from your action definitions. You don't explicitly define them — the exploration discovers them.

## Context: The Glue Between Actions

The **context** is a key-value store that persists between actions:

```python
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])  # Store
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")  # Retrieve
    if order_id is None:
        return None  # Skip - no order to refund
    return api.post(f"/orders/{order_id}/refund")
```

### How Context Flows

```
Action 1: create_order
  └─ context.set("order_id", "abc123")

Action 2: refund_order
  └─ context.get("order_id") → "abc123"

Action 3: cancel_order
  └─ context.get("order_id") → "abc123"
```

The context survives across actions in the same exploration path.

## Writing Context-Aware Actions

### Pattern 1: Store on Create

```python
def create_user(api, context):
    resp = api.post("/users", json={"email": "test@example.com"})
    context.set("user_id", resp.json()["id"])
    context.set("user_email", resp.json()["email"])
    return resp
```

### Pattern 2: Skip When Missing

```python
def delete_user(api, context):
    user_id = context.get("user_id")
    if user_id is None:
        return None  # No user to delete
    return api.delete(f"/users/{user_id}")
```

### Pattern 3: Derived Values

```python
def get_user_orders(api, context):
    user_id = context.get("user_id")
    if user_id is None:
        return None
    return api.get(f"/users/{user_id}/orders")
```

### Pattern 4: Update Context

```python
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])
    return resp

def pay_order(api, context):
    order_id = context.get("order_id")
    resp = api.post(f"/orders/{order_id}/pay")
    context.set("payment_id", resp.json()["payment_id"])
    return resp
```

## State Extraction

VenomQA can extract state from context to detect duplicate states:

```python
from venomqa import World

world = World(
    api=api,
    state_from_context=["order_id", "user_id"],
)
```

This tells VenomQA: "Two states are identical if they have the same `order_id` and `user_id`."

### Why This Matters

Without state extraction:

```
create_order → [has order] → refund → [refunded]
                              ↓
                        cancel (skip)
                              ↓
                        refund (skip)
```

With state extraction, VenomQA recognizes that revisiting `[has order]` with the same `order_id` is redundant.

## Common Journey Patterns

### CRUD Cycle

```python
actions = [
    Action("create", create_item),   # Sets item_id
    Action("read", read_item),       # Uses item_id
    Action("update", update_item),   # Uses item_id
    Action("delete", delete_item),   # Uses item_id
]
```

Explores: create→read, create→update, create→delete, create→read→update→delete, etc.

### State Machine

```python
actions = [
    Action("create", create_order),
    Action("pay", pay_order),        # Requires: order_id
    Action("ship", ship_order),      # Requires: order_id, paid
    Action("refund", refund_order),  # Requires: order_id
    Action("cancel", cancel_order),  # Requires: order_id
]
```

### Multi-Resource

```python
actions = [
    Action("create_user", create_user),     # Sets user_id
    Action("create_order", create_order),   # Sets order_id
    Action("add_item", add_item),           # Uses order_id
    Action("checkout", checkout),           # Uses order_id
]
```

## Context vs. World State

| Aspect | Context | World State |
|--------|---------|-------------|
| Storage | Key-value dict | Database, files, etc. |
| Scope | Per exploration path | Shared across paths |
| Checkpoint | Copied on branch | Rolled back on branch |
| Use case | IDs, tokens | DB rows, files |

Context is for passing data between actions. World state is for the actual system under test.

## Example: Full E-commerce Journey

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["user_id", "cart_id", "order_id"])

def create_user(api, context):
    resp = api.post("/users", json={"email": "test@example.com"})
    context.set("user_id", resp.json()["id"])
    return resp

def create_cart(api, context):
    user_id = context.get("user_id")
    if user_id is None:
        return None
    resp = api.post(f"/users/{user_id}/carts")
    context.set("cart_id", resp.json()["id"])
    return resp

def add_item(api, context):
    cart_id = context.get("cart_id")
    if cart_id is None:
        return None
    return api.post(f"/carts/{cart_id}/items", json={"sku": "ABC123", "qty": 1})

def checkout(api, context):
    cart_id = context.get("cart_id")
    if cart_id is None:
        return None
    resp = api.post(f"/carts/{cart_id}/checkout")
    context.set("order_id", resp.json()["order_id"])
    return resp

actions = [
    Action("create_user", create_user),
    Action("create_cart", create_cart),
    Action("add_item", add_item),
    Action("checkout", checkout),
]

result = Agent(
    world=world,
    actions=actions,
    invariants=[],
    strategy=BFS(),
    max_steps=50,
).explore()
```

This explores paths like:

- create_user → create_cart → add_item → checkout
- create_user → create_cart → checkout (empty cart?)
- create_user → add_item (no cart - skip)
- etc.

## Next Steps

- [Checkpoints & Branching](branching.md) - Database rollback
- [State Management](state.md) - Context and state extraction
- [Examples](../examples/index.md) - Real-world patterns
