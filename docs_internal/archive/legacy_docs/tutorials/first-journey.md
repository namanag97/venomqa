# Your First Journey

In this tutorial, you'll create a complete journey that tests a user authentication and item management flow.

**Time:** 15 minutes

**What you'll learn:**

- Creating a journey with multiple steps
- Sharing data between steps using context
- Handling authentication
- Testing error conditions

## Prerequisites

- VenomQA installed (`pip install venomqa`)
- A running API server (see [Tutorial Index](index.md) for example server)

## Step 1: Create Project Structure

```bash
mkdir my-api-tests
cd my-api-tests
mkdir journeys actions
```

Your project structure:

```
my-api-tests/
├── venomqa.yaml
├── journeys/
│   └── item_management.py
└── actions/
    ├── __init__.py
    └── auth.py
```

## Step 2: Configure VenomQA

Create `venomqa.yaml`:

```yaml
base_url: "http://localhost:8000"
timeout: 30
verbose: false
report_dir: "reports"
report_formats:
  - markdown
  - junit
```

## Step 3: Create Reusable Auth Actions

Create `actions/__init__.py`:

```python
# Empty file to make this a Python package
```

Create `actions/auth.py`:

```python
"""Reusable authentication actions."""


def login(client, context):
    """
    Authenticate user and store token.

    Stores:
        - context["token"]: JWT auth token
        - context["user_email"]: User's email
        - context["user_name"]: User's name
    """
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })

    if response.status_code == 200:
        data = response.json()
        context["token"] = data["token"]
        context["user_email"] = data["user"]["email"]
        context["user_name"] = data["user"]["name"]

        # Set auth header for all future requests
        client.set_auth_token(data["token"])

    return response


def login_invalid(client, context):
    """
    Attempt login with invalid credentials.
    This should fail with 401.
    """
    response = client.post("/api/auth/login", json={
        "email": "wrong@example.com",
        "password": "wrongpassword",
    })
    return response


def get_profile(client, context):
    """Get the authenticated user's profile."""
    return client.get("/api/users/me")
```

## Step 4: Create the Journey

Create `journeys/item_management.py`:

```python
"""
Item Management Journey

Tests the complete flow of:
1. User authentication
2. Creating an item
3. Retrieving the item
4. Deleting the item
5. Verifying deletion
"""
from venomqa import Journey, Step

# Import our reusable actions (works automatically when run via venomqa run)
from actions.auth import login, login_invalid, get_profile


def create_item(client, context):
    """Create a new item."""
    response = client.post("/api/items", json={
        "name": "Test Widget",
        "price": 29.99,
    })

    if response.status_code in [200, 201]:
        item_data = response.json()
        context["item_id"] = item_data["id"]
        context["item_name"] = item_data["name"]

    return response


def get_item(client, context):
    """Retrieve the created item."""
    item_id = context.get_required("item_id")
    return client.get(f"/api/items/{item_id}")


def delete_item(client, context):
    """Delete the item."""
    item_id = context.get_required("item_id")
    return client.delete(f"/api/items/{item_id}")


def get_deleted_item(client, context):
    """
    Try to get the deleted item.
    This should fail with 404.
    """
    item_id = context.get_required("item_id")
    return client.get(f"/api/items/{item_id}")


# Define the journey
journey = Journey(
    name="item_management",
    description="Test complete item CRUD operations with authentication",
    tags=["items", "crud", "auth"],
    steps=[
        # Authentication
        Step(
            name="login",
            action=login,
            description="Authenticate user",
        ),
        Step(
            name="verify_profile",
            action=get_profile,
            description="Verify authentication works",
        ),

        # Create and Read
        Step(
            name="create_item",
            action=create_item,
            description="Create a new item",
        ),
        Step(
            name="get_item",
            action=get_item,
            description="Retrieve the created item",
        ),

        # Delete and verify
        Step(
            name="delete_item",
            action=delete_item,
            description="Delete the item",
        ),
        Step(
            name="verify_deleted",
            action=get_deleted_item,
            description="Verify item no longer exists",
            expect_failure=True,  # We expect a 404 error
        ),
    ],
)
```

## Step 5: Run the Journey

Make sure your API server is running, then:

```bash
venomqa run item_management
```

Expected output:

```
Running journey: item_management
  [PASS] login (89ms)
  [PASS] verify_profile (23ms)
  [PASS] create_item (45ms)
  [PASS] get_item (18ms)
  [PASS] delete_item (31ms)
  [PASS] verify_deleted (expected failure) (15ms)

Journey completed: 6/6 steps passed
```

## Step 6: Add Error Testing

Let's add a journey that specifically tests error conditions.

Create `journeys/auth_errors.py`:

```python
"""
Authentication Error Testing

Tests that the API correctly handles:
1. Invalid login credentials
2. Missing authentication
3. Invalid tokens
"""
from venomqa import Journey, Step


def login_invalid_email(client, context):
    """Login with non-existent email."""
    return client.post("/api/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "secret123",
    })


def login_wrong_password(client, context):
    """Login with wrong password."""
    return client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "wrongpassword",
    })


def access_without_auth(client, context):
    """Try to access protected endpoint without auth."""
    # Don't set any auth headers
    client.clear_auth()
    return client.get("/api/users/me")


def access_with_invalid_token(client, context):
    """Try to access with an invalid token."""
    client.set_auth_token("invalid-token-12345")
    return client.get("/api/users/me")


journey = Journey(
    name="auth_errors",
    description="Test authentication error handling",
    tags=["auth", "errors", "security"],
    steps=[
        Step(
            name="invalid_email",
            action=login_invalid_email,
            description="Should reject non-existent email",
            expect_failure=True,
        ),
        Step(
            name="wrong_password",
            action=login_wrong_password,
            description="Should reject wrong password",
            expect_failure=True,
        ),
        Step(
            name="missing_auth",
            action=access_without_auth,
            description="Should reject requests without auth",
            expect_failure=True,
        ),
        Step(
            name="invalid_token",
            action=access_with_invalid_token,
            description="Should reject invalid tokens",
            expect_failure=True,
        ),
    ],
)
```

Run it:

```bash
venomqa run auth_errors
```

## Step 7: List and Run All Journeys

List all available journeys:

```bash
venomqa list
```

Output:

```
Found 2 journey(s):

  - item_management (journeys/item_management.py)
  - auth_errors (journeys/auth_errors.py)
```

Run all journeys:

```bash
venomqa run
```

## Step 8: Generate Reports

Generate a markdown report:

```bash
venomqa report --format markdown --output reports/test.md
```

Generate a JUnit XML report for CI:

```bash
venomqa report --format junit --output reports/junit.xml
```

## Understanding the Code

### Context Sharing

Data flows between steps via the `context` object:

```python
def create_item(client, context):
    response = client.post("/api/items", json={...})
    context["item_id"] = response.json()["id"]  # Store
    return response

def get_item(client, context):
    item_id = context.get_required("item_id")  # Retrieve
    return client.get(f"/api/items/{item_id}")
```

### Authentication

The client maintains auth state:

```python
def login(client, context):
    response = client.post("/api/auth/login", json={...})
    client.set_auth_token(response.json()["token"])
    return response

# All subsequent requests include the auth header
def get_profile(client, context):
    return client.get("/api/users/me")  # Auth header added automatically
```

### Expected Failures

Use `expect_failure=True` for error testing:

```python
Step(
    name="verify_deleted",
    action=get_deleted_item,
    expect_failure=True,  # Pass if action fails (404)
)
```

## Next Steps

You've created your first journey! Now learn:

- [Testing Payment Flows](payment-flows.md) - Use checkpoints and branching
- [CI/CD Integration](ci-cd.md) - Run tests in your pipeline
- [Core Concepts](../concepts/index.md) - Deep dive into VenomQA
