# VenomQA

**Test APIs like a human QA would** - State-based testing that catches what unit tests miss.

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://pypi.org/project/venomqa/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Install & Run in 60 Seconds

```bash
# Install
pip install venomqa

# Try the built-in demo (no setup needed)
venomqa demo --explain
```

That's it. You'll see VenomQA testing a sample API with state graphs, journeys, and invariants.

---

## Add to Your Project

```bash
# In your project directory
venomqa init --with-sample

# Configure (edit venomqa.yaml)
base_url: "http://localhost:8000"

# Run
venomqa smoke-test  # Quick health check
venomqa run         # Full test suite
```

---

## Why VenomQA?

Traditional tests check endpoints in isolation. Real bugs happen when features **interact**:

```
User uploads file → Does it appear in listing?
                  → Did storage usage increase?
                  → Can search find it?
                  → Did quota decrease?
```

VenomQA tests these **cross-feature effects** automatically

---

## Quick Start

```bash
pip install venomqa
```

```python
from venomqa import Client, StateGraph

# Define your app as a state graph
graph = StateGraph(name="my_app")

# Add states (nodes)
graph.add_node("empty", initial=True)
graph.add_node("has_data")

# Add transitions (edges)
graph.add_edge("empty", "has_data", action=create_item, name="create")
graph.add_edge("has_data", "empty", action=delete_item, name="delete")

# Add invariants (rules that must ALWAYS be true)
graph.add_invariant(
    "count_matches",
    check=lambda client, db, ctx: api_count == db_count,
    description="API count must match database"
)

# Explore ALL paths and verify invariants
client = Client(base_url="http://localhost:8000")
result = graph.explore(client)

print(result.summary())
# Paths explored: 18
# Invariant violations: 0
# ALL PATHS PASSED
```

---

## Key Features

### State Graph Testing
Model your app as states and transitions. VenomQA explores **all possible paths** automatically.

```
┌─────────┐  create   ┌──────────┐  complete  ┌───────────┐
│  empty  │──────────▶│ has_data │───────────▶│ completed │
└─────────┘           └──────────┘            └───────────┘
     ▲                      │                       │
     └──────── delete ──────┴───────────────────────┘
```

### Invariants
Define rules that must hold after **every** action:

```python
graph.add_invariant("usage_accurate",
    check=lambda c, db, ctx: ctx["api_usage"] == ctx["db_usage"],
    description="Storage usage must be accurate")
```

### Journey Testing
Chain steps together with automatic context flow:

```python
from venomqa import Journey, Step

def health_check(client, context):
    return client.get("/health")

def create_item(client, context):
    response = client.post("/items", json={"name": "Test", "price": 9.99})
    context["item_id"] = response.json()["id"]
    return response

def get_item(client, context):
    return client.get(f"/items/{context['item_id']}")

journey = Journey(
    name="crud_test",
    steps=[
        Step(name="health", action=health_check),
        Step(name="create", action=create_item),
        Step(name="verify", action=get_item),
    ]
)
```

Run with: `venomqa run crud_test`

### Cross-Feature Consistency
Test that changes in one feature reflect correctly everywhere:

```python
# After file upload, verify:
# - File appears in listing
# - Usage increased
# - Quota decreased
# - Search can find it
```

---

## Installation

```bash
# Basic
pip install venomqa

# With PostgreSQL
pip install "venomqa[postgres]"

# With all features
pip install "venomqa[all]"
```

**Requirements:** Python 3.10+

---

## Examples

### Test a REST API

```python
from venomqa import Client, StateGraph

graph = StateGraph(name="todo_api")
graph.add_node("empty", initial=True)
graph.add_node("has_todos")

def create_todo(client, ctx):
    resp = client.post("/todos", json={"title": "Test"})
    ctx["todo_id"] = resp.json()["id"]
    return resp

def delete_todo(client, ctx):
    return client.delete(f"/todos/{ctx['todo_id']}")

graph.add_edge("empty", "has_todos", action=create_todo)
graph.add_edge("has_todos", "empty", action=delete_todo)

graph.add_invariant("api_matches_db", check_api_db_consistency)

result = graph.explore(Client(base_url="http://localhost:8000"))
```

### Test Multiple User Paths

```python
# User can: view posts, view todos, view albums
# From posts: select post, view comments
# From todos: select todo, mark complete
# VenomQA explores ALL combinations

graph.add_node("start", initial=True)
graph.add_node("viewing_posts")
graph.add_node("viewing_todos")
graph.add_node("viewing_comments")

graph.add_edge("start", "viewing_posts", action=view_posts)
graph.add_edge("start", "viewing_todos", action=view_todos)
graph.add_edge("viewing_posts", "viewing_comments", action=select_post)
# ... etc

result = graph.explore(client, max_depth=5)
# Explores all paths up to depth 5
```

---

## Preflight Smoke Tests

Before running a full test suite, validate that your API is functional:

```bash
# Quick check
venomqa smoke-test http://localhost:8000 --token $API_TOKEN

# With configuration file
venomqa smoke-test --config preflight.yaml
```

**Output:**
```
VenomQA Preflight Smoke Test
==================================================
  [PASS] Health check 200 (42ms)
  [PASS] Auth check 200 (18ms)
  [PASS] Create resource 201 (35ms)
  [PASS] List resources 200 (22ms)

All 4 checks passed. API is ready for testing. (117ms)
```

**Configure via YAML:**
```yaml
# preflight.yaml
base_url: "${API_URL:http://localhost:8000}"

auth:
  token_env_var: "API_TOKEN"

health_checks:
  - path: /health
    expected_json: { status: "healthy" }

crud_checks:
  - path: /api/v1/items
    payload: { name: "Test ${RANDOM}" }
```

Supports environment variable substitution (`${VAR}`, `${VAR:default}`), special placeholders (`${RANDOM}`, `${UUID}`, `${TIMESTAMP}`), and multiple check types.

See [Preflight Configuration](docs/preflight-configuration.md) for full documentation.

---

## CLI

```bash
venomqa init           # Create new project
venomqa run            # Run all tests
venomqa run --verbose  # With detailed output
venomqa list           # List journeys
venomqa validate       # Check configuration
venomqa smoke-test     # Run preflight checks
```

---

## Reporting

- **HTML** - Visual reports with diagrams
- **JSON** - For CI/CD pipelines
- **JUnit XML** - For Jenkins/GitHub Actions
- **Slack/Discord** - Notifications

---

## Documentation

- [Getting Started](docs/getting-started/)
- [State Graph Guide](docs/specs/VISION.md)
- [Examples](examples/)
- [API Reference](docs/reference/)

---

## Why "Venom"?

Like venom spreading through a system, VenomQA **penetrates every corner** of your application to find inconsistencies that isolated tests miss.

---

## License

MIT License - see [LICENSE](LICENSE)

Built by [Naman Agarwal](https://github.com/namanagarwal)
