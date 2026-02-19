# The Theory

Why sequence testing catches bugs that traditional methods miss.

## The Problem with Unit Tests

Unit tests are **isolated by design**. Each test:

1. Sets up a fresh fixture
2. Makes one request
3. Asserts the response
4. Tears down

This is great for testing individual endpoints, but it misses how users actually use your API.

### A Real Bug That Unit Tests Missed

```python
# test_orders.py - All pass ✓

def test_create_order():
    resp = client.post("/orders", json={"amount": 100})
    assert resp.status_code == 201

def test_refund_order():
    order = create_order()  # Fresh fixture
    resp = client.post(f"/orders/{order.id}/refund")
    assert resp.status_code == 200
    assert resp.json()["refunded"] == 100

def test_refund_twice():
    order = create_order()  # Fresh fixture
    client.post(f"/orders/{order.id}/refund")
    resp = client.post(f"/orders/{order.id}/refund")
    # This test never gets written because:
    # - It seems redundant
    # - Developers assume "idempotency" without testing
```

All tests pass. But in production:

```
User: POST /orders         → {"id": "abc123", "amount": 100}
User: POST /orders/abc123/refund → {"refunded": 100}
User: POST /orders/abc123/refund → {"refunded": 200}  ← BUG
```

The API allows multiple refunds. Each individual call looks valid. The bug only appears in the **sequence**.

## The State Graph Model

Every stateful API defines an implicit state machine:

```
States:     What data exists right now
Actions:    What transitions are possible
Invariants: What must always be true
```

### Example: E-commerce Order

```
States:
  - [empty]      No order exists
  - [created]    Order exists, not paid
  - [paid]       Order paid, not shipped
  - [shipped]    Order shipped
  - [refunded]   Order refunded
  - [canceled]   Order canceled

Actions:
  - create_order   [empty] → [created]
  - pay_order      [created] → [paid]
  - ship_order     [paid] → [shipped]
  - refund_order   [paid] | [shipped] → [refunded]
  - cancel_order   [created] | [paid] → [canceled]

Invariants:
  - refunded_amount ≤ original_amount
  - cannot_refund_canceled
  - cannot_ship_unpaid
```

### Why This Is Hard to Test Manually

For this simple model, there are **20+ valid sequences**:

```
create → pay → ship → refund
create → pay → refund
create → pay → ship
create → cancel
create → pay → cancel
create → pay → ship → refund → refund (?)
...
```

Nobody writes 20 tests. They write 3-5 and call it done.

**VenomQA explores all 20 automatically.**

## The Combinatorial Explosion

As your API grows, the number of possible sequences explodes:

| Actions | Depth 3 | Depth 5 | Depth 10 |
|---------|---------|---------|----------|
| 3 | 27 | 243 | 59,049 |
| 5 | 125 | 3,125 | 9.7M |
| 10 | 1,000 | 100,000 | 10B |

VenomQA uses **intelligent pruning**:

1. **Precondition checks**: Skip actions that don't apply
2. **State deduplication**: Don't revisit identical states
3. **Invariant early-exit**: Stop exploring violating paths
4. **Budget limits**: Configurable max depth and steps

This brings exploration from "impossible" to "runs in CI."

## What Bugs Does This Catch?

### 1. Double Operations

```python
# create → delete → delete
# Bug: Second delete returns 200 instead of 404
```

### 2. Stale State

```python
# create → update → delete → get
# Bug: Get returns cached data instead of 404
```

### 3. Order-Dependent Failures

```python
# create_A → create_B → delete_A → get_B
# Bug: Deleting A corrupts B's state
```

### 4. Idempotency Violations

```python
# create → create (same idempotency key)
# Bug: Creates two orders instead of one
```

### 5. Missing Authorization Checks

```python
# create_as_user_A → delete_as_user_B
# Bug: User B can delete User A's resource
```

### 6. Race Conditions (with parallel actions)

```python
# create → [refund_1 || refund_2]
# Bug: Both refunds succeed simultaneously
```

## The Complement, Not Replacement

VenomQA doesn't replace your existing tests:

| Tool | Catches | Misses |
|------|---------|--------|
| **pytest** | Logic errors, edge cases | Sequences |
| **Schemathesis** | Schema violations, fuzzing | Sequences |
| **VenomQA** | Sequence bugs | Fuzzing |
| **Postman** | Manual verification | Automation |

**Best practice**: Run all three in CI.

```yaml
# .github/workflows/test.yml
jobs:
  unit-tests:
    run: pytest tests/

  schema-tests:
    run: schemathesis run schema.yaml

  sequence-tests:
    run: venomqa run qa/
```

## Key Insight

> **The bug isn't in any single endpoint. It's in the space between them.**

VenomQA explores that space systematically.

## Next Steps

- [Journeys](journeys.md) - How to define action chains
- [Checkpoints & Branching](branching.md) - Database rollback
- [Quickstart](../getting-started/quickstart.md) - Try it yourself
