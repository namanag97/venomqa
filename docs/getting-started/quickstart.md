# Quickstart

Get VenomQA up and running in 5 minutes.

## Install VenomQA

```bash
pip install venomqa
```

Verify the installation:

```bash
venomqa --version
```

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
    return client.get("/health")

def get_version(client, context):
    """Get API version information."""
    response = client.get("/api/version")
    context["version"] = response.json().get("version")
    return response

journey = Journey(
    name="hello_world",
    description="My first VenomQA journey",
    steps=[
        Step(name="check_health", action=health_check),
        Step(name="get_version", action=get_version),
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
  [PASS] get_version (32ms)

Journey completed: 2/2 steps passed
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

## Next Steps

You've learned the basics! Now explore:

- [Core Concepts](../concepts/index.md) - Deep dive into Journeys, Checkpoints, and Branches
- [Configuration](configuration.md) - All configuration options
- [Tutorials](../tutorials/index.md) - Step-by-step guides for specific scenarios
- [CLI Reference](../reference/cli.md) - Complete CLI documentation
