# Writing Actions

Actions are the building blocks of exploration. Each Action represents something a user could do — typically an API call.

This guide explains how to write effective Actions.

## Anatomy of an Action

```python
Action(
    name="create_order",
    execute=lambda api: api.post("/orders", json={"product_id": 1}),
    preconditions=[lambda state: state.observations["db"].data.get("logged_in")],
    description="Create a new order",
    tags=["orders", "critical"],
)
```

| Field | Purpose |
|-------|---------|
| `name` | Unique identifier, used in logs and graphs |
| `execute` | Function that performs the action |
| `preconditions` | When is this action valid? |
| `description` | Human-readable explanation |
| `tags` | Categorization for filtering |

## The Execute Function

The `execute` function receives an `APIClient` and returns an `ActionResult`.

### Basic Pattern

```python
def create_order(api: APIClient) -> ActionResult:
    response = api.post("/orders", json={"product_id": 1, "quantity": 2})
    return ActionResult.from_response(response)

Action(name="create_order", execute=create_order)
```

### With Lambda

For simple actions, use a lambda:

```python
Action(
    name="get_orders",
    execute=lambda api: ActionResult.from_response(api.get("/orders")),
)
```

### With Request Building

For complex requests:

```python
def checkout(api: APIClient) -> ActionResult:
    # Get current cart
    cart = api.get("/cart").json()

    # Build checkout request
    response = api.post("/checkout", json={
        "cart_id": cart["id"],
        "shipping_address": {
            "street": "123 Main St",
            "city": "Anytown",
            "zip": "12345",
        },
        "payment_method": "card",
    })

    return ActionResult.from_response(response)
```

### With Authentication

If your API requires authentication:

```python
def create_order_authenticated(api: APIClient) -> ActionResult:
    # Assume token is stored after login
    # The API client should handle this via session/cookies
    response = api.post(
        "/orders",
        json={"product_id": 1},
        headers={"Authorization": f"Bearer {api.token}"},
    )
    return ActionResult.from_response(response)
```

Better: Configure the APIClient with auth once:

```python
api = APIClient(
    base_url="http://localhost:8000",
    default_headers={"Authorization": "Bearer test_token"},
)
```

## Preconditions

Preconditions define when an Action is valid. The Agent skips Actions whose preconditions fail.

### Basic Precondition

```python
def is_logged_in(state: State) -> bool:
    return state.observations.get("db", {}).data.get("logged_in", False)

Action(
    name="create_order",
    execute=...,
    preconditions=[is_logged_in],
)
```

### Multiple Preconditions

All preconditions must pass:

```python
Action(
    name="checkout",
    execute=...,
    preconditions=[
        is_logged_in,
        lambda s: s.observations["db"].data.get("cart_items", 0) > 0,
        lambda s: s.observations["db"].data.get("payment_method_set", False),
    ],
)
```

### Preconditions from Observations

Use data from any system:

```python
Action(
    name="process_next_job",
    execute=...,
    preconditions=[
        lambda s: s.observations["queue"].data.get("pending", 0) > 0,
    ],
)

Action(
    name="clear_cache",
    execute=...,
    preconditions=[
        lambda s: s.observations["cache"].data.get("count", 0) > 0,
    ],
)
```

### Preconditions Based on Previous Actions

If you need to check if a previous action occurred, encode it in observations:

```python
# In your database adapter's observe():
def observe(self) -> Observation:
    return Observation(
        system="db",
        data={
            "has_orders": self.query("SELECT COUNT(*) FROM orders")[0][0] > 0,
            "latest_order_status": self.query(
                "SELECT status FROM orders ORDER BY id DESC LIMIT 1"
            ),
        },
        observed_at=datetime.now(),
    )

# Then in preconditions:
Action(
    name="pay_order",
    preconditions=[
        lambda s: s.observations["db"].data.get("latest_order_status") == "pending",
    ],
)
```

## Action Patterns

### CRUD Actions

```python
# Create
Action(name="create_user", execute=lambda api: api.post("/users", json={...}))

# Read
Action(name="get_user", execute=lambda api: api.get("/users/1"))
Action(name="list_users", execute=lambda api: api.get("/users"))

# Update
Action(name="update_user", execute=lambda api: api.patch("/users/1", json={...}))

# Delete
Action(name="delete_user", execute=lambda api: api.delete("/users/1"))
```

### Authentication Actions

```python
Action(
    name="login",
    execute=lambda api: api.post("/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    }),
    preconditions=[lambda s: not s.observations["db"].data.get("logged_in")],
)

Action(
    name="logout",
    execute=lambda api: api.post("/auth/logout"),
    preconditions=[lambda s: s.observations["db"].data.get("logged_in")],
)

Action(
    name="refresh_token",
    execute=lambda api: api.post("/auth/refresh"),
    preconditions=[lambda s: s.observations["db"].data.get("logged_in")],
)
```

### State Transition Actions

```python
# Order state machine: pending → paid → shipped → delivered
Action(
    name="pay_order",
    execute=lambda api: api.post("/orders/1/pay", json={"method": "card"}),
    preconditions=[
        lambda s: s.observations["db"].data.get("order_status") == "pending",
    ],
)

Action(
    name="ship_order",
    execute=lambda api: api.post("/orders/1/ship"),
    preconditions=[
        lambda s: s.observations["db"].data.get("order_status") == "paid",
    ],
)

Action(
    name="deliver_order",
    execute=lambda api: api.post("/orders/1/deliver"),
    preconditions=[
        lambda s: s.observations["db"].data.get("order_status") == "shipped",
    ],
)
```

### Parameterized Actions

For actions with varying inputs, create multiple Actions or use a factory:

```python
def make_add_to_cart_action(product_id: int) -> Action:
    return Action(
        name=f"add_product_{product_id}_to_cart",
        execute=lambda api: api.post("/cart", json={"product_id": product_id}),
        preconditions=[is_logged_in],
    )

actions = [
    make_add_to_cart_action(1),
    make_add_to_cart_action(2),
    make_add_to_cart_action(3),
]
```

### Error-Inducing Actions

Include actions that should fail to test error handling:

```python
Action(
    name="create_order_invalid_product",
    execute=lambda api: api.post("/orders", json={"product_id": 99999}),
    description="Create order with non-existent product (should fail)",
)

Action(
    name="checkout_empty_cart",
    execute=lambda api: api.post("/checkout"),
    preconditions=[
        lambda s: s.observations["db"].data.get("cart_items", 0) == 0,
    ],
    description="Checkout with empty cart (should fail)",
)
```

## Generating Actions from OpenAPI

If you have an OpenAPI spec, generate Actions automatically:

```python
from venomqa.generators import OpenAPIGenerator

generator = OpenAPIGenerator("openapi.yaml")
actions = generator.generate_actions()

# This creates Actions for every endpoint:
# - POST /users → create_user
# - GET /users → list_users
# - GET /users/{id} → get_user
# - etc.
```

You'll still need to add preconditions manually for most actions.

## Best Practices

### 1. Use Descriptive Names

```python
# Good
Action(name="create_order_with_coupon", ...)
Action(name="login_with_invalid_password", ...)

# Bad
Action(name="action1", ...)
Action(name="test", ...)
```

### 2. Keep Execute Functions Simple

Each action should do one thing:

```python
# Good: Single responsibility
Action(name="add_to_cart", execute=lambda api: api.post("/cart", json={...}))
Action(name="checkout", execute=lambda api: api.post("/checkout"))

# Bad: Multiple operations
def add_and_checkout(api):
    api.post("/cart", json={...})
    return api.post("/checkout")  # This should be a separate action
```

### 3. Make Preconditions Precise

```python
# Good: Precise precondition
preconditions=[
    lambda s: s.observations["db"].data.get("order_status") == "pending",
]

# Bad: Vague precondition (might miss invalid transitions)
preconditions=[
    lambda s: s.observations["db"].data.get("has_order", False),
]
```

### 4. Include Both Happy and Unhappy Paths

```python
actions = [
    # Happy path
    Action(name="login_valid", execute=lambda api: api.post("/login", json=valid_creds)),

    # Unhappy paths
    Action(name="login_wrong_password", execute=lambda api: api.post("/login", json=wrong_pw)),
    Action(name="login_unknown_user", execute=lambda api: api.post("/login", json=unknown)),
    Action(name="login_missing_fields", execute=lambda api: api.post("/login", json={})),
]
```

### 5. Tag Actions for Filtering

```python
Action(name="login", tags=["auth", "critical"])
Action(name="update_profile", tags=["user", "non-critical"])
Action(name="delete_account", tags=["user", "destructive", "critical"])

# Later: run only critical actions
critical_actions = [a for a in actions if "critical" in a.tags]
```

## Debugging Actions

### Check if Action Executes

```python
def create_order(api: APIClient) -> ActionResult:
    print(f"Executing create_order")  # Debug output
    response = api.post("/orders", json={...})
    print(f"Response: {response.status_code}")
    return ActionResult.from_response(response)
```

### Check Preconditions

```python
def debug_preconditions(action: Action, state: State) -> None:
    for i, precond in enumerate(action.preconditions):
        result = precond(state)
        print(f"Precondition {i}: {result}")
```

### Inspect State

```python
def observe_debug(self) -> Observation:
    data = {
        "users_count": self.query("SELECT COUNT(*) FROM users")[0][0],
        "orders_count": self.query("SELECT COUNT(*) FROM orders")[0][0],
        # Add more fields to understand state
        "latest_order": self.query("SELECT * FROM orders ORDER BY id DESC LIMIT 1"),
    }
    print(f"DB State: {data}")  # Debug output
    return Observation(system="db", data=data, observed_at=datetime.now())
```
