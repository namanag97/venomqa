# Writing Actions

Actions are the building blocks of exploration. Each Action represents something a user could do — typically an API call.

This guide explains how to write effective Actions.

## Anatomy of an Action

```python
Action(
    name="create_order",
    execute=create_order,
    preconditions=[lambda ctx: ctx.get("user_id") is not None],
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

The `execute` function receives an `HttpClient` and a `Context`, and returns an `ActionResult` (which is what `api.get()`, `api.post()`, etc. already return — no wrapping needed).

### Basic Pattern

```python
def create_order(api, context):
    resp = api.post("/orders", json={"product_id": 1, "quantity": 2})
    resp.expect_status(201)                       # raises if not 201
    data = resp.expect_json_field("id", "total")  # raises if fields missing
    context.set("order_id", data["id"])
    context.set("order_total", data["total"])
    return resp

Action(name="create_order", execute=create_order)
```

### With Lambda

For simple read-only actions that don't need to share state, use a lambda:

```python
Action(
    name="list_orders",
    execute=lambda api, context: api.get("/orders"),
)
```

### Reading Context in an Action

Use `context.get()` to access values set by earlier actions in the same path:

```python
def refund_order(api, context):
    order_id = context.get("order_id")
    resp = api.post(f"/orders/{order_id}/refund", json={"amount": 50})
    resp.expect_status(200, 201)  # accepts either
    return resp
```

### With Request Building

For complex requests:

```python
def checkout(api, context):
    # Read cart ID stored by an earlier action
    cart_id = context.get("cart_id")

    resp = api.post("/checkout", json={
        "cart_id": cart_id,
        "shipping_address": {
            "street": "123 Main St",
            "city": "Anytown",
            "zip": "12345",
        },
        "payment_method": "card",
    })
    resp.expect_status(200, 201)
    return resp
```

### With Authentication

Configure `HttpClient` with default auth headers once — all actions share the client:

```python
from venomqa.adapters.http import HttpClient

api = HttpClient(
    base_url="http://localhost:8000",
    headers={"Authorization": "Bearer test_token"},
)
```

If the token must be obtained dynamically (e.g. after a login action), store it in context and pass it per-request:

```python
def login(api, context):
    resp = api.post("/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })
    resp.expect_status(200)
    context.set("token", resp.json()["token"])
    return resp

def create_order(api, context):
    token = context.get("token")
    resp = api.post(
        "/orders",
        json={"product_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.expect_status(201)
    context.set("order_id", resp.json()["id"])
    return resp
```

## Validation Helpers

`ActionResult` (what `api.get()` / `api.post()` return) has built-in assertion helpers. VenomQA treats `AssertionError` raised inside an action as a violation, so use these freely:

```python
resp.expect_status(201)              # raises if not 201
resp.expect_status(200, 201, 204)    # raises if not any of these
resp.expect_success()                # raises if not 2xx/3xx
data = resp.expect_json()            # raises if not JSON, returns body
data = resp.expect_json_field("id")  # raises if "id" missing, returns dict
items = resp.expect_json_list()      # raises if not array, returns list
resp.status_code                     # returns 0 on network error (safe)
resp.headers                         # returns {} on network error (safe)
```

## Preconditions

Preconditions define when an Action is valid. The Agent skips Actions whose preconditions fail.

### Context-Based Preconditions (Most Common)

Gate an action on a context key being set by an earlier action:

```python
Action(
    name="refund_order",
    execute=refund_order,
    precondition=lambda ctx: ctx.get("order_id") is not None,
)
```

### String Shorthand

Reference another action by name — the action will only run after the named action has executed at least once:

```python
Action(
    name="refund_order",
    execute=refund_order,
    preconditions=["create_order"],  # shorthand: requires create_order to have run
)
```

### Multiple Preconditions

All preconditions must pass:

```python
Action(
    name="checkout",
    execute=checkout,
    preconditions=[
        lambda ctx: ctx.get("user_id") is not None,
        lambda ctx: ctx.get("cart_id") is not None,
        lambda ctx: ctx.get("payment_method") is not None,
    ],
)
```

### Preconditions from Observations

For DB-backed state checks, use data from system observations:

```python
Action(
    name="process_next_job",
    execute=process_next_job,
    preconditions=[
        lambda s: s.observations["queue"].data.get("pending", 0) > 0,
    ],
)

Action(
    name="clear_cache",
    execute=clear_cache,
    preconditions=[
        lambda s: s.observations["cache"].data.get("count", 0) > 0,
    ],
)
```

### Preconditions Based on Previous Actions

If you need to check DB state from a previous action, encode it in your adapter's `observe()`:

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
def create_user(api, context):
    resp = api.post("/users", json={"name": "Alice", "email": "alice@example.com"})
    resp.expect_status(201)
    context.set("user_id", resp.json()["id"])
    return resp

def get_user(api, context):
    user_id = context.get("user_id")
    return api.get(f"/users/{user_id}")

def list_users(api, context):
    resp = api.get("/users")
    resp.expect_status(200)
    context.set("users", resp.expect_json_list())
    return resp

def update_user(api, context):
    user_id = context.get("user_id")
    return api.patch(f"/users/{user_id}", json={"name": "Alice Updated"})

def delete_user(api, context):
    user_id = context.get("user_id")
    return api.delete(f"/users/{user_id}")
```

### Authentication Actions

```python
Action(
    name="login",
    execute=lambda api, context: api.post("/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    }),
    preconditions=[lambda s: not s.observations["db"].data.get("logged_in")],
)

Action(
    name="logout",
    execute=lambda api, context: api.post("/auth/logout"),
    preconditions=[lambda s: s.observations["db"].data.get("logged_in")],
)

Action(
    name="refresh_token",
    execute=lambda api, context: api.post("/auth/refresh"),
    preconditions=[lambda s: s.observations["db"].data.get("logged_in")],
)
```

### State Transition Actions

```python
# Order state machine: pending → paid → shipped → delivered
Action(
    name="pay_order",
    execute=lambda api, context: api.post(
        f"/orders/{context.get('order_id')}/pay", json={"method": "card"}
    ),
    preconditions=[
        lambda s: s.observations["db"].data.get("order_status") == "pending",
    ],
)

Action(
    name="ship_order",
    execute=lambda api, context: api.post(f"/orders/{context.get('order_id')}/ship"),
    preconditions=[
        lambda s: s.observations["db"].data.get("order_status") == "paid",
    ],
)

Action(
    name="deliver_order",
    execute=lambda api, context: api.post(f"/orders/{context.get('order_id')}/deliver"),
    preconditions=[
        lambda s: s.observations["db"].data.get("order_status") == "shipped",
    ],
)
```

### Parameterized Actions

For actions with varying inputs, create multiple Actions or use a factory:

```python
def make_add_to_cart_action(product_id: int) -> Action:
    def add_to_cart(api, context):
        resp = api.post("/cart", json={"product_id": product_id})
        resp.expect_status(200, 201)
        return resp

    return Action(
        name=f"add_product_{product_id}_to_cart",
        execute=add_to_cart,
        preconditions=[lambda ctx: ctx.get("user_id") is not None],
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
    execute=lambda api, context: api.post("/orders", json={"product_id": 99999}),
    description="Create order with non-existent product (should fail)",
    expected_status=[404, 422],
)

Action(
    name="checkout_empty_cart",
    execute=lambda api, context: api.post("/checkout"),
    preconditions=[
        lambda s: s.observations["db"].data.get("cart_items", 0) == 0,
    ],
    description="Checkout with empty cart (should fail)",
    expect_failure=True,
)
```

## Generating Actions from OpenAPI

If you have an OpenAPI spec, generate Actions automatically:

```bash
venomqa scaffold openapi https://api.example.com/openapi.json \
  --base-url https://api.example.com \
  --output actions.py

python3 actions.py
```

Or programmatically:

```python
from venomqa.v1.generators.openapi_actions import generate_actions

actions = generate_actions("openapi.yaml", base_url="http://localhost:8000")

# This creates Actions for every endpoint:
# - POST /users → create_user
# - GET /users → list_users
# - GET /users/{id} → get_user
# - etc.
```

You will still need to add preconditions manually for most actions.

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
def add_to_cart(api, context):
    resp = api.post("/cart", json={"product_id": 1})
    resp.expect_status(200)
    return resp

def checkout(api, context):
    return api.post("/checkout")

# Bad: Multiple operations in one action
def add_and_checkout(api, context):
    api.post("/cart", json={"product_id": 1})
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
valid_creds = {"email": "alice@example.com", "password": "correct"}
wrong_pw    = {"email": "alice@example.com", "password": "wrong"}
unknown     = {"email": "nobody@example.com", "password": "x"}

actions = [
    # Happy path
    Action(name="login_valid", execute=lambda api, ctx: api.post("/login", json=valid_creds)),

    # Unhappy paths
    Action(name="login_wrong_password", execute=lambda api, ctx: api.post("/login", json=wrong_pw)),
    Action(name="login_unknown_user",   execute=lambda api, ctx: api.post("/login", json=unknown)),
    Action(name="login_missing_fields", execute=lambda api, ctx: api.post("/login", json={})),
]
```

### 5. Tag Actions for Filtering

```python
Action(name="login",          tags=["auth", "critical"])
Action(name="update_profile", tags=["user", "non-critical"])
Action(name="delete_account", tags=["user", "destructive", "critical"])

# Later: run only critical actions
critical_actions = [a for a in actions if "critical" in a.tags]
```

## Debugging Actions

### Check if Action Executes

```python
def create_order(api, context):
    print("Executing create_order")
    resp = api.post("/orders", json={"product_id": 1, "quantity": 2})
    print(f"Response: {resp.status_code}")
    resp.expect_status(201)
    context.set("order_id", resp.json()["id"])
    return resp
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
