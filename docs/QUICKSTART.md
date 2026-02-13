# VenomQA Quick Start Guide

Get running with VenomQA in 5 minutes.

---

## Step 1: Install VenomQA

```bash
pip install venomqa
```

Verify installation:

```bash
venomqa --version
```

---

## Step 2: Initialize Your Project

```bash
# Create a new project
venomqa init my-api-tests
cd my-api-tests
```

This creates:

```
my-api-tests/
├── venomqa.yaml              # Configuration file
├── docker-compose.qa.yml     # Test infrastructure
├── actions/
│   └── __init__.py
├── journeys/
│   └── __init__.py
└── reports/
```

---

## Step 3: Configure Your API

Edit `venomqa.yaml`:

```yaml
base_url: "http://localhost:8000"  # Your API URL
timeout: 30
verbose: false
```

Or use environment variables:

```bash
export VENOMQA_BASE_URL="http://localhost:8000"
```

---

## Step 4: Write Your First Action

Create `actions/users.py`:

```python
def create_user(client, context):
    """Create a new user and store the ID."""
    response = client.post("/api/users", json={
        "name": "Test User",
        "email": "test@example.com"
    })

    # Store the user ID for later steps
    if response.status_code == 201:
        context["user_id"] = response.json()["id"]

    return response


def get_user(client, context):
    """Fetch the user we just created."""
    user_id = context["user_id"]
    return client.get(f"/api/users/{user_id}")


def delete_user(client, context):
    """Clean up the test user."""
    user_id = context["user_id"]
    return client.delete(f"/api/users/{user_id}")
```

**Key concept:** The `context` dictionary flows between steps. Store IDs, tokens, or any data you need later.

---

## Step 5: Write Your First Journey

Create `journeys/user_crud.py`:

```python
from venomqa import Journey, Step
from actions.users import create_user, get_user, delete_user

journey = Journey(
    name="user_crud",
    description="Test user create, read, delete operations",
    steps=[
        Step(name="create_user", action=create_user),
        Step(name="get_user", action=get_user),
        Step(name="delete_user", action=delete_user),
    ]
)
```

---

## Step 6: Run Preflight Checks

Before running tests, verify everything is set up correctly:

```bash
venomqa preflight
```

This checks:
- Configuration file exists and is valid
- Base URL is reachable
- Required dependencies are installed

---

## Step 7: Run Your Journey

```bash
# Run all journeys
venomqa run

# Run a specific journey
venomqa run user_crud

# Run with verbose output
venomqa run user_crud --verbose
```

---

## Step 8: View Reports

```bash
# Generate HTML report
venomqa report --format html --output reports/results.html

# Generate JUnit XML (for CI/CD)
venomqa report --format junit --output reports/junit.xml

# Generate JSON (for processing)
venomqa report --format json --output reports/results.json
```

---

## Complete Example

Here is a complete working example you can copy and run:

### `venomqa.yaml`

```yaml
base_url: "https://jsonplaceholder.typicode.com"
timeout: 30
verbose: true
```

### `actions/posts.py`

```python
def create_post(client, context):
    """Create a new post."""
    response = client.post("/posts", json={
        "title": "Test Post",
        "body": "This is a test post created by VenomQA",
        "userId": 1
    })

    if response.status_code == 201:
        context["post_id"] = response.json()["id"]

    return response


def get_post(client, context):
    """Fetch the post we created."""
    post_id = context["post_id"]
    return client.get(f"/posts/{post_id}")


def update_post(client, context):
    """Update the post."""
    post_id = context["post_id"]
    return client.put(f"/posts/{post_id}", json={
        "title": "Updated Post",
        "body": "This post was updated by VenomQA",
        "userId": 1
    })


def delete_post(client, context):
    """Delete the post."""
    post_id = context["post_id"]
    return client.delete(f"/posts/{post_id}")
```

### `journeys/posts_crud.py`

```python
from venomqa import Journey, Step
from actions.posts import create_post, get_post, update_post, delete_post

journey = Journey(
    name="posts_crud",
    description="Full CRUD operations on posts",
    tags=["smoke", "crud"],
    steps=[
        Step(name="create", action=create_post),
        Step(name="read", action=get_post),
        Step(name="update", action=update_post),
        Step(name="delete", action=delete_post),
    ]
)
```

### Run It

```bash
venomqa run posts_crud --verbose
```

---

## Adding State Branching

Test multiple paths from the same state:

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path

def login(client, context):
    response = client.post("/auth/login", json={
        "email": "user@example.com",
        "password": "password123"
    })
    context["token"] = response.json()["token"]
    return response

def add_to_cart(client, context):
    return client.post("/cart/items", json={"product_id": 1})

def pay_with_card(client, context):
    return client.post("/checkout/pay", json={"method": "card"})

def pay_with_paypal(client, context):
    return client.post("/checkout/pay", json={"method": "paypal"})

journey = Journey(
    name="checkout_payments",
    steps=[
        Step("login", login),
        Step("add_to_cart", add_to_cart),
        Checkpoint("cart_ready"),  # Save state here
        Branch(
            checkpoint_name="cart_ready",
            paths=[
                Path("card", [Step("pay_card", pay_with_card)]),
                Path("paypal", [Step("pay_paypal", pay_with_paypal)]),
            ]
        )
    ]
)
```

Each payment method runs from the same starting state.

---

## Common Patterns

### Authentication

```python
def login(client, context):
    response = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "secret"
    })

    if response.status_code == 200:
        token = response.json()["token"]
        context["token"] = token
        # Set auth header for all future requests
        client.set_auth_token(token)

    return response
```

### Error Testing

```python
journey = Journey(
    name="error_cases",
    steps=[
        Step(
            name="invalid_login",
            action=invalid_login,
            expect_failure=True  # This step should fail
        ),
    ]
)
```

### Using Context

```python
def step_one(client, context):
    response = client.post("/items")
    context["item_id"] = response.json()["id"]
    context["created_at"] = response.json()["created_at"]
    return response

def step_two(client, context):
    # Access data from previous step
    item_id = context["item_id"]
    return client.get(f"/items/{item_id}")
```

---

## Next Steps

Now that you have the basics, explore:

| Topic | Link |
|-------|------|
| Writing Journeys | [docs/journeys.md](journeys.md) |
| State Branching | [docs/concepts/branching.md](concepts/branching.md) |
| CLI Reference | [docs/cli.md](cli.md) |
| Configuration | [docs/reference/config.md](reference/config.md) |
| Examples | [docs/examples.md](examples.md) |
| CI/CD Integration | [docs/ci-cd.md](ci-cd.md) |

---

## Troubleshooting

### "Journey not found"

```bash
# Check that your journey file exports a 'journey' variable
# List discovered journeys
venomqa list
```

### "Connection refused"

```bash
# Verify your API is running
curl http://localhost:8000/health

# Check your base_url in venomqa.yaml
```

### "Context key not found"

```bash
# A step is trying to use a key that wasn't set
# Check that previous steps set the required context keys
venomqa run your_journey --verbose
```

### Enable Debug Mode

```bash
venomqa run your_journey --verbose
```

---

## Getting Help

- **Documentation:** [docs/](.)
- **Examples:** [examples/](../examples/)
- **Issues:** [GitHub Issues](https://github.com/venomqa/venomqa/issues)
- **Discussions:** [GitHub Discussions](https://github.com/venomqa/venomqa/discussions)
