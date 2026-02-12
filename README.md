# VenomQA

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://badge.fury.io/py/venomqa)
[![Python Support](https://img.shields.io/pypi/pyversions/venomqa.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://github.com/your-org/venomqa/workflows/Tests/badge.svg)](https://github.com/your-org/venomqa/actions)
[![Coverage](https://codecov.io/gh/your-org/venomqa/branch/main/graph/badge.svg)](https://codecov.io/gh/your-org/venomqa)

A **stateful journey testing framework** for API QA with database checkpointing and branch exploration.

VenomQA lets you test complex user flows while automatically exploring multiple execution paths from saved database states. Unlike traditional test runners, it can fork execution at checkpoints, test alternative scenarios, and roll back to pristine state between branches.

## Features

- **State Branching** - Save database checkpoints and fork execution to test multiple paths from the same state
- **Journey DSL** - Declarative syntax for defining user flows with Steps, Checkpoints, and Branches
- **Ports & Adapters** - Clean architecture with swappable backends for databases, caches, queues, and more
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

def login(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret"
    })
    context["token"] = response.json()["token"]
    return response

def create_order(client, context):
    return client.post("/api/orders", json={"item_id": 1, "quantity": 1})

def pay_with_card(client, context):
    return client.post("/api/payments", json={"method": "credit_card"})

def pay_with_wallet(client, context):
    return client.post("/api/payments", json={"method": "wallet"})

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

Forks execution to explore multiple paths from a checkpoint.

```python
Branch(
    checkpoint_name="user_created",
    paths=[
        Path(name="admin_flow", steps=[...]),
        Path(name="regular_user_flow", steps=[...]),
    ]
)
```

## Ports & Adapters

VenomQA uses a **Ports and Adapters** architecture for clean separation between test logic and external dependencies.

### What are Ports?

Ports are abstract interfaces that define what operations your tests need:

```python
from venomqa.ports import CachePort, MailPort, QueuePort

# Depend on the abstraction
def test_with_cache(cache: CachePort):
    cache.set("user:1", {"name": "John"})
    assert cache.get("user:1") is not None
```

### What are Adapters?

Adapters are concrete implementations for real services:

```python
from venomqa.adapters import RedisCacheAdapter, MailhogAdapter

# Use in tests
cache = RedisCacheAdapter(host="localhost")
mail = MailhogAdapter(host="localhost")

# Wait for email
email = mail.wait_for_email(to="user@example.com", timeout=30.0)
```

### Available Adapters

| Category | Adapters |
|----------|----------|
| **Email** | MailhogAdapter, MailpitAdapter, SMTPMockAdapter |
| **Cache** | RedisCacheAdapter |
| **Queue** | RedisQueueAdapter, CeleryQueueAdapter |
| **Search** | ElasticsearchAdapter |
| **Storage** | S3StorageAdapter, LocalStorageAdapter |
| **Mock** | WireMockAdapter |
| **Time** | ControllableTimeAdapter, RealTimeAdapter |
| **Concurrency** | ThreadingConcurrencyAdapter, AsyncConcurrencyAdapter |

### Benefits

- **Testability**: Swap real services for mocks in unit tests
- **Flexibility**: Change infrastructure without modifying test code
- **Clarity**: Clear contracts between test logic and external systems

See [Ports Documentation](docs/ports.md) and [Adapters Reference](docs/adapters.md) for details.

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

# Generate report
venomqa report --format markdown --output reports/test.md
venomqa report --format junit --output reports/junit.xml
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
parallel_paths: 1
report_dir: "reports"
report_formats:
  - markdown
  - junit
```

Environment variables (prefix with `VENOMQA_`):

```bash
export VENOMQA_BASE_URL="http://api.example.com"
export VENOMQA_DB_URL="postgresql://user:pass@host/db"
export VENOMQA_VERBOSE=true
```

## Documentation

- [API Reference](docs/api.md) - Complete API documentation
- [Ports & Adapters](docs/ports.md) - Ports and Adapters architecture guide
- [Adapters Reference](docs/adapters.md) - All available adapters and configuration
- [CLI Documentation](docs/cli.md) - Full CLI usage guide
- [Writing Journeys](docs/journeys.md) - Guide to creating test journeys
- [Database Backends](docs/backends.md) - State management configuration
- [Advanced Usage](docs/advanced.md) - Caching, parallelism, custom reporters
- [Examples](docs/examples.md) - Real-world usage examples

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and contribution guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT License - see [LICENSE](LICENSE) for details.
