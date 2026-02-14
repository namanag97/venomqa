# Examples

Real-world examples of VenomQA usage patterns.

## Quick Links

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### [CRUD Operations](crud.md)

Test create, read, update, delete operations with proper validation.

</div>

<div class="feature-card" markdown>

### [Authentication Flows](auth.md)

Login, registration, password reset, and token refresh patterns.

</div>

<div class="feature-card" markdown>

### [E-commerce Checkout](checkout.md)

Complete checkout flow with multiple payment methods.

</div>

</div>

## Example Categories

| Category | Description |
|----------|-------------|
| [CRUD Operations](crud.md) | Basic CRUD with validation |
| [Authentication](auth.md) | Auth flows and security testing |
| [E-commerce](checkout.md) | Shopping cart and checkout |

## Minimal Example

The simplest possible journey:

```python
from venomqa import Journey, Step

journey = Journey(
    name="health_check",
    steps=[
        Step(
            name="check_api",
            action=lambda c, ctx: c.get("/health"),
        ),
    ],
)
```

Run it:

```bash
venomqa run health_check
```

## Common Patterns

### Context Sharing

```python
def create_user(client, context):
    response = client.post("/api/users", json={"name": "John"})
    context["user_id"] = response.json()["id"]
    return response

def get_user(client, context):
    return client.get(f"/api/users/{context['user_id']}")

journey = Journey(
    name="user_flow",
    steps=[
        Step(name="create", action=create_user),
        Step(name="retrieve", action=get_user),
    ],
)
```

### Authentication

```python
def login(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret",
    })
    if response.status_code == 200:
        client.set_auth_token(response.json()["token"])
    return response

def protected_action(client, context):
    return client.get("/api/protected")

journey = Journey(
    name="auth_flow",
    steps=[
        Step(name="login", action=login),
        Step(name="access", action=protected_action),
    ],
)
```

### Error Testing

```python
journey = Journey(
    name="error_handling",
    steps=[
        Step(
            name="unauthorized",
            action=lambda c, ctx: c.get("/api/admin"),
            expect_failure=True,
        ),
        Step(
            name="not_found",
            action=lambda c, ctx: c.get("/api/users/999999"),
            expect_failure=True,
        ),
    ],
)
```

### Branching

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path

journey = Journey(
    name="payment_test",
    steps=[
        Step(name="setup", action=setup_order),
        Checkpoint(name="ready_to_pay"),
        Branch(
            checkpoint_name="ready_to_pay",
            paths=[
                Path(name="card", steps=[
                    Step(name="pay", action=pay_with_card),
                ]),
                Path(name="wallet", steps=[
                    Step(name="pay", action=pay_with_wallet),
                ]),
            ],
        ),
    ],
)
```

## Project Structure

Recommended project layout:

```
my-tests/
├── venomqa.yaml              # Configuration
├── docker-compose.qa.yml     # Test infrastructure
├── journeys/
│   ├── __init__.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── login.py
│   │   └── registration.py
│   ├── checkout/
│   │   ├── __init__.py
│   │   └── payment.py
│   └── admin/
│       ├── __init__.py
│       └── users.py
├── actions/
│   ├── __init__.py
│   ├── auth.py               # Reusable auth actions
│   └── users.py              # Reusable user actions
└── reports/
    └── (generated)
```

## More Examples

See the [examples directory](https://github.com/venomqa/venomqa/tree/main/examples) for complete working examples:

- `quickstart/` - Getting started examples
- `fastapi-example/` - Testing a FastAPI application
- `test-server/` - Example test server
