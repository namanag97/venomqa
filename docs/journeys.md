# Writing Journeys

This guide covers how to write effective test journeys using VenomQA's Journey DSL.

## Table of Contents

- [What is a Journey?](#what-is-a-journey)
- [Basic Journey Structure](#basic-journey-structure)
- [Step Actions](#step-actions)
- [Context and State Sharing](#context-and-state-sharing)
- [Checkpoints and Rollback](#checkpoints-and-rollback)
- [Branching Paths](#branching-paths)
- [Expected Failures](#expected-failures)
- [Reusable Actions](#reusable-actions)
- [Best Practices](#best-practices)
- [Common Patterns](#common-patterns)

---

## What is a Journey?

A **journey** represents a complete user scenario from start to finish. Unlike traditional unit tests that test isolated functions, journeys test how your system behaves when users perform real-world workflows.

```
User Journey: Online Shopping
├── Login
├── Browse Products
├── Add to Cart
├── Checkout
│   ├── Credit Card Payment
│   ├── PayPal Payment
│   └── Gift Card Payment
└── Confirmation
```

---

## Basic Journey Structure

### Simple Linear Journey

The simplest journey is a linear sequence of steps:

```python
from venomqa import Journey, Step

def login(client, context):
    return client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret",
    })

def get_profile(client, context):
    return client.get("/api/users/me")

def update_profile(client, context):
    return client.patch("/api/users/me", json={
        "name": "Updated Name",
    })

journey = Journey(
    name="profile_update",
    description="Test profile update flow",
    steps=[
        Step(name="login", action=login),
        Step(name="get_profile", action=get_profile),
        Step(name="update_profile", action=update_profile),
    ],
)
```

### Journey with Metadata

Add tags and descriptions for organization:

```python
journey = Journey(
    name="checkout_flow",
    description="Complete checkout with payment processing",
    tags=["e-commerce", "critical", "payment"],
    timeout=120.0,  # 2 minute timeout
    steps=[...],
)
```

---

## Step Actions

### Action Function Signature

Every step action receives two parameters:

```python
def action(client: Client, context: ExecutionContext) -> Any:
    """
    Args:
        client: HTTP client configured with base URL and auth
        context: Shared state between steps
    
    Returns:
        Typically an httpx.Response object
    """
    pass
```

### Basic HTTP Operations

```python
# GET request
def list_users(client, context):
    return client.get("/api/users", params={"page": 1, "limit": 10})

# POST with JSON body
def create_user(client, context):
    return client.post("/api/users", json={
        "name": "John Doe",
        "email": "john@example.com",
    })

# PUT for full updates
def replace_user(client, context):
    user_id = context["user_id"]
    return client.put(f"/api/users/{user_id}", json={
        "name": "Jane Doe",
        "email": "jane@example.com",
    })

# PATCH for partial updates
def update_email(client, context):
    user_id = context["user_id"]
    return client.patch(f"/api/users/{user_id}", json={
        "email": "newemail@example.com",
    })

# DELETE
def delete_user(client, context):
    user_id = context["user_id"]
    return client.delete(f"/api/users/{user_id}")
```

### Step Options

```python
Step(
    name="create_order",
    action=create_order,
    description="Create a new order",     # Optional description
    timeout=10.0,                         # Override timeout
    retries=3,                            # Retry on failure
    expect_failure=False,                 # Expect this to fail
)
```

### Using Lambda Functions

For simple actions, use lambda functions:

```python
journey = Journey(
    name="quick_test",
    steps=[
        Step(
            name="health_check",
            action=lambda c, ctx: c.get("/health"),
        ),
        Step(
            name="create_item",
            action=lambda c, ctx: c.post("/items", json={"name": "test"}),
        ),
    ],
)
```

---

## Context and State Sharing

### Storing Values

Use the context to pass data between steps:

```python
def login(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret",
    })
    data = response.json()
    
    # Store values for later steps
    context["token"] = data["token"]
    context["user_id"] = data["user"]["id"]
    
    # Set auth token for subsequent requests
    client.set_auth_token(data["token"])
    
    return response

def get_orders(client, context):
    # Access stored values
    user_id = context["user_id"]
    return client.get(f"/api/users/{user_id}/orders")
```

### Context Methods

```python
# Store a value
context["key"] = value
context.set("key", value)

# Get a value (returns None if not found)
value = context.get("key")
value = context.get("key", default="fallback")

# Get required value (raises KeyError if missing)
value = context.get_required("key")

# Check if key exists
if "key" in context:
    # ...

# Store step result explicitly
context.store_step_result("login", response.json())

# Get previous step result
login_data = context.get_step_result("login")

# Create snapshot for restoration
snapshot = context.snapshot()
context.restore(snapshot)

# Export context
data = context.to_dict()
```

### Accessing Previous Responses

```python
def verify_order(client, context):
    # Access the response from the previous step
    order_id = context.get_step_result("create_order")["id"]
    return client.get(f"/api/orders/{order_id}")
```

---

## Checkpoints and Rollback

### Creating Checkpoints

Checkpoints save the database state for later rollback:

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path

journey = Journey(
    name="order_testing",
    steps=[
        Step(name="login", action=login),
        Step(name="create_order", action=create_order),
        Checkpoint(name="order_created"),  # Save state here
        # ... more steps
    ],
)
```

### When to Use Checkpoints

Use checkpoints before operations that modify state when you want to test multiple scenarios:

```python
journey = Journey(
    name="payment_flows",
    steps=[
        Step(name="login", action=login),
        Step(name="add_to_cart", action=add_to_cart),
        Checkpoint(name="cart_ready"),      # State: cart has items
        Step(name="checkout", action=checkout),
        Checkpoint(name="order_pending"),    # State: order created, awaiting payment
        Branch(
            checkpoint_name="order_pending",  # Rollback here before each path
            paths=[
                Path(name="card_payment", steps=[...]),
                Path(name="wallet_payment", steps=[...]),
                Path(name="payment_failure", steps=[...]),
            ],
        ),
    ],
)
```

### How Rollback Works

1. When a `Branch` is encountered, the runner saves the context snapshot
2. For each `Path` in the branch:
   - Context is restored to the snapshot
   - Database is rolled back to the checkpoint (if state manager is configured)
   - Path steps are executed
3. After all paths complete, execution continues

---

## Branching Paths

### Basic Branching

Test multiple scenarios from the same starting state:

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path

journey = Journey(
    name="checkout_flows",
    steps=[
        Step(name="login", action=login),
        Step(name="add_items", action=add_items),
        Checkpoint(name="items_added"),
        Branch(
            checkpoint_name="items_added",
            paths=[
                Path(name="standard_checkout", steps=[
                    Step(name="checkout_standard", action=checkout_standard),
                ]),
                Path(name="express_checkout", steps=[
                    Step(name="checkout_express", action=checkout_express),
                ]),
            ],
        ),
    ],
)
```

### Payment Method Testing

```python
def pay_with_card(client, context):
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "credit_card",
        "card_number": "4242424242424242",
    })

def pay_with_paypal(client, context):
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "paypal",
    })

def pay_with_wallet(client, context):
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "wallet",
    })

journey = Journey(
    name="payment_methods",
    steps=[
        Step(name="setup_order", action=setup_order),
        Checkpoint(name="order_ready"),
        Branch(
            checkpoint_name="order_ready",
            paths=[
                Path(name="credit_card", steps=[
                    Step(name="pay_card", action=pay_with_card),
                ]),
                Path(name="paypal", steps=[
                    Step(name="pay_paypal", action=pay_with_paypal),
                ]),
                Path(name="wallet", steps=[
                    Step(name="pay_wallet", action=pay_with_wallet),
                ]),
            ],
        ),
    ],
)
```

### Error Path Testing

```python
def pay_insufficient_funds(client, context):
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "credit_card",
        "card_number": "4000000000000002",  # Test card that declines
    })

def pay_expired_card(client, context):
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "credit_card",
        "card_number": "4000000000000069",  # Test card that's expired
    })

journey = Journey(
    name="payment_errors",
    steps=[
        Step(name="setup_order", action=setup_order),
        Checkpoint(name="order_ready"),
        Branch(
            checkpoint_name="order_ready",
            paths=[
                Path(name="insufficient_funds", steps=[
                    Step(
                        name="pay_insufficient",
                        action=pay_insufficient_funds,
                        expect_failure=True,  # We expect this to fail
                    ),
                ]),
                Path(name="expired_card", steps=[
                    Step(
                        name="pay_expired",
                        action=pay_expired_card,
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```

### Nested Checkpoints in Paths

```python
journey = Journey(
    name="complex_flows",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create_order", action=create_order),
        Checkpoint(name="order_created"),
        Branch(
            checkpoint_name="order_created",
            paths=[
                Path(name="full_payment", steps=[
                    Step(name="process_payment", action=process_payment),
                    Checkpoint(name="payment_done"),
                    Step(name="ship_order", action=ship_order),
                ]),
                Path(name="partial_payment", steps=[
                    Step(name="pay_deposit", action=pay_deposit),
                    Checkpoint(name="deposit_paid"),
                    Step(name="pay_remainder", action=pay_remainder),
                ]),
            ],
        ),
    ],
)
```

---

## Expected Failures

### Testing Error Responses

Use `expect_failure=True` when testing that your API correctly rejects invalid requests:

```python
# Test unauthorized access
Step(
    name="access_admin_without_auth",
    action=lambda c, ctx: c.get("/api/admin/users"),
    expect_failure=True,
)

# Test invalid input
Step(
    name="create_invalid_user",
    action=lambda c, ctx: c.post("/api/users", json={"email": "invalid"}),
    expect_failure=True,
)

# Test rate limiting
Step(
    name="exceed_rate_limit",
    action=spam_requests,
    expect_failure=True,
)
```

### Handling Expected Failures

When `expect_failure=True`:
- Step **passes** if the action fails (HTTP 4xx/5xx, exception)
- Step **fails** if the action succeeds

This ensures your error handling works correctly:

```python
def access_protected_resource(client, context):
    # Don't set auth token - should fail
    return client.get("/api/admin/settings")

journey = Journey(
    name="security_tests",
    steps=[
        Step(
            name="unauthorized_access",
            action=access_protected_resource,
            expect_failure=True,
        ),
    ],
)
```

---

## Reusable Actions

### Creating Action Modules

Organize actions in separate files for reuse:

```python
# actions/auth.py

def login(client, context, email="test@example.com", password="secret"):
    response = client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    if response.status_code == 200:
        context["token"] = response.json()["token"]
        client.set_auth_token(context["token"])
    return response

def logout(client, context):
    return client.post("/api/auth/logout")

def register(client, context, email=None, password=None, name=None):
    return client.post("/api/auth/register", json={
        "email": email or context.get("email", "test@example.com"),
        "password": password or context.get("password", "secret"),
        "name": name or context.get("name", "Test User"),
    })
```

```python
# actions/items.py

def create_item(client, context, name=None, price=None):
    response = client.post("/api/items", json={
        "name": name or context.get("item_name", "Default Item"),
        "price": price or context.get("item_price", 0.0),
    })
    if response.status_code in [200, 201]:
        context["item_id"] = response.json()["id"]
    return response

def get_item(client, context, item_id=None):
    item_id = item_id or context.get("item_id")
    return client.get(f"/api/items/{item_id}")

def delete_item(client, context, item_id=None):
    item_id = item_id or context.get("item_id")
    return client.delete(f"/api/items/{item_id}")
```

### Using Actions in Journeys

```python
# journeys/item_crud.py
from venomqa import Journey, Step, Checkpoint
from actions.auth import login
from actions.items import create_item, get_item, delete_item

journey = Journey(
    name="item_crud",
    steps=[
        Step(name="login", action=login),
        Step(name="create", action=create_item),
        Checkpoint(name="item_created"),
        Step(name="read", action=get_item),
        Step(name="delete", action=delete_item),
    ],
)
```

### Parameterized Actions

Create flexible actions that accept parameters:

```python
def search_items(client, context, query="", page=1, limit=10):
    return client.get("/api/items", params={
        "q": query,
        "page": page,
        "limit": limit,
    })

def create_item_with_params(client, context, **kwargs):
    defaults = {"name": "Item", "price": 0.0, "description": ""}
    data = {**defaults, **kwargs}
    return client.post("/api/items", json=data)
```

---

## Best Practices

### 1. Name Steps Clearly

```python
# Good
Step(name="create_order", action=create_order)
Step(name="process_payment", action=process_payment)
Step(name="send_confirmation_email", action=send_email)

# Bad
Step(name="step1", action=create_order)
Step(name="do_it", action=process_payment)
```

### 2. Use Descriptive Journey Names

```python
# Good
Journey(name="user_registration_email_verification")
Journey(name="checkout_with_credit_card")

# Bad
Journey(name="test1")
Journey(name="my_journey")
```

### 3. Add Tags for Organization

```python
Journey(
    name="payment_processing",
    tags=["critical", "payment", "integration"],
    steps=[...],
)
```

### 4. Use Meaningful Checkpoint Names

```python
# Good
Checkpoint(name="user_authenticated")
Checkpoint(name="order_created")
Checkpoint(name="payment_completed")

# Bad
Checkpoint(name="cp1")
Checkpoint(name="save_here")
```

### 5. Keep Actions Focused

```python
# Good - single responsibility
def create_order(client, context):
    return client.post("/api/orders", json={"item_id": context["item_id"]})

def add_shipping(client, context):
    return client.post(f"/api/orders/{context['order_id']}/shipping", json={...})

# Bad - doing too much
def create_order_with_shipping(client, context):
    order = client.post("/api/orders", json={...})
    shipping = client.post(f"/api/orders/{order.json()['id']}/shipping", json={...})
    return shipping
```

### 6. Handle Context Carefully

```python
def get_user_orders(client, context):
    # Use get() with default for optional values
    user_id = context.get("user_id")
    if not user_id:
        # Handle missing value gracefully
        return client.get("/api/orders")
    return client.get(f"/api/users/{user_id}/orders")
```

### 7. Set Timeouts Appropriately

```python
# Quick operations
Step(name="health_check", action=health_check, timeout=5.0)

# Normal operations
Step(name="create_order", action=create_order, timeout=30.0)

# Long-running operations
Step(name="generate_report", action=generate_report, timeout=120.0)
```

---

## Common Patterns

### CRUD Operations

```python
journey = Journey(
    name="user_crud",
    steps=[
        Step(name="login", action=login),
        Step(name="create_user", action=create_user),
        Checkpoint(name="user_created"),
        Step(name="read_user", action=read_user),
        Step(name="update_user", action=update_user),
        Step(name="delete_user", action=delete_user),
    ],
)
```

### Authentication Flow

```python
journey = Journey(
    name="auth_flow",
    steps=[
        Step(name="register", action=register),
        Step(name="login", action=login),
        Step(name="access_protected", action=access_protected),
        Step(name="refresh_token", action=refresh_token),
        Step(name="logout", action=logout),
    ],
)
```

### Multi-User Interaction

```python
def login_as_buyer(client, context):
    return login(client, context, email="buyer@example.com")

def login_as_seller(client, context):
    return login(client, context, email="seller@example.com")

journey = Journey(
    name="marketplace_transaction",
    steps=[
        Step(name="seller_lists_item", action=login_as_seller),
        Step(name="create_listing", action=create_listing),
        Checkpoint(name="item_listed"),
        Step(name="buyer_browses", action=login_as_buyer),
        Step(name="add_to_cart", action=add_to_cart),
        Step(name="checkout", action=checkout),
    ],
)
```

### Cleanup Pattern

Always clean up created resources:

```python
journey = Journey(
    name="with_cleanup",
    steps=[
        Step(name="login", action=login),
        Step(name="create_resource", action=create_resource),
        Checkpoint(name="resource_created"),
        # ... test operations ...
        Step(name="delete_resource", action=delete_resource),  # Always cleanup
    ],
)
```

### Conditional Logic

```python
def get_or_create_user(client, context):
    response = client.get(f"/api/users/{context['user_id']}")
    if response.status_code == 404:
        response = client.post("/api/users", json={"id": context["user_id"]})
    return response
```
