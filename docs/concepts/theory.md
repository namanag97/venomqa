# The Theory Behind VenomQA

Understanding *why* VenomQA works the way it does will help you get the most out of it.

## The Problem with Traditional API Testing

Traditional API testing treats each request in isolation:

```python
# Traditional approach
def test_create_item():
    response = client.post("/items", json={"name": "Widget"})
    assert response.status_code == 201

def test_list_items():
    response = client.get("/items")
    assert response.status_code == 200

def test_delete_item():
    # But wait... what item? The one from test_create_item?
    # Maybe. Depends on test execution order.
    response = client.delete("/items/1")
    assert response.status_code == 204
```

**Problems:**

1. **Test isolation paradox**: Tests should be independent, but real user flows are dependent
2. **State uncertainty**: Each test doesn't know what state the system is in
3. **Order dependence**: Tests often secretly depend on each other's side effects
4. **Incomplete coverage**: You test happy paths but miss complex state combinations

## Real Users Don't Work That Way

Real users follow **journeys** through your application:

```
Login → Browse → Add to Cart → Checkout → Pay → Verify Order
```

Each step depends on the previous one. The "Pay" step doesn't make sense without "Add to Cart" first.

And here's the key insight: **bugs often emerge from specific state combinations**.

- The checkout works fine with 1 item, but breaks with 100 items
- Payment works with a new user, but fails for users with expired cards
- The cart works, but only if you haven't applied a discount code first

## VenomQA's Approach: State-Based Testing

VenomQA models your application as a **state machine**:

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
                    ▼                                         │
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  Empty   │──▶│ Has Cart │──▶│ Checkout │──▶│   Paid   │────┘
│  (start) │   │          │   │          │   │          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
                    │              │
                    │              │
                    ▼              ▼
               ┌──────────┐   ┌──────────┐
               │  Empty   │   │  Failed  │
               │ (cleared)│   │ Payment  │
               └──────────┘   └──────────┘
```

### Two Testing Paradigms

**1. Journey Testing** - For user flows

You define the exact path a user takes. VenomQA executes it step by step, passing context between steps.

```python
journey = Journey(
    name="checkout",
    steps=[
        Step("login", login),
        Step("add_item", add_to_cart),
        Step("checkout", start_checkout),
        Step("pay", pay_with_card),
    ]
)
```

**2. State Graph Testing** - For exhaustive exploration

You define the possible states and transitions. VenomQA automatically explores ALL reachable paths.

```python
graph = StateGraph("cart_app")
graph.add_node("empty", initial=True)
graph.add_node("has_items")
graph.add_node("checked_out")

graph.add_edge("empty", "has_items", action=add_item)
graph.add_edge("has_items", "empty", action=clear_cart)
graph.add_edge("has_items", "has_items", action=add_item)  # Can add more
graph.add_edge("has_items", "checked_out", action=checkout)

# VenomQA explores: empty→has_items→checkout, empty→has_items→has_items→checkout, etc.
result = graph.explore(client, max_depth=5)
```

## Checkpoints: Git for Your Database

The key insight that makes this work is **checkpoints**.

```python
Checkpoint(name="cart_ready")
```

When VenomQA hits a checkpoint:

1. It saves the entire database state (like a Git commit)
2. When you branch, it can restore to that exact state
3. Each branch starts from the same known state

This solves the "test isolation paradox":

- Your tests can be truly independent (each branch starts fresh)
- Your tests can still test complex flows (the setup is shared)

```
     login
       │
       ▼
   add_to_cart
       │
       ▼
  ┌────────────────┐
  │  CHECKPOINT    │   ← Database state saved here
  │  "cart_ready"  │
  └────────────────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
pay_visa  pay_wallet   ← Each branch starts from identical state
   │       │
   ▼       ▼
verify   verify
```

## Invariants: Catching Hidden Bugs

An **invariant** is a rule that must ALWAYS be true, no matter what actions were taken.

```python
graph.add_invariant(
    name="cart_total_matches_items",
    check=lambda client, db, ctx: (
        client.get("/cart/total").json()["total"] ==
        sum(item["price"] for item in db.query("SELECT price FROM cart_items"))
    ),
    description="Cart total must equal sum of item prices"
)
```

VenomQA checks invariants after EVERY action. This catches bugs that only appear in specific state combinations:

```
empty → add_item($10) → add_item($20) → apply_discount(50%) → remove_item($10)

Expected: total = $10 (one $20 item with 50% discount)
Bug:      total = $5 (discount was applied to removed item too)
```

Traditional tests might miss this because they don't test that specific sequence of actions.

## Why "Venom"?

Like venom spreading through a system, VenomQA **penetrates every corner** of your application. It doesn't just test the happy path - it explores the edges, the combinations, the states that only emerge after specific sequences of actions.

## Key Principles

### 1. Context Passing

Every step receives a `context` dict that persists across the journey:

```python
def login(client, context):
    response = client.post("/auth/login", json={...})
    context["token"] = response.json()["token"]  # Set it here
    return response

def get_orders(client, context):
    # Use it in any later step
    return client.get("/orders", headers={"Authorization": f"Bearer {context['token']}"})
```

### 2. Explicit Dependencies

Steps can declare what context keys they need:

```python
Step(name="get_orders", action=get_orders, requires=["token"])
```

### 3. Failure Expectations

Some steps are *supposed* to fail:

```python
Step(
    name="pay_declined",
    action=pay_with_bad_card,
    expect_failure=True,  # 4xx response is success for this step
)
```

### 4. Clean Architecture

VenomQA uses ports and adapters so you can swap implementations:

```python
# In tests: use PostgreSQL
client = Client(base_url="http://localhost:8000")
db = PostgresAdapter(connection_string="...")

# In CI: use SQLite
db = SQLiteAdapter(path=":memory:")

# Same tests, different backends
```

## When to Use What

| Scenario | Approach |
|----------|----------|
| Testing a specific user flow | Journey |
| Finding edge cases in state transitions | State Graph |
| Ensuring data consistency | Invariants |
| Testing multiple variations of a flow | Branches |
| Testing error handling | `expect_failure=True` |

## Summary

VenomQA shifts API testing from "test endpoints in isolation" to "test the system as users actually use it":

1. **Journeys** model real user flows
2. **Checkpoints** enable branching without test interdependence
3. **State Graphs** explore all possible paths
4. **Invariants** catch consistency bugs
5. **Context** flows between steps naturally

The result: tests that catch bugs traditional testing misses, because they test the *combinations* of states that real users encounter.
