# VenomQA

A **stateful journey testing framework** for API QA with database checkpointing and branch exploration.

VenomQA lets you test complex user flows while automatically exploring multiple execution paths from saved database states. Unlike traditional test runners, it can fork execution at checkpoints, test alternative scenarios, and roll back to pristine state between branches.

## Features

- **State Branching** - Save database checkpoints and fork execution to test multiple paths from the same state
- **Journey DSL** - Declarative syntax for defining user flows with Steps, Checkpoints, and Branches
- **Issue Capture** - Automatic failure detection with request/response logs and fix suggestions
- **Infrastructure Management** - Docker Compose integration for isolated test environments
- **Context Passing** - Share data between steps with typed execution context
- **Rich Reporters** - Markdown, JSON, JUnit XML, and HTML output formats

## Installation

```bash
pip install venomqa
```

For PostgreSQL state management:

```bash
pip install "venomqa[postgres]"
```

## Quick Start

Create a journey file `journeys/my_journey.py`:

```python
from venomqa import Journey, Step, Branch, Path, Checkpoint
from venomqa.core.context import ExecutionContext

def login(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret"
    })
    return response

def create_order(client, context):
    return client.post("/api/orders", json={
        "item_id": context["item_id"],
        "quantity": 1
    })

def pay_with_card(client, context):
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "credit_card"
    })

def pay_with_wallet(client, context):
    return client.post("/api/payments", json={
        "order_id": context["order_id"],
        "method": "wallet"
    })

journey = Journey(
    name="checkout_flow",
    description="Test checkout with multiple payment methods",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create_order", action=create_order),
        Checkpoint(name="order_created"),
        Branch(
            checkpoint_name="order_created",
            paths=[
                Path(name="card_payment", steps=[
                    Step(name="pay_card", action=pay_with_card),
                ]),
                Path(name="wallet_payment", steps=[
                    Step(name="pay_wallet", action=pay_with_wallet),
                ]),
            ]
        ),
    ],
)
```

Run the journey:

```bash
venomqa run checkout_flow
```

## Core Concepts

### Journey

A complete user scenario from start to finish. Contains a sequence of Steps, Checkpoints, and Branches.

```python
journey = Journey(
    name="user_registration",
    description="Full registration flow",
    tags=["auth", "critical"],
    steps=[...],
)
```

### Step

A single action with assertions. Steps receive `(client, context)` and can access previous results.

```python
def get_profile(client, context):
    user_id = context["login_response"]["user"]["id"]
    return client.get(f"/api/users/{user_id}")

Step(
    name="fetch_profile",
    action=get_profile,
    timeout=10.0,
    retries=3,
    expect_failure=False,
)
```

### Checkpoint

A savepoint for database state. Enables rollback after exploring branches.

```python
Checkpoint(name="user_created")
```

### Branch

Forks execution to explore multiple paths from a checkpoint. Each path runs independently with state rollback between them.

```python
Branch(
    checkpoint_name="user_created",
    paths=[
        Path(name="admin_flow", steps=[...]),
        Path(name="regular_user_flow", steps=[...]),
    ]
)
```

### Path

A sequence of steps within a branch. Each path tests a different scenario from the same starting state.

```python
Path(
    name="premium_checkout",
    steps=[
        Step(name="apply_discount", action=apply_discount),
        Step(name="complete_payment", action=complete_payment),
    ]
)
```

## Configuration

Create `venomqa.yaml`:

```yaml
base_url: "http://localhost:8000"
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"
docker_compose_file: "docker-compose.qa.yml"
timeout: 30
retry_count: 3
retry_delay: 1.0
capture_logs: true
log_lines: 50
parallel_paths: 1
report_dir: "reports"
report_formats:
  - markdown
  - junit
verbose: false
fail_fast: false
```

Environment variables (prefix with `VENOMQA_`):

```bash
export VENOMQA_BASE_URL="http://api.example.com"
export VENOMQA_DB_URL="postgresql://user:pass@host/db"
export VENOMQA_TIMEOUT=60
export VENOMQA_VERBOSE=true
```

## CLI Usage

```bash
# Run all journeys
venomqa run

# Run specific journeys
venomqa run checkout_flow payment_flow

# Run with options
venomqa run checkout_flow --fail-fast --format json

# Skip infrastructure setup
venomqa run --no-infra

# List available journeys
venomqa list

# List in JSON format
venomqa list --format json

# Generate report from last run
venomqa report --format markdown --output reports/test.md
venomqa report --format junit --output reports/junit.xml
venomqa report --format html --output reports/report.html
```

### CLI Options

| Command | Option | Description |
|---------|--------|-------------|
| `run` | `--fail-fast` | Stop on first failure |
| `run` | `--format` | Output format: `text` or `json` |
| `run` | `--no-infra` | Skip Docker setup/teardown |
| `list` | `--format` | Output format: `text` or `json` |
| `report` | `--format` | Report format: `markdown`, `json`, `junit`, `html` |
| `report` | `--output` | Output file path |
| Global | `--config` | Path to config file |
| Global | `--verbose` | Enable debug logging |

## Writing Journeys

### Context Passing

Store and access data between steps:

```python
def login(client, context):
    response = client.post("/api/auth/login", json={"email": "test@example.com", "password": "secret"})
    context["token"] = response.json()["token"]
    context["user_id"] = response.json()["user"]["id"]
    return response

def get_orders(client, context):
    client.set_auth_token(context["token"])
    return client.get(f"/api/users/{context['user_id']}/orders")

journey = Journey(
    name="order_history",
    steps=[
        Step(name="login", action=login),
        Step(name="fetch_orders", action=get_orders),
    ],
)
```

### Using the ExecutionContext

```python
def create_item(client, context):
    response = client.post("/api/items", json={"name": "Test Item"})
    context.store_step_result("created_item", response.json())
    context["item_id"] = response.json()["id"]
    return response

def verify_item(client, context):
    item_id = context.get_required("item_id")
    return client.get(f"/api/items/{item_id}")
```

### Branching for Edge Cases

Test multiple outcomes from the same state:

```python
journey = Journey(
    name="order_processing",
    steps=[
        Step(name="create_order", action=create_order),
        Checkpoint(name="order_pending"),
        Branch(
            checkpoint_name="order_pending",
            paths=[
                Path(name="successful_payment", steps=[
                    Step(name="pay", action=pay_successfully),
                    Step(name="confirm_order", action=confirm_order),
                ]),
                Path(name="insufficient_funds", steps=[
                    Step(name="pay_insufficient", action=pay_insufficient, expect_failure=True),
                    Step(name="retry_payment", action=retry_payment),
                ]),
                Path(name="timeout_recovery", steps=[
                    Step(name="simulate_timeout", action=simulate_timeout),
                    Step(name="check_status", action=check_order_status),
                ]),
            ]
        ),
    ],
)
```

### Expected Failures

```python
Step(
    name="access_admin_unauthorized",
    action=lambda client, ctx: client.get("/api/admin/users"),
    expect_failure=True,
)
```

## Reporters

### Markdown

```bash
venomqa report --format markdown --output reports/test.md
```

Generates human-readable reports with pass/fail status and issue details.

### JSON

```bash
venomqa report --format json --output reports/test.json
```

Structured output for programmatic processing.

### JUnit XML

```bash
venomqa report --format junit --output reports/junit.xml
```

Compatible with CI/CD systems (Jenkins, GitLab CI, CircleCI).

### HTML

```bash
venomqa report --format html --output reports/test.html
```

Standalone HTML report with styling for sharing results.

## Issue Capture

VenomQA automatically captures failures with full context:

```python
@dataclass
class Issue:
    journey: str
    path: str
    step: str
    error: str
    severity: Severity
    request: dict | None
    response: dict | None
    logs: list[str]
    suggestion: str  # Auto-generated fix hint
```

Auto-generated suggestions cover common patterns:

| Error | Suggestion |
|-------|------------|
| 401 | Check authentication - token may be invalid or expired |
| 403 | Permission denied - check user roles and permissions |
| 404 | Endpoint not found - verify route registration and URL path |
| 422 | Validation error - check request body schema |
| 500 | Server error - check backend logs for exception traceback |
| timeout | Operation timed out - check if service is healthy |

## Infrastructure Management

VenomQA can manage Docker Compose environments:

```yaml
# docker-compose.qa.yml
version: "3.8"
services:
  api:
    build: .
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
```

The runner automatically starts/stops services when configured.

## Project Structure

```
my_project/
├── venomqa.yaml
├── docker-compose.qa.yml
├── journeys/
│   ├── __init__.py
│   ├── auth_flow.py
│   ├── checkout.py
│   └── admin.py
├── actions/
│   ├── __init__.py
│   ├── auth.py
│   └── items.py
└── reports/
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Run tests: `pytest`
5. Run linting: `ruff check . && mypy venomqa`
6. Commit changes: `git commit -m "Add my feature"`
7. Push and create a pull request

### Development Setup

```bash
git clone https://github.com/your-org/venomqa.git
cd venomqa
pip install -e ".[dev]"
pre-commit install
```

### Running Tests

```bash
pytest
pytest --cov=venomqa
pytest -k "test_branch" -v
```

## License

MIT License - see [LICENSE](LICENSE) for details.
