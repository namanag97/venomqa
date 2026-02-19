# Concepts

Understand the mental model behind VenomQA.

## The Core Insight

Traditional API testing is **stateless**. Each test runs in isolation with a fresh fixture and a predetermined assertion. But real applications are **stateful** — what happened before affects what happens next.

```
Traditional Testing:
  Test 1: POST /orders  → 201 ✓
  Test 2: POST /refund  → 200 ✓
  (Each test runs independently)

Real Usage:
  User: POST /orders  → 201 ✓
  User: POST /refund  → 200 ✓
  User: POST /refund  → 200 ✓  ← Bug: double refund!
```

VenomQA models your API as a **state graph** and explores every path through it.

## The Three Primitives

Everything in VenomQA is built from three concepts:

| Primitive | Purpose | Analogy |
|-----------|---------|---------|
| **Action** | One thing your API can do | A button the user clicks |
| **Invariant** | A rule that must always hold | A business constraint |
| **World** | The sandbox with rollback | The test environment |

### Actions

An action is a Python function that makes one API call:

```python
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])  # Store for later
    return resp
```

Actions can:

- Make HTTP requests
- Read/write to the context
- Return `None` to skip (precondition not met)

### Invariants

An invariant is a rule checked after **every** action:

```python
no_over_refund = Invariant(
    "no_over_refund",
    lambda world: get_total_refunded() <= get_order_total(),
    Severity.CRITICAL,
)
```

Invariants catch bugs that only appear in specific sequences.

### World

The world holds the API client, database connections, and context:

```python
world = World(
    api=HttpClient("http://localhost:8000"),
    state_from_context=["order_id"],
)
```

Worlds support checkpoint/rollback for branching exploration.

## The Exploration Model

VenomQA treats your API as a state machine:

```
         ┌──────────────┐
         │   [empty]    │
         └──────┬───────┘
                │ create_order
                ▼
         ┌──────────────┐
         │ [has_order]  │◄──────┐
         └──────┬───────┘       │
        ┌───────┴───────┐       │
        │               │       │
   refund          cancel       │
        ▼               ▼       │
  ┌──────────┐  ┌────────────┐  │
  │[refunded]│  │ [canceled] │──┘
  └──────────┘  └────────────┘
```

The agent explores this graph using BFS, DFS, or coverage-guided strategies. At each node, it:

1. Saves the world state (checkpoint)
2. Tries each applicable action
3. Checks all invariants
4. Rolls back and tries the next branch

## Why This Finds Bugs Others Miss

| Bug Type | pytest | Schemathesis | VenomQA |
|----------|--------|--------------|---------|
| Double refund | ✗ | ✗ | ✓ |
| Stale cache after delete | ✗ | ✗ | ✓ |
| Idempotency violation | ✗ | ✗ | ✓ |
| Race condition in sequence | ✗ | ✗ | ✓ |
| Schema validation | ✓ | ✓ | ✓ |
| Fuzzing edge cases | ✗ | ✓ | ✗ |

**VenomQA complements, not replaces, your existing tests.** Use Schemathesis for schema fuzzing, pytest for unit tests, and VenomQA for sequence bugs.

## Topics

<div class="grid cards" markdown>

-   :material-lightbulb:{ .lg .middle } __The Theory__

    ---

    Why sequence testing matters and what bugs it catches.

    [:octicons-arrow-right-24: Read more](theory.md)

-   :material-map-marker-path:{ .lg .middle } __Journeys__

    ---

    How actions chain together with automatic context flow.

    [:octicons-arrow-right-24: Read more](journeys.md)

-   :material-source-branch:{ .lg .middle } __Checkpoints & Branching__

    ---

    Database rollback for true parallel exploration.

    [:octicons-arrow-right-24: Read more](branching.md)

-   :material-database:{ .lg .middle } __State Management__

    ---

    Context, checkpoints, and state extraction.

    [:octicons-arrow-right-24: Read more](state.md)

-   :material-pipe:{ .lg .middle } __Ports & Adapters__

    ---

    Clean architecture for testable code.

    [:octicons-arrow-right-24: Read more](ports-adapters.md)

</div>
