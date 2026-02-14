# Quickstart

Get VenomQA up and running in 5 minutes.

## Try It First (No Setup Required)

Want to see VenomQA in action before setting anything up? Run the demo:

```bash
pip install venomqa
venomqa demo
```

This starts a built-in test server and runs an example journey automatically. No configuration needed.

```
VenomQA Demo
==================================================

Starting demo server on http://127.0.0.1:8000...
Running demo journey...

Demo Journey Results
┌─────────────────┬────────┬──────────┐
│ Step            │ Status │ Duration │
├─────────────────┼────────┼──────────┤
│ health_check    │ PASS   │ 12ms     │
│ list_items      │ PASS   │ 8ms      │
│ create_item     │ PASS   │ 15ms     │
│ get_item        │ PASS   │ 6ms      │
│ update_item     │ PASS   │ 9ms      │
│ delete_item     │ PASS   │ 7ms      │
│ verify_deleted  │ PASS   │ 5ms      │
└─────────────────┴────────┴──────────┘

Demo Complete!
```

---

## Prerequisites

To test your own APIs, you need:

1. **Python 3.10+** installed
2. **An API to test** - If you don't have one, use our test server:

### Option A: Use the VenomQA Test Server (Recommended for beginners)

We provide a simple test server so you can start immediately:

```bash
# Clone the repo (if you haven't already)
git clone https://github.com/namanagarwal/venomqa.git
cd venomqa/examples/quickstart

# Install the test server dependencies
pip install fastapi uvicorn pydantic

# Start the test server
python test_server.py
```

The test server runs at `http://localhost:8000` and provides:
- `GET /health` - Health check
- `GET /items` - List items
- `POST /items` - Create item
- `GET /items/{id}` - Get item
- `PUT /items/{id}` - Update item
- `DELETE /items/{id}` - Delete item

**Keep this terminal running** and open a new terminal for the next steps.

### Option B: Use Your Own API

If you have an existing API, update the `base_url` in `venomqa.yaml` to point to it.

## Install VenomQA

```bash
pip install venomqa
```

Verify the installation:

```bash
venomqa --version
```

## Which API Should I Use?

VenomQA offers multiple approaches. Here's when to use each:

| Approach | Best For | Complexity |
|----------|----------|------------|
| **Journey** | Linear user flows (login -> action -> verify) | Simple |
| **StateGraph** | Testing all state transitions systematically | Medium |
| **CLI** | Quick tests, CI/CD integration | Simple |

**For beginners: Start with Journey** - it's the most intuitive.

## Create Your First Journey

### 1. Set up the project structure

```bash
mkdir my-api-tests && cd my-api-tests
mkdir journeys
```

### 2. Create a configuration file

Create `venomqa.yaml`:

```yaml
base_url: "http://localhost:8000"
timeout: 30
verbose: false
```

### 3. Write your first journey

Create `journeys/hello.py`:

```python
from venomqa import Journey, Step

def health_check(client, context):
    """Check if the API is healthy."""
    response = client.get("/health")
    # Store the result for later steps
    if response.status_code == 200:
        context["api_status"] = response.json()["status"]
    return response

def list_items(client, context):
    """List all items from the API."""
    return client.get("/items")

journey = Journey(
    name="hello_world",
    description="My first VenomQA journey",
    steps=[
        Step(name="check_health", action=health_check),
        Step(name="list_items", action=list_items),
    ],
)
```

### 4. Run the journey

```bash
venomqa run hello_world
```

You should see output like:

```
Running journey: hello_world
  [PASS] check_health (45ms)
  [PASS] list_items (32ms)

Journey completed: 2/2 steps passed
```

## CRUD Example (Create, Read, Delete)

Here's a more complete example that creates, reads, and deletes an item:

```python
# journeys/crud_flow.py
from venomqa import Journey, Step, Checkpoint, Branch, Path

def create_item(client, context):
    """Create a new item."""
    response = client.post("/items", json={
        "name": "Test Item",
        "description": "Created by VenomQA",
        "price": 19.99,
    })
    if response.status_code == 201:
        context["item_id"] = response.json()["id"]
    return response

def get_item(client, context):
    """Fetch the created item."""
    item_id = context.get("item_id")
    return client.get(f"/items/{item_id}")

def delete_item(client, context):
    """Delete the item."""
    item_id = context.get("item_id")
    return client.delete(f"/items/{item_id}")

def verify_deleted(client, context):
    """Verify item was deleted (expect 404)."""
    item_id = context.get("item_id")
    return client.get(f"/items/{item_id}")

journey = Journey(
    name="crud_flow",
    description="Test create, read, and delete operations",
    steps=[
        Step(name="create_item", action=create_item),
        Step(name="get_item", action=get_item),
        Checkpoint(name="item_exists"),
        Branch(
            checkpoint_name="item_exists",
            paths=[
                Path(name="delete_flow", steps=[
                    Step(name="delete_item", action=delete_item),
                    Step(
                        name="verify_deleted",
                        action=verify_deleted,
                        expect_failure=True,  # We expect 404
                    ),
                ]),
            ],
        ),
    ],
)
```

Run it:

```bash
venomqa run crud_flow
```

## Add Authentication

Most APIs require authentication. Here's how to handle it:

```python
# journeys/auth_flow.py
from venomqa import Journey, Step

def login(client, context):
    """Authenticate and store the token."""
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })

    if response.status_code == 200:
        token = response.json()["token"]
        context["token"] = token
        client.set_auth_token(token)  # Sets Authorization header

    return response

def get_profile(client, context):
    """Fetch authenticated user's profile."""
    return client.get("/api/users/me")

def update_profile(client, context):
    """Update user's name."""
    return client.patch("/api/users/me", json={
        "name": "Updated Name",
    })

journey = Journey(
    name="auth_flow",
    description="Test authentication and profile operations",
    steps=[
        Step(name="login", action=login),
        Step(name="get_profile", action=get_profile),
        Step(name="update_profile", action=update_profile),
    ],
)
```

Run it:

```bash
venomqa run auth_flow
```

## Use Checkpoints and Branches

VenomQA's power comes from testing multiple scenarios from the same state:

```python
# journeys/checkout.py
from venomqa import Journey, Step, Checkpoint, Branch, Path

def login(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123",
    })
    context["token"] = response.json()["token"]
    client.set_auth_token(context["token"])
    return response

def add_to_cart(client, context):
    response = client.post("/api/cart/items", json={
        "product_id": 1,
        "quantity": 2,
    })
    context["cart_id"] = response.json()["cart_id"]
    return response

def pay_with_card(client, context):
    return client.post("/api/checkout/pay", json={
        "method": "credit_card",
        "card_token": "tok_test_visa",
    })

def pay_with_wallet(client, context):
    return client.post("/api/checkout/pay", json={
        "method": "wallet",
    })

def pay_insufficient_funds(client, context):
    return client.post("/api/checkout/pay", json={
        "method": "credit_card",
        "card_token": "tok_test_declined",
    })

journey = Journey(
    name="checkout_flow",
    description="Test checkout with multiple payment methods",
    steps=[
        Step(name="login", action=login),
        Step(name="add_to_cart", action=add_to_cart),
        Checkpoint(name="cart_ready"),  # Save state here
        Branch(
            checkpoint_name="cart_ready",
            paths=[
                Path(name="credit_card", steps=[
                    Step(name="pay_card", action=pay_with_card),
                ]),
                Path(name="wallet", steps=[
                    Step(name="pay_wallet", action=pay_with_wallet),
                ]),
                Path(name="declined", steps=[
                    Step(
                        name="pay_declined",
                        action=pay_insufficient_funds,
                        expect_failure=True,  # We expect this to fail
                    ),
                ]),
            ],
        ),
    ],
)
```

Run it:

```bash
venomqa run checkout_flow
```

Output:

```
Running journey: checkout_flow
  [PASS] login (89ms)
  [PASS] add_to_cart (45ms)
  [CHECKPOINT] cart_ready

  Branch: cart_ready
    Path: credit_card
      [PASS] pay_card (123ms)
    Path: wallet
      [PASS] pay_wallet (98ms)
    Path: declined
      [PASS] pay_declined (expected failure) (67ms)

Journey completed: 3/3 paths passed
```

## Generate Reports

After running tests, generate a report:

```bash
# Markdown report (human-readable)
venomqa report --format markdown --output reports/test.md

# JUnit XML (for CI/CD)
venomqa report --format junit --output reports/junit.xml

# HTML report (shareable)
venomqa report --format html --output reports/test.html
```

## List Available Journeys

```bash
venomqa list
```

Output:

```
Found 3 journey(s):

  - hello_world (journeys/hello.py)
  - auth_flow (journeys/auth_flow.py)
  - checkout_flow (journeys/checkout.py)
```

## Using with Docker

If your API runs in Docker, use the infrastructure management:

Create `docker-compose.qa.yml`:

```yaml
version: "3.8"
services:
  api:
    image: your-api:latest
    ports:
      - "8000:8000"
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: qa_test
      POSTGRES_USER: qa
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
```

Update `venomqa.yaml`:

```yaml
base_url: "http://localhost:8000"
docker_compose_file: "docker-compose.qa.yml"
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"
```

Run with infrastructure:

```bash
venomqa run  # Starts Docker, runs tests, stops Docker
```

Or skip if services are already running:

```bash
venomqa run --no-infra
```

## Troubleshooting

### "Connection refused" error

**Problem:** `ConnectionRefusedError: [Errno 111] Connection refused`

**Solutions:**
1. Make sure your API server is running
2. Check if the `base_url` in `venomqa.yaml` is correct
3. If using the test server, ensure it's running in another terminal

```bash
# Check if something is running on port 8000
lsof -i :8000

# Start the test server if needed
cd examples/quickstart && python test_server.py
```

### "Journey not found" error

**Problem:** `JourneyNotFound: Could not find journey 'my_journey'`

**Solutions:**
1. Check that your journey file is in the `journeys/` directory
2. Ensure the file has a `journey` variable at module level
3. Verify the journey `name` matches what you're running

```bash
# List available journeys
venomqa list
```

### "Context key not found" error

**Problem:** `KeyError: 'item_id'`

**Solutions:**
1. A previous step didn't set the expected context value
2. The previous step may have failed silently
3. Use `context.get("key", default)` instead of `context["key"]`

```python
# Instead of:
item_id = context["item_id"]  # Raises KeyError if missing

# Use:
item_id = context.get("item_id")  # Returns None if missing
if not item_id:
    raise ValueError("item_id not set by previous step")
```

### Import errors

**Problem:** `ModuleNotFoundError: No module named 'venomqa'`

**Solutions:**
1. Make sure VenomQA is installed: `pip install venomqa`
2. Check you're in the right virtual environment
3. Try reinstalling: `pip uninstall venomqa && pip install venomqa`

### HTTP 422 Validation Error

**Problem:** `422 Unprocessable Entity`

**Solutions:**
1. Check your request body matches the API schema
2. Ensure required fields are provided
3. Verify data types (e.g., integers vs strings)

```python
# Check the actual error in the response
response = client.post("/items", json={"name": 123})  # Wrong type!
print(response.json())  # Shows validation errors
```

## Next Steps

You've learned the basics! Now explore:

- [Core Concepts](../concepts/index.md) - Deep dive into Journeys, Checkpoints, and Branches
- [Configuration](configuration.md) - All configuration options
- [Tutorials](../tutorials/index.md) - Step-by-step guides for specific scenarios
- [CLI Reference](../reference/cli.md) - Complete CLI documentation
- [FAQ](../faq.md) - Common questions and answers
