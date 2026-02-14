# Journeys

A **Journey** is the fundamental unit of testing in VenomQA. It represents a complete user scenario from start to finish.

## What is a Journey?

Unlike traditional unit tests that test isolated functions, a Journey tests how your system behaves when users perform real-world workflows. Each journey consists of:

- **Steps**: Individual actions that make API calls
- **Checkpoints**: Savepoints for database state
- **Branches**: Multiple paths to explore from checkpoints

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

## Creating a Journey

### Basic Journey

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

Add tags, descriptions, and timeouts for organization:

```python
journey = Journey(
    name="checkout_flow",
    description="Complete checkout with payment processing",
    tags=["e-commerce", "critical", "payment"],
    timeout=120.0,  # 2 minute total timeout
    steps=[...],
)
```

## Journey Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique identifier for the journey |
| `steps` | `list` | Required | Sequence of Steps, Checkpoints, and Branches |
| `description` | `str` | `""` | Human-readable description |
| `tags` | `list[str]` | `[]` | Tags for filtering/categorization |
| `timeout` | `float` | `None` | Maximum execution time in seconds |

## Steps

### Action Function Signature

Every step action receives two parameters:

```python
def action(client: Client, context: ExecutionContext) -> Any:
    """
    Args:
        client: HTTP client for making API requests
        context: Shared state between steps

    Returns:
        Typically an httpx.Response object
    """
    pass
```

### HTTP Operations

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

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique identifier for the step |
| `action` | `Callable` | Required | Function to execute |
| `description` | `str` | `""` | Human-readable description |
| `timeout` | `float` | `None` | Max execution time in seconds |
| `retries` | `int` | `0` | Number of retry attempts |
| `expect_failure` | `bool` | `False` | If True, step passes when action fails |

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
```

## Expected Failures

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

When `expect_failure=True`:

- Step **passes** if the action fails (HTTP 4xx/5xx, exception)
- Step **fails** if the action succeeds

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

### 4. Keep Actions Focused

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

### 5. Set Timeouts Appropriately

```python
# Quick operations
Step(name="health_check", action=health_check, timeout=5.0)

# Normal operations
Step(name="create_order", action=create_order, timeout=30.0)

# Long-running operations
Step(name="generate_report", action=generate_report, timeout=120.0)
```

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

## Next Steps

- [Checkpoints & Branching](branching.md) - Learn about state management and path exploration
- [State Management](state.md) - Understand how checkpoints work
- [Tutorials](../tutorials/index.md) - Step-by-step guides for specific scenarios
