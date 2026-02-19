# Testing Patterns

Common patterns for testing CRUD operations, auth flows, payment systems, and multi-tenant applications.

## Overview

This guide covers battle-tested patterns for testing different types of APIs with VenomQA.

## CRUD Testing

The most common pattern: testing Create, Read, Update, Delete operations.

### Basic CRUD

```python
from venomqa import Action, Agent, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["item_id"])

# Create
def create_item(api, context):
    resp = api.post("/items", json={"name": "test", "value": 100})
    context.set("item_id", resp.json()["id"])
    context.set("item_name", "test")
    return resp

# Read
def get_item(api, context):
    item_id = context.get("item_id")
    if not item_id:
        return None  # Skip: no item exists
    return api.get(f"/items/{item_id}")

# Update
def update_item(api, context):
    item_id = context.get("item_id")
    if not item_id:
        return None
    return api.patch(f"/items/{item_id}", json={"value": 200})

# Delete
def delete_item(api, context):
    item_id = context.get("item_id")
    if not item_id:
        return None
    resp = api.delete(f"/items/{item_id}")
    if resp.ok:
        context.delete("item_id")
    return resp

# List
def list_items(api, context):
    return api.get("/items")

actions = [
    Action(name="create_item", execute=create_item),
    Action(name="get_item", execute=get_item, preconditions=["create_item"]),
    Action(name="update_item", execute=update_item, preconditions=["create_item"]),
    Action(name="delete_item", execute=delete_item, preconditions=["create_item"]),
    Action(name="list_items", execute=list_items),
]

# Invariants
def item_consistency(world):
    """GET should return same data as created."""
    item_id = world.context.get("item_id")
    if not item_id:
        return True
    resp = world.api.get(f"/items/{item_id}")
    if not resp.ok:
        return True  # Item deleted, OK
    return resp.json()["name"] == world.context.get("item_name")

def no_500_errors(world):
    """No server errors allowed."""
    return world.context.get("last_status", 200) < 500

invariants = [
    Invariant("item_consistency", item_consistency, Severity.HIGH),
    Invariant("no_500_errors", no_500_errors, Severity.CRITICAL),
]

agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    max_steps=100,
)
result = agent.explore()
```

### CRUD with Pagination

```python
def list_items_paginated(api, context):
    page = context.get("page", 1)
    resp = api.get("/items", params={"page": page, "limit": 10})
    context.set("page", page + 1)
    return resp

def next_page(api, context):
    page = context.get("page", 1)
    return api.get("/items", params={"page": page, "limit": 10})
```

## Auth Flow Testing

### Login/Logout Pattern

```python
world = World(
    api=api,
    state_from_context=["user_id", "logged_in"],
)

def register(api, context):
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    resp = api.post("/auth/register", json={
        "email": email,
        "password": "password123",
    })
    if resp.ok:
        context.set("user_email", email)
    return resp

def login(api, context):
    email = context.get("user_email")
    if not email:
        return None
    resp = api.post("/auth/login", json={
        "email": email,
        "password": "password123",
    })
    if resp.ok:
        token = resp.json()["token"]
        context.set("auth_token", token)
        context.set("logged_in", True)
        api.set_header("Authorization", f"Bearer {token}")
    return resp

def logout(api, context):
    if not context.get("logged_in"):
        return None
    resp = api.post("/auth/logout")
    if resp.ok:
        context.delete("auth_token")
        context.set("logged_in", False)
        api.remove_header("Authorization")
    return resp

def get_profile(api, context):
    if not context.get("logged_in"):
        return None
    return api.get("/auth/profile")

def delete_account(api, context):
    if not context.get("logged_in"):
        return None
    resp = api.delete("/auth/account")
    if resp.ok:
        context.delete("user_email")
        context.delete("auth_token")
        context.set("logged_in", False)
    return resp

actions = [
    Action(name="register", execute=register),
    Action(name="login", execute=login, preconditions=["register"]),
    Action(name="logout", execute=logout, preconditions=["login"]),
    Action(name="get_profile", execute=get_profile, preconditions=["login"]),
    Action(name="delete_account", execute=delete_account, preconditions=["login"]),
]

# Invariant: can't access protected routes after logout
def auth_enforcement(world):
    if not world.context.get("logged_in"):
        return True  # Not logged in, nothing to check
    
    # Try accessing protected route
    resp = world.api.get("/auth/profile")
    if resp.status_code == 401:
        # Good: properly rejected
        return True
    return resp.ok  # Should succeed if logged in

invariants = [
    Invariant("auth_enforcement", auth_enforcement, Severity.CRITICAL),
]
```

### Token Refresh Pattern

```python
def refresh_token(api, context):
    token = context.get("auth_token")
    if not token:
        return None
    resp = api.post("/auth/refresh")
    if resp.ok:
        context.set("auth_token", resp.json()["token"])
    return resp

def use_expired_token(api, context):
    """Test that expired tokens are rejected."""
    old_token = context.get("auth_token")
    if not old_token:
        return None
    
    # Simulate expired token
    api.set_header("Authorization", "Bearer expired_token_xyz")
    resp = api.get("/auth/profile")
    api.set_header("Authorization", f"Bearer {old_token}")
    
    return resp

# Invariant: expired tokens should return 401
def expired_token_rejected(world):
    last_status = world.context.get("last_status", 200)
    if world.context.get("testing_expired"):
        return last_status == 401
    return True
```

## Payment Flow Testing

### Order → Payment → Refund

```python
world = World(
    api=api,
    state_from_context=["order_id", "payment_id", "order_status"],
)

# Order creation
def create_order(api, context):
    resp = api.post("/orders", json={
        "amount": 10000,  # $100.00 in cents
        "currency": "USD",
    })
    if resp.ok:
        context.set("order_id", resp.json()["id"])
        context.set("order_amount", 10000)
        context.set("order_status", "pending")
    return resp

# Payment
def pay_order(api, context):
    order_id = context.get("order_id")
    if not order_id or context.get("order_status") != "pending":
        return None
    
    resp = api.post(f"/orders/{order_id}/pay", json={
        "payment_method": "card",
        "card_token": "test_token",
    })
    if resp.ok:
        context.set("payment_id", resp.json()["payment_id"])
        context.set("order_status", "paid")
        context.set("amount_paid", resp.json().get("amount", 10000))
    return resp

# Refund
def refund_order(api, context):
    order_id = context.get("order_id")
    payment_id = context.get("payment_id")
    if not order_id or not payment_id:
        return None
    
    amount = context.get("refund_amount", 10000)
    resp = api.post(f"/orders/{order_id}/refund", json={
        "payment_id": payment_id,
        "amount": amount,
    })
    if resp.ok:
        refunded = context.get("total_refunded", 0) + amount
        context.set("total_refunded", refunded)
    return resp

# Partial refund
def partial_refund(api, context):
    context.set("refund_amount", 5000)  # $50.00
    return refund_order(api, context)

# Full refund
def full_refund(api, context):
    context.set("refund_amount", 10000)  # $100.00
    return refund_order(api, context)

# Cancel
def cancel_order(api, context):
    order_id = context.get("order_id")
    if not order_id:
        return None
    
    resp = api.post(f"/orders/{order_id}/cancel")
    if resp.ok:
        context.set("order_status", "canceled")
    return resp

actions = [
    Action(name="create_order", execute=create_order),
    Action(name="pay_order", execute=pay_order, preconditions=["create_order"]),
    Action(name="partial_refund", execute=partial_refund, preconditions=["pay_order"]),
    Action(name="full_refund", execute=full_refund, preconditions=["pay_order"]),
    Action(name="cancel_order", execute=cancel_order, preconditions=["create_order"]),
]

# Invariants
def no_over_refund(world):
    """Total refunded should not exceed order amount."""
    total_refunded = world.context.get("total_refunded", 0)
    order_amount = world.context.get("order_amount", 0)
    return total_refunded <= order_amount

def no_refund_unpaid(world):
    """Can't refund an unpaid order."""
    order_status = world.context.get("order_status")
    if order_status == "pending":
        last_status = world.context.get("last_status", 200)
        # Refund attempt should fail with 400 or 403
        return last_status >= 400
    return True

def cancel_prevents_refund(world):
    """Can't refund a canceled order."""
    order_status = world.context.get("order_status")
    if order_status == "canceled":
        last_status = world.context.get("last_status", 200)
        # Any refund attempt should fail
        if world.context.get("refund_attempted"):
            return last_status >= 400
    return True

invariants = [
    Invariant("no_over_refund", no_over_refund, Severity.CRITICAL),
    Invariant("no_refund_unpaid", no_refund_unpaid, Severity.HIGH),
    Invariant("cancel_prevents_refund", cancel_prevents_refund, Severity.HIGH),
]
```

## Multi-Tenant Testing

### Tenant Isolation

```python
world = World(
    api=api,
    state_from_context=["tenant_a_id", "tenant_b_id", "resource_id"],
)

# Setup tenants
def setup_tenant_a(api, context):
    resp = api.post("/tenants", json={"name": "Tenant A"})
    if resp.ok:
        context.set("tenant_a_id", resp.json()["id"])
        context.set("tenant_a_token", resp.json()["api_key"])
    return resp

def setup_tenant_b(api, context):
    resp = api.post("/tenants", json={"name": "Tenant B"})
    if resp.ok:
        context.set("tenant_b_id", resp.json()["id"])
        context.set("tenant_b_token", resp.json()["api_key"])
    return resp

def create_resource_as_a(api, context):
    token = context.get("tenant_a_token")
    if not token:
        return None
    
    resp = api.post(
        "/resources",
        json={"name": "A's resource"},
        headers={"X-API-Key": token},
    )
    if resp.ok:
        context.set("resource_id", resp.json()["id"])
        context.set("resource_owner", "A")
    return resp

def try_access_as_b(api, context):
    """Tenant B tries to access Tenant A's resource."""
    resource_id = context.get("resource_id")
    token_b = context.get("tenant_b_token")
    
    if not resource_id or not token_b:
        return None
    
    context.set("cross_tenant_attempt", True)
    resp = api.get(
        f"/resources/{resource_id}",
        headers={"X-API-Key": token_b},
    )
    context.set("cross_tenant_status", resp.status_code)
    return resp

actions = [
    Action(name="setup_tenant_a", execute=setup_tenant_a),
    Action(name="setup_tenant_b", execute=setup_tenant_b, preconditions=["setup_tenant_a"]),
    Action(name="create_resource_as_a", execute=create_resource_as_a, preconditions=["setup_tenant_a"]),
    Action(name="try_access_as_b", execute=try_access_as_b, preconditions=["create_resource_as_a", "setup_tenant_b"]),
]

# Invariant: tenants can't access each other's resources
def tenant_isolation(world):
    if world.context.get("cross_tenant_attempt"):
        status = world.context.get("cross_tenant_status", 200)
        # Should be 403 or 404
        return status in [403, 404]
    return True

invariants = [
    Invariant("tenant_isolation", tenant_isolation, Severity.CRITICAL),
]
```

## State Machine Testing

### Order State Machine

```
pending → paid → fulfilled
    ↓        ↓
canceled  refunded
```

```python
world = World(api=api, state_from_context=["order_id", "status"])

# Define valid transitions
VALID_TRANSITIONS = {
    None: ["create"],
    "pending": ["pay", "cancel"],
    "paid": ["fulfill", "refund"],
    "fulfilled": [],  # Terminal
    "canceled": [],   # Terminal
    "refunded": [],   # Terminal
}

def create_order(api, context):
    if context.get("order_id"):
        return None  # Already have an order
    resp = api.post("/orders", json={"amount": 100})
    if resp.ok:
        context.set("order_id", resp.json()["id"])
        context.set("status", "pending")
    return resp

def pay_order(api, context):
    if context.get("status") != "pending":
        return None
    resp = api.post(f"/orders/{context.get('order_id')}/pay")
    if resp.ok:
        context.set("status", "paid")
    return resp

def fulfill_order(api, context):
    if context.get("status") != "paid":
        return None
    resp = api.post(f"/orders/{context.get('order_id')}/fulfill")
    if resp.ok:
        context.set("status", "fulfilled")
    return resp

def refund_order(api, context):
    if context.get("status") != "paid":
        return None
    resp = api.post(f"/orders/{context.get('order_id')}/refund")
    if resp.ok:
        context.set("status", "refunded")
    return resp

def cancel_order(api, context):
    if context.get("status") != "pending":
        return None
    resp = api.post(f"/orders/{context.get('order_id')}/cancel")
    if resp.ok:
        context.set("status", "canceled")
    return resp

# Invariant: only valid transitions allowed
def state_transition_validity(world):
    """All transitions must follow the state machine."""
    last_status = world.context.get("last_status", 200)
    if last_status >= 400:
        # Request failed - acceptable if it was an invalid transition
        return True
    
    # If request succeeded, transition was valid
    return True

invariants = [
    Invariant("state_transition_validity", state_transition_validity, Severity.HIGH),
]
```

## Rate Limiting

```python
import time

class RateLimitedAction:
    """Action wrapper that respects rate limits."""
    
    def __init__(self, action, min_interval_ms: int = 100):
        self.action = action
        self.min_interval_ms = min_interval_ms
        self.last_call = 0
    
    def __call__(self, api, context):
        now = time.time() * 1000
        elapsed = now - self.last_call
        if elapsed < self.min_interval_ms:
            time.sleep((self.min_interval_ms - elapsed) / 1000)
        
        self.last_call = time.time() * 1000
        return self.action(api, context)

# Wrap actions
actions = [
    Action("create", RateLimitedAction(create_fn, min_interval_ms=200)),
    Action("update", RateLimitedAction(update_fn, min_interval_ms=200)),
]
```

## Best Practices Summary

| Pattern | Key Insight |
|---------|-------------|
| CRUD | Use preconditions for Read/Update/Delete |
| Auth | Track `logged_in` state in context |
| Payment | Track cumulative values (total_refunded) |
| Multi-tenant | Test cross-tenant access explicitly |
| State machine | Define valid transitions upfront |
| Rate limiting | Wrap actions or use sleep |

## Common Invariants

```python
# No server errors
Invariant("no_500s", lambda w: w.context.get("last_status", 200) < 500, Severity.CRITICAL)

# Idempotency
Invariant("create_idempotent", lambda w: count_items() <= expected, Severity.HIGH)

# Data consistency
Invariant("api_db_sync", lambda w: api_count() == db_count(), Severity.HIGH)

# Business rules
Invariant("positive_balance", lambda w: get_balance() >= 0, Severity.CRITICAL)

# Security
Invariant("no_unauthorized_access", lambda w: not (was_unauthorized and succeeded), Severity.CRITICAL)
```
