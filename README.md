# VenomQA

**State-Based API Testing Framework** - Test your entire app, not just endpoints.

[![PyPI version](https://badge.fury.io/py/venomqa.svg)](https://pypi.org/project/venomqa/)
[![Python versions](https://img.shields.io/pypi/pyversions/venomqa.svg)](https://pypi.org/project/venomqa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## The Problem

Every action in your app has **cascading effects**. When a user uploads a file:
- Does it appear in the file list?
- Does the storage usage update?
- Does the quota remaining decrease?
- Can search find it?

Traditional API testing checks endpoints in isolation. **VenomQA tests like a human QA** - verifying consistency across your entire application after every action.

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
journey = Journey(
    name="checkout",
    steps=[
        Step("create_cart", create_cart),      # stores cart_id
        Step("add_item", add_item),            # uses cart_id
        Step("checkout", checkout),            # uses cart_id, stores order_id
        Step("verify", verify_order),          # uses order_id
    ]
)
```

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

## CLI

```bash
venomqa init           # Create new project
venomqa run            # Run all tests
venomqa run --verbose  # With detailed output
venomqa list           # List journeys
venomqa validate       # Check configuration
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
