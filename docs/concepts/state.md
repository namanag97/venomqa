# State Management

How VenomQA tracks and restores state across exploration paths.

## Two Types of State

VenomQA manages two kinds of state:

| Type | What | Storage | Use Case |
|------|------|---------|----------|
| **Context** | IDs, tokens, references | In-memory dict | Passing data between actions |
| **System State** | Database rows, cache | External systems | The actual app state |

## Context

The context is a simple key-value store that persists across actions:

```python
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")
    return api.post(f"/orders/{order_id}/refund")
```

### Context API

```python
# Set a value
context.set("key", value)

# Get a value (returns None if not set)
value = context.get("key")

# Get with default
value = context.get("key", default="fallback")

# Check if exists
if context.has("key"):
    ...

# Delete a value
context.delete("key")

# Clear all
context.clear()

# Get all keys
keys = context.keys()
```

### Context Checkpointing

When the agent branches, context is automatically copied:

```python
# Original path
context.set("order_id", "A")

# Branch 1
context.set("status", "refunded")  # Has: order_id=A, status=refunded

# Rollback + Branch 2
context.set("status", "canceled")  # Has: order_id=A, status=canceled
# (status=refunded is gone)
```

## State Extraction

State extraction tells VenomQA how to identify "the same state":

```python
world = World(
    api=api,
    state_from_context=["order_id", "user_id"],
)
```

This means: "Two states are identical if `order_id` and `user_id` are the same."

### Why This Matters

Without state extraction:

```
create_order → [order=A]
    → refund → [order=A, refunded=True]
    → rollback
    → refund → [order=A, refunded=True]  ← Explored twice!
```

With state extraction:

```
create_order → [state: order_id=A]
    → refund → [state: order_id=A, refunded=True]
    → (skip: already seen this state)
```

### What to Extract

Extract values that define distinct states:

```python
# Good: Core resource IDs
state_from_context=["user_id", "order_id", "cart_id"]

# Less useful: Transient values
state_from_context=["request_id", "timestamp"]  # Changes every run

# Too coarse: Missing important dimensions
state_from_context=["user_id"]  # Misses order state changes
```

## System State

System state lives in databases, caches, files — anything external to VenomQA.

### With Database Adapters

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter("postgresql://localhost/testdb")
world = World(api=api, systems={"db": db})
```

The adapter handles:

- Checkpoint: `SAVEPOINT vq_xxx`
- Rollback: `ROLLBACK TO SAVEPOINT vq_xxx`
- State query: `SELECT * FROM orders WHERE id = ?`

### Without Database Adapters

If your API is remote or you can't access the DB:

```python
# Use context-only state
world = World(api=api, state_from_context=["order_id"])
```

You lose:

- True rollback (API state persists)
- State deduplication via DB queries
- Invariants that check DB state

But you gain:

- Ability to test remote APIs
- No DB setup required

## State in Invariants

Invariants check state to find bugs:

```python
def check_refund_consistency(world):
    """Refunded amount in API must match database."""
    api_refunded = world.api.get("/orders/123").json()["refunded"]
    db_refunded = world.systems["db"].query(
        "SELECT refunded FROM orders WHERE id = 123"
    )
    return api_refunded == db_refunded

consistency = Invariant(
    "refund_consistency",
    check_refund_consistency,
    Severity.CRITICAL,
)
```

### Common Invariant Patterns

```python
# 1. No 500 errors
no_500s = Invariant(
    "no_server_errors",
    lambda w: w.context.get("last_status", 200) < 500,
    Severity.CRITICAL,
)

# 2. State consistency
consistency = Invariant(
    "api_db_consistency",
    lambda w: get_api_count() == get_db_count(),
    Severity.HIGH,
)

# 3. Business rules
no_over_refund = Invariant(
    "no_over_refund",
    lambda w: get_refunded() <= get_order_total(),
    Severity.CRITICAL,
)

# 4. Idempotency
idempotent = Invariant(
    "create_is_idempotent",
    lambda w: count_orders() == expected_count,
    Severity.MEDIUM,
)
```

## State Serialization

For reproducibility, state can be serialized:

```python
# Get snapshot
snapshot = world.serialize()

# Restore from snapshot
world.deserialize(snapshot)
```

This enables:

- Recording/replaying exploration
- Sharing failing states as bug reports
- CI reproducibility

## Best Practices

### 1. Extract Meaningful State

```python
# Good
state_from_context=["user_id", "order_id", "order_status"]

# Bad (too granular)
state_from_context=["user_id", "order_id", "order_status", "last_request_time"]
```

### 2. Use Context for IDs, Not State

```python
# Good: Store reference
context.set("order_id", resp.json()["id"])

# Bad: Store full state
context.set("order", resp.json())  # Gets stale
```

### 3. Check System State in Invariants

```python
# Good: Cross-verify
def check(world):
    return world.api.get("/count") == world.db.count_rows()

# Bad: Only check API
def check(world):
    return world.api.get("/count") > 0  # Could be wrong
```

### 4. Clean Up Transient State

```python
def teardown(api, context):
    # Remove test data
    user_id = context.get("user_id")
    if user_id:
        api.delete(f"/users/{user_id}")
```

## Next Steps

- [Checkpoints & Branching](branching.md) - Database rollback
- [Invariants Guide](../INVARIANTS_GUIDE.md) - Writing effective invariants
- [Adapters](../reference/adapters.md) - Database adapter reference
