# Testing Payment Flows

Test complex e-commerce state machines with database rollback.

## What You'll Build

A test suite for a payment API with:

- Order creation and state transitions
- Payment processing
- Refund handling
- Partial refunds
- Idempotency checks

## The State Machine

Payment flows are classic state machines:

```
                    ┌─────────────┐
                    │   [empty]   │
                    └──────┬──────┘
                           │ create
                           ▼
                    ┌─────────────┐
          ┌─────────│   [pending] │─────────┐
          │         └──────┬──────┘         │
          │ cancel        │ pay             │ timeout
          ▼               ▼                 ▼
   ┌─────────────┐ ┌─────────────┐  ┌─────────────┐
   │ [canceled]  │ │  [paid]     │  │ [expired]   │
   └─────────────┘ └──────┬──────┘  └─────────────┘
                   ┌──────┴──────┐
                   │ refund      │ capture
                   ▼             ▼
            ┌─────────────┐ ┌─────────────┐
            │ [refunded]  │ │ [captured]  │
            └─────────────┘ └──────┬──────┘
                                   │ refund
                                   ▼
                            ┌─────────────┐
                            │ [refunded]  │
                            └─────────────┘
```

## Setup

```bash
pip install venomqa
pip install psycopg[binary]  # For PostgreSQL rollback
```

## Step 1: Define Actions

Create `qa/actions/payments.py`:

```python
"""Payment API actions."""

from typing import Optional
from decimal import Decimal

def create_order(api, context) -> Optional[dict]:
    """Create a new order."""
    resp = api.post("/orders", json={
        "amount": "100.00",
        "currency": "USD",
        "customer_id": "cust_123",
    })
    
    if resp.status_code == 201:
        data = resp.json()
        context.set("order_id", data["id"])
        context.set("order_amount", Decimal(data["amount"]))
        context.set("order_status", data["status"])
        context.set("total_refunded", Decimal("0"))
        return data
    return None

def pay_order(api, context) -> Optional[dict]:
    """Pay for a pending order."""
    order_id = context.get("order_id")
    if not order_id:
        return None
    
    status = context.get("order_status")
    if status != "pending":
        return None  # Can only pay pending orders
    
    resp = api.post(f"/orders/{order_id}/pay", json={
        "payment_method": "card",
        "card_token": "tok_test",
    })
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("order_status", data["status"])
        context.set("payment_id", data.get("payment_id"))
        return data
    return None

def refund_order(api, context) -> Optional[dict]:
    """Refund a paid order (full refund)."""
    order_id = context.get("order_id")
    if not order_id:
        return None
    
    status = context.get("order_status")
    if status not in ("paid", "captured"):
        return None  # Can only refund paid/captured orders
    
    resp = api.post(f"/orders/{order_id}/refund")
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("order_status", data["status"])
        current = context.get("total_refunded", Decimal("0"))
        context.set("total_refunded", current + Decimal(str(data.get("refunded_amount", 0))))
        return data
    return None

def partial_refund(api, context) -> Optional[dict]:
    """Refund part of an order."""
    order_id = context.get("order_id")
    if not order_id:
        return None
    
    status = context.get("order_status")
    if status not in ("paid", "captured"):
        return None
    
    # Refund $25
    resp = api.post(f"/orders/{order_id}/refund", json={
        "amount": "25.00",
    })
    
    if resp.status_code == 200:
        data = resp.json()
        current = context.get("total_refunded", Decimal("0"))
        context.set("total_refunded", current + Decimal("25.00"))
        return data
    return None

def cancel_order(api, context) -> Optional[dict]:
    """Cancel a pending order."""
    order_id = context.get("order_id")
    if not order_id:
        return None
    
    status = context.get("order_status")
    if status != "pending":
        return None  # Can only cancel pending orders
    
    resp = api.post(f"/orders/{order_id}/cancel")
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("order_status", data["status"])
        return data
    return None

def capture_order(api, context) -> Optional[dict]:
    """Capture an authorized payment."""
    order_id = context.get("order_id")
    if not order_id:
        return None
    
    status = context.get("order_status")
    if status != "paid":
        return None  # Can only capture paid (authorized) orders
    
    resp = api.post(f"/orders/{order_id}/capture")
    
    if resp.status_code == 200:
        data = resp.json()
        context.set("order_status", data["status"])
        return data
    return None
```

## Step 2: Define Invariants

Create `qa/invariants_payments.py`:

```python
"""Payment invariants."""

from decimal import Decimal
from venomqa import Invariant, Severity

def no_over_refund(world) -> bool:
    """Total refunds cannot exceed order amount."""
    total_refunded = world.context.get("total_refunded", Decimal("0"))
    order_amount = world.context.get("order_amount", Decimal("0"))
    return total_refunded <= order_amount

def no_refund_after_cancel(world) -> bool:
    """Cannot refund a canceled order."""
    status = world.context.get("order_status")
    if status == "canceled":
        total_refunded = world.context.get("total_refunded", Decimal("0"))
        return total_refunded == Decimal("0")
    return True

def status_consistency(world) -> bool:
    """Order status must match API state."""
    order_id = world.context.get("order_id")
    if not order_id:
        return True
    
    resp = world.api.get(f"/orders/{order_id}")
    if resp.status_code != 200:
        return True
    
    api_status = resp.json()["status"]
    context_status = world.context.get("order_status")
    return api_status == context_status

# Create invariant objects
invariants = [
    Invariant(
        name="no_over_refund",
        check=no_over_refund,
        severity=Severity.CRITICAL,
        description="Refunds cannot exceed order total",
    ),
    Invariant(
        name="no_refund_after_cancel",
        check=no_refund_after_cancel,
        severity=Severity.CRITICAL,
        description="Cannot refund a canceled order",
    ),
    Invariant(
        name="status_consistency",
        check=status_consistency,
        severity=Severity.HIGH,
        description="API status must match context",
    ),
    Invariant(
        name="no_500_errors",
        check=lambda w: w.context.get("last_status", 200) < 500,
        severity=Severity.CRITICAL,
    ),
]
```

## Step 3: Add Database Rollback

Create `qa/conftest.py`:

```python
"""Configuration and fixtures."""

import os
from venomqa import World
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter

def get_world():
    """Create a world with PostgreSQL rollback."""
    api = HttpClient(
        base_url=os.getenv("API_URL", "http://localhost:8000"),
        timeout=30.0,
    )
    
    # PostgreSQL adapter for rollback
    db = PostgresAdapter(
        os.getenv("DATABASE_URL", "postgresql://localhost/payments_test")
    )
    
    return World(
        api=api,
        systems={"db": db},
        state_from_context=["order_id", "order_status"],
    )
```

## Step 4: Run the Test

Create `qa/test_payments.py`:

```python
"""Payment flow tests."""

from venomqa import Action, Agent, BFS
from conftest import get_world
from actions.payments import (
    create_order, pay_order, refund_order, 
    partial_refund, cancel_order, capture_order
)
from invariants_payments import invariants

world = get_world()

actions = [
    Action("create_order", create_order),
    Action("pay_order", pay_order),
    Action("refund_order", refund_order),
    Action("partial_refund", partial_refund),
    Action("cancel_order", cancel_order),
    Action("capture_order", capture_order),
]

agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    strategy=BFS(),
    max_steps=200,
    max_depth=15,
)

if __name__ == "__main__":
    result = agent.explore()
    
    print(f"\n{'='*60}")
    print(f"PAYMENT FLOW EXPLORATION RESULTS")
    print(f"{'='*60}")
    print(f"States visited:     {result.states_visited}")
    print(f"Transitions:        {result.transitions}")
    print(f"Invariants checked: {result.invariants_checked}")
    print(f"Violations:         {result.violations}")
    
    if result.violations:
        print(f"\n{'─'*60}")
        print("VIOLATIONS FOUND:")
        for v in result.violations:
            print(f"\n  [{v.severity}] {v.invariant_name}")
            print(f"    Path: {' → '.join(v.path)}")
            print(f"    {v.message}")
    else:
        print(f"\n{'─'*60}")
        print("✓ All invariants passed!")
```

Run:

```bash
python qa/test_payments.py
```

## Common Bugs This Catches

### 1. Double Refund

```python
# Bug: API allows refunding more than order total
create → pay → refund → refund → refund
# Expected: Second+ refund fails
# Bug: All refunds succeed, total > order amount
```

### 2. Refund After Cancel

```python
# Bug: Can refund a canceled order
create → cancel → refund
# Expected: Refund fails (order canceled)
# Bug: Refund succeeds
```

### 3. State Transitions

```python
# Bug: Can capture a refunded order
create → pay → refund → capture
# Expected: Capture fails (already refunded)
# Bug: Capture succeeds, corrupts state
```

### 4. Partial Refund Overflow

```python
# Bug: Can partially refund more than total
create → pay → partial_refund → partial_refund → partial_refund → partial_refund → partial_refund
# Expected: Total capped at order amount
# Bug: No limit on partial refunds
```

## Best Practices

### 1. Track State in Context

```python
# Always update context when state changes
context.set("order_status", data["status"])
context.set("total_refunded", current + amount)
```

### 2. Check Preconditions

```python
# Skip actions that don't apply
if context.get("order_status") != "pending":
    return None  # Skip
```

### 3. Use Decimal for Money

```python
# Never use float for money
amount = Decimal("100.00")  # Correct
amount = 100.00             # Wrong - floating point errors
```

### 4. Verify Database State

```python
def db_api_consistency(world):
    api_amount = world.api.get("/orders/123").json()["refunded"]
    db_amount = world.systems["db"].query("SELECT refunded FROM orders WHERE id = 123")
    return api_amount == db_amount
```

## Next Steps

- [CI/CD Integration](ci-cd.md) - Automate these tests
- [Invariants Guide](../INVARIANTS_GUIDE.md) - Write better invariants
- [Examples](../examples/index.md) - More patterns
