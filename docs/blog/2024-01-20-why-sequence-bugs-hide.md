---
date: 2024-01-20
authors:
  - venomqa-team
categories:
  - API Testing
  - Software Quality
tags:
  - API testing
  - sequence bugs
  - stateful testing
  - integration testing
  - automated testing
title: "Why Your Tests Pass But Your API Still Breaks: The Hidden World of Sequence Bugs"
description: "Discover why traditional testing misses the most dangerous bugs—the ones that only appear in specific action sequences. Learn how stateful testing catches what unit tests can't."
---

# Why Your Tests Pass But Your API Still Breaks: The Hidden World of Sequence Bugs

It was 3 AM when the PagerDuty alert woke Sarah. The payment service was returning 500 errors. Again.

She pulled up the logs and stared at the stack trace. A customer had been **refunded twice** for the same order. The first refund worked fine. The second one—the one that happened 47 seconds later—crashed the entire service.

Sarah did what any engineer would do. She ran the test suite.

```
450 tests passed ✓
0 failures ✗
Coverage: 94%
```

Every single test passed. The `refund_order` endpoint had 12 dedicated test cases. All green. So how did this bug make it to production?

Here's the uncomfortable truth: **the bug only appeared when you refunded an already-refunded order.**

Not when you refund once. Not when you refund an invalid order. Only in that *specific sequence*.

This is a **sequence bug**. And traditional testing is blind to them.

---

## The Illusion of Passing Tests

Let's look at what Sarah's test suite actually tested:

```python
def test_refund_order_success():
    order = create_order(amount=100)
    response = api.post(f"/orders/{order.id}/refund")
    assert response.status_code == 200
    assert response.json()["status"] == "refunded"

def test_refund_nonexistent_order():
    response = api.post("/orders/99999/refund")
    assert response.status_code == 404

def test_refund_already_refunded():
    order = create_order(amount=100)
    api.post(f"/orders/{order.id}/refund")  # First refund
    response = api.post(f"/orders/{order.id}/refund")  # Second refund
    assert response.status_code == 400  # Expected: bad request
```

Wait—there's even a test for double refunds! So what happened?

The test passed because it was testing with a **fresh database**. After the first test ran, the database was wiped clean. The order was created *fresh* for each test.

But in production? Orders sit in the database for weeks. Customers click refund buttons multiple times (accidentally or not). Background jobs retry failed requests.

The test didn't fail because **the test and production had different state**.

---

## Why Unit Tests Miss These Bugs

Unit tests are designed for **isolation**. This is their strength and their blindness.

### 1. Fresh Fixtures, Fresh Problems

Every test gets a pristine world:

```python
@pytest.fixture
def clean_db():
    db.begin_transaction()
    yield db
    db.rollback()  # Everything goes away
```

This means no state carries over between tests. Which is great for repeatability—but terrible for catching bugs that only emerge from accumulated state.

### 2. Linear Thinking, Non-Linear Bugs

Unit tests are written linearly:

```python
def test_checkout():
    cart = add_to_cart(item_id=123)  # Step 1
    checkout = process_payment(cart)  # Step 2
    assert checkout.status == "success"  # Verify
```

But users don't behave linearly. They:

- Add items, remove them, add them again
- Start checkout, cancel, start again
- Click buttons multiple times "just to be sure"
- Open multiple tabs with the same session

### 3. The Combinatorial Explosion

If your API has just 5 actions (create, read, update, delete, refund), how many sequences should you test?

- Sequences of length 2: 25 combinations
- Sequences of length 3: 125 combinations
- Sequences of length 5: **3,125 combinations**
- Sequences of length 10: **9,765,625 combinations**

Nobody writes 10 million test cases. So we test the happy path, a few edge cases, and hope.

---

## Real-World Sequence Bugs (That Made It to Production)

### The Double Refund (Stripe-style)

```python
# Bug: Race condition in refund processing
def process_refund(order_id):
    order = db.get_order(order_id)
    if order.status == "refunded":
        raise AlreadyRefundedError()
    
    # ⚠️ Time gap here — another request can slip in
    
    payment_gateway.refund(order.payment_id)
    order.status = "refunded"
    db.save(order)
```

Two requests arrive simultaneously. Both pass the `if order.status == "refunded"` check. Both issue refunds. **Customer gets double their money back.**

### The Stale Cache After Delete

```python
# Bug: Cache not invalidated after delete
def delete_user(user_id):
    db.delete_user(user_id)
    # Forgot: cache.delete(f"user:{user_id}")
    
def get_user(user_id):
    cached = cache.get(f"user:{user_id}")
    if cached:
        return cached  # Returns deleted user!
    return db.get_user(user_id)
```

Unit tests pass because they don't test the sequence `delete → get`. They test delete. They test get. But not together.

### The Idempotency Violation

```python
# Bug: Idempotency key not checked atomically
def charge_customer(amount, idempotency_key):
    if cache.exists(idempotency_key):
        return cache.get(idempotency_key)
    
    # ⚠️ Gap between check and charge
    
    result = stripe.charge(amount)
    cache.set(idempotency_key, result)
    return result
```

Customer's payment times out, they retry, and get charged twice.

### The Zombie Subscription

```python
# Bug: Cancel doesn't stop renewal job
def cancel_subscription(sub_id):
    sub = db.get_subscription(sub_id)
    sub.status = "cancelled"
    db.save(sub)
    # Forgot: scheduler.cancel(sub.renewal_job_id)

# Two months later...
@renewal_job
def renew_subscription(sub_id):
    sub = db.get_subscription(sub_id)
    charge_customer(sub.amount)  # Charges cancelled subscription!
```

---

## The Testing Gap

Here's what popular testing tools actually check:

| Tool | Tests | Misses |
|------|-------|--------|
| **pytest** | Individual functions | Sequences of operations |
| **Schemathesis** | Schema compliance, types | Business logic violations |
| **Postman** | Manual sequences you write | Sequences you didn't think of |
| **k6/Locust** | Performance under load | Correctness of behavior |
| **Chaos Engineering** | System resilience | Logic bugs in happy paths |

They're all valuable. But none of them systematically explore **what happens when you combine actions in unexpected orders**.

---

## The Human Factor

Even if tools supported sequence testing, there's a more fundamental problem: **humans are bad at imagining all the sequences.**

### Cognitive Biases

1. **Happy Path Bias**: We test what should work, not what could go wrong
2. **Linear Thinking**: We imagine users following the "normal" flow
3. **Confirmation Bias**: Once we find a bug, we stop looking for others
4. **Anchoring**: We copy test patterns from existing tests

### The Math of Edge Cases

For 3 actions, there are 27 possible sequences of length 3. But most engineers write:

```python
def test_action_a(): ...
def test_action_b(): ...
def test_action_c(): ...
```

That's 3 tests. Not 27. We're testing **11% of the state space**.

Add just 2 more actions? Now there are 3,125 sequences of length 5. Nobody writes 3,125 tests.

---

## How to Fix It: Stateful API Testing

The solution isn't more unit tests. The solution is **exploration**, not enumeration.

### Model-Based Testing

Instead of writing individual test cases, you define:

1. **Actions**: What can users do?
2. **Invariants**: What must always be true?

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

# Define what users CAN do
actions = [
    Action(name="create_order", execute=lambda api, ctx: 
        api.post("/orders", json={"amount": 100})),
    Action(name="refund_order", execute=lambda api, ctx:
        api.post(f"/orders/{ctx.get('order_id')}/refund") 
        if ctx.get('order_id') else None),
    Action(name="delete_order", execute=lambda api, ctx:
        api.delete(f"/orders/{ctx.get('order_id')}") 
        if ctx.get('order_id') else None),
]

# Define what MUST be true
invariants = [
    Invariant(
        name="no_500_errors",
        check=lambda world: world.context.get("last_status", 200) < 500,
        severity=Severity.CRITICAL,
    ),
    Invariant(
        name="refunded_orders_cant_be_deleted",
        check=lambda world: not (
            world.context.get("order_refunded") and 
            world.context.get("last_action") == "delete_order" and
            world.context.get("last_status") == 200
        ),
        severity=Severity.HIGH,
    ),
]

# Let the agent explore EVERY sequence
api = HttpClient(base_url="http://localhost:8000")
world = World(api=api, state_from_context=["order_id", "order_refunded"])

agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    strategy=BFS(),
    max_steps=100,
)

result = agent.explore()
print(f"Explored {result.states_visited} states")
print(f"Found {len(result.violations)} violations")
```

The agent explores **systematically**: `create → refund → refund`, `create → delete → refund`, `create → refund → delete`, and so on.

When it finds a violation, it reports the **exact sequence** that caused it:

```
INVARIANT VIOLATION: no_500_errors
  Sequence: create_order → refund_order → refund_order
  State transition:
    - Order #1234 created
    - Order #1234 refunded (status=200)
    - Order #1234 refunded (status=500) ← BUG!
```

### State Exploration with Rollback

The key innovation is **database rollback** between sequences:

```python
# Test sequence 1: create → refund → refund
checkpoint()  # Save state
create_order()
refund_order()
refund_order()  # ← This might crash!
rollback()  # Restore state

# Test sequence 2: create → delete → refund
checkpoint()  # Fresh start
create_order()
delete_order()
refund_order()  # ← Different bug might appear!
rollback()
```

This lets you test **thousands of sequences** against the same database, without contaminating state between tests.

### Invariant Checking

Instead of asserting specific outcomes, you define **global properties**:

```python
# "Total money in = total money out" (conservation)
def money_conserved(world):
    created = sum(o.amount for o in world.created_orders)
    refunded = sum(o.amount for o in world.refunded_orders)
    return refunded <= created  # Can't refund more than created

# "No operation takes > 5 seconds" (performance)
def response_time_ok(world):
    return world.context.get("last_response_time", 0) < 5.0

# "No sensitive data in responses" (security)
def no_pii_leak(world):
    response = world.context.get("last_response", "")
    return not any(pii in response for pii in ["ssn", "credit_card"])
```

These invariants are checked **after every action** in every sequence.

---

## The Takeaway

Traditional testing catches bugs in *components*. Sequence bugs hide in the *interactions* between components.

- **Unit tests**: "Does `refund()` work?"
- **Integration tests**: "Do `refund()` and `stripe_charge()` work together?"
- **Stateful testing**: "What happens when `create → refund → refund → delete → create`?"

You need all three.

The good news? You don't have to write a million test cases. You define the rules, and let the computer explore the combinations.

Because the bug that crashed your production at 3 AM? It's already there, hiding in a sequence you haven't tested yet.

---

## Start Finding Sequence Bugs Today

VenomQA is an open-source tool that explores your API's state graph automatically. Define actions, define invariants, and let it find the bugs your tests missed.

```bash
pip install venomqa
venomqa demo  # See it find a sequence bug in 30 seconds
```

Or check out the [examples](https://github.com/anomalyco/venomqa/tree/main/examples) to see it find real bugs in a payment system.

---

*Found this helpful? Star us on [GitHub](https://github.com/anomalyco/venomqa) and follow for more on API testing, stateful testing, and automated QA.*
