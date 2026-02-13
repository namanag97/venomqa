# VenomQA

**Stateful Journey Testing Framework** - Test APIs like a human QA would.

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://pypi.org/project/venomqa/)
[![Python versions](https://img.shields.io/pypi/pyversions/venomqa.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## Why VenomQA?

Traditional API testing treats each request in isolation. But real users follow journeys through your application, and bugs emerge from specific state combinations.

**VenomQA is different:**

| Problem | VenomQA Solution |
|---------|------------------|
| Manually tracking IDs between requests | **Context-aware testing** - IDs flow automatically |
| Writing separate tests for each path | **State chain exploration** - discover all API paths |
| Isolated endpoint testing | **Real journeys** - test complete user flows |
| Missing edge cases | **Smart issue detection** - catches calculation bugs, data inconsistencies |

---

## Quick Start

```bash
# Install
pip install venomqa

# Initialize project
venomqa init my-project
cd my-project

# Run preflight checks
venomqa preflight

# Run tests
venomqa run
```

---

## Example Journey

```python
from venomqa import Journey, Step

def create_cart(client, context):
    response = client.post("/api/cart")
    context["cart_id"] = response.json()["id"]
    return response

def add_item(client, context):
    return client.post(f"/api/cart/{context['cart_id']}/items", json={
        "product_id": 123,
        "quantity": 2
    })

def checkout(client, context):
    response = client.post(f"/api/cart/{context['cart_id']}/checkout")
    context["order_id"] = response.json()["order_id"]
    return response

def verify_order(client, context):
    return client.get(f"/api/orders/{context['order_id']}")

journey = Journey(
    name="checkout_flow",
    description="Complete checkout with automatic ID chaining",
    steps=[
        Step("create_cart", create_cart),       # Returns cart_id
        Step("add_item", add_item),             # Uses cart_id
        Step("checkout", checkout),             # Uses cart_id, returns order_id
        Step("verify_order", verify_order),     # Uses order_id
    ]
)
```

**Key insight:** Context flows between steps automatically. No manual ID tracking.

---

## State Chain Exploration

Test multiple paths from a single checkpoint:

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path

journey = Journey(
    name="payment_methods",
    steps=[
        Step("login", login),
        Step("add_to_cart", add_to_cart),
        Checkpoint("ready_to_pay"),  # Save database state
        Branch(
            checkpoint_name="ready_to_pay",
            paths=[
                Path("credit_card", [Step("pay_card", pay_card)]),
                Path("paypal", [Step("pay_paypal", pay_paypal)]),
                Path("crypto", [Step("pay_crypto", pay_crypto)]),
            ]
        ),
    ]
)
```

Each payment path runs from the same database state. No flaky tests from inconsistent data.

---

## Features

### Core Testing
- **Stateful journeys** with automatic context passing
- **State chain exploration** with checkpoints and branches
- **Smart assertions** that catch data inconsistencies

### Integration
- **OpenAPI spec parsing** for automatic endpoint discovery
- **GraphQL support** with query/mutation testing
- **gRPC support** for microservices

### Infrastructure
- **Docker Compose integration** for test environments
- **Multiple database backends** (PostgreSQL, MySQL, SQLite)
- **Redis, S3, and queue adapters**

### Reporting
- **HTML reports** with visual test results
- **JSON output** for CI/CD integration
- **JUnit XML** for Jenkins/GitHub Actions
- **Slack/Discord notifications**

### Performance
- **Load testing** capabilities
- **Security scanning** integration
- **Parallel execution** support

---

## Installation Options

```bash
# Basic installation
pip install venomqa

# With PostgreSQL state management
pip install "venomqa[postgres]"

# With Redis adapters
pip install "venomqa[redis]"

# With all features
pip install "venomqa[all]"
```

**Requirements:** Python 3.10+

---

## CLI Commands

```bash
# Initialize new project
venomqa init

# Run all journeys
venomqa run

# Run specific journey
venomqa run checkout_flow

# Run with verbose output
venomqa run --verbose

# List available journeys
venomqa list

# Validate configuration
venomqa validate

# Generate reports
venomqa report --format html --output reports/
```

---

## Configuration

Create `venomqa.yaml` in your project:

```yaml
base_url: "http://localhost:8000"
db_url: "postgresql://qa:secret@localhost:5432/qa_test"
db_backend: "postgresql"
timeout: 30
retry_count: 3

report_formats:
  - html
  - junit
```

Override with environment variables:

```bash
export VENOMQA_BASE_URL="http://api.staging.example.com"
export VENOMQA_VERBOSE=true
```

---

## Documentation

### Getting Started
- [Quick Start Guide](docs/QUICKSTART.md) - Get running in 5 minutes
- [Getting Started](docs/getting-started.md) - Full installation and setup
- [Your First Journey](docs/tutorials/first-journey.md) - Step-by-step tutorial

### Core Concepts
- [Journeys](docs/journeys.md) - Writing effective test journeys
- [State Explorer](docs/STATE_CHAIN_SPEC.md) - State chain exploration deep dive
- [Branching](docs/concepts/branching.md) - Testing multiple paths

### Reference
- [CLI Reference](docs/cli.md) - All CLI commands and options
- [API Reference](docs/api.md) - Complete API documentation
- [Configuration](docs/reference/config.md) - All configuration options

### Advanced
- [Ports and Adapters](docs/ports.md) - Clean architecture patterns
- [Custom Reporters](docs/advanced/custom-reporters.md) - Build your own reporters
- [CI/CD Integration](docs/ci-cd.md) - GitHub Actions, GitLab CI

### Examples
- [Examples Gallery](docs/examples.md) - Real-world patterns
- [Todo App Example](examples/todo_app/) - Complete working example
- [FastAPI Example](examples/fastapi-example/) - FastAPI integration

---

## Project Structure

```
my-project/
├── venomqa.yaml              # Configuration
├── docker-compose.qa.yml     # Test infrastructure
├── actions/
│   ├── auth.py               # Login, logout, register
│   └── orders.py             # Order operations
├── journeys/
│   ├── checkout.py           # Checkout flows
│   └── user_management.py    # User journeys
└── reports/                  # Generated reports
```

---

## Comparison

| Feature | VenomQA | Postman | pytest | Playwright |
|---------|---------|---------|--------|------------|
| Stateful journeys | Yes | Manual | Manual | Yes |
| State branching | Yes | No | No | No |
| Context auto-flow | Yes | Manual | Manual | Manual |
| Database checkpoints | Yes | No | No | No |
| OpenAPI integration | Yes | Yes | Plugin | No |
| Load testing | Yes | Yes | Plugin | No |

---

## Contributing

We welcome contributions! See our [Contributing Guide](CONTRIBUTING.md) for details.

```bash
# Clone and setup
git clone https://github.com/venomqa/venomqa.git
cd venomqa
pip install -e ".[dev]"
pre-commit install

# Run tests
pytest
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

Built by [Naman Agarwal](https://github.com/namanagarwal) and contributors.
