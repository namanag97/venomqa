---
hide:
  - navigation
  - toc
---

<style>
.hero-section {
  text-align: center;
  padding: 2rem 0 3rem 0;
}
.hero-section h1 {
  font-size: 3.5rem;
  margin-bottom: 0.5rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.hero-tagline {
  font-size: 1.4rem;
  color: var(--md-default-fg-color--light);
  margin-bottom: 2rem;
}
.try-it-box {
  background: var(--md-code-bg-color);
  border: 1px solid var(--md-default-fg-color--lightest);
  border-radius: 8px;
  padding: 1.5rem 2rem;
  margin: 2rem auto;
  max-width: 500px;
  font-family: var(--md-code-font-family);
}
.try-it-box code {
  font-size: 1.1rem;
  color: var(--md-code-fg-color);
}
.try-it-label {
  font-size: 0.85rem;
  color: var(--md-default-fg-color--light);
  margin-bottom: 0.5rem;
  font-family: var(--md-text-font-family);
}
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
  margin: 2rem 0;
}
.feature-card {
  background: var(--md-code-bg-color);
  border-radius: 8px;
  padding: 1.5rem;
  border: 1px solid var(--md-default-fg-color--lightest);
}
.feature-card h3 {
  margin-top: 0;
  color: var(--md-primary-fg-color);
}
.step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--md-primary-fg-color);
  color: white;
  border-radius: 50%;
  font-weight: bold;
  margin-right: 0.5rem;
}
.architecture-box {
  background: var(--md-code-bg-color);
  border-radius: 8px;
  padding: 1rem;
  overflow-x: auto;
  font-family: var(--md-code-font-family);
  font-size: 0.75rem;
  line-height: 1.4;
}
</style>

<div class="hero-section" markdown>

# VenomQA

<p class="hero-tagline">State-Based API Testing Framework</p>

**Test your entire app, not just endpoints.**

<div class="try-it-box">
<div class="try-it-label">Try it now (no config needed):</div>
<code>pip install venomqa && venomqa demo</code>
</div>

<div class="button-group">
[Get Started](getting-started/quickstart.md){ .md-button .md-button--primary }
[GitHub](https://github.com/namanag97/venomqa){ .md-button }
</div>

</div>

---

## The Problem

Every action in your app has **cascading effects**. When a user uploads a file:

- Does it appear in the file list?
- Does the storage usage update?
- Does the quota remaining decrease?
- Can search find it?

Traditional API testing checks endpoints in isolation. **VenomQA tests like a human QA** - verifying consistency across your entire application after every action.

---

## Two Ways to Test

<div class="feature-grid">

<div class="feature-card" markdown>

### Journey Testing

Linear test flows with checkpoints and branching. Perfect for user flows.

```python
journey = Journey(
    name="checkout",
    steps=[
        Step(name="login", action=login),
        Step(name="add_cart", action=add_to_cart),
        Checkpoint(name="cart_ready"),
        Branch(paths=[
            Path("pay_card", [...]),
            Path("pay_wallet", [...]),
        ])
    ]
)
```

</div>

<div class="feature-card" markdown>

### State Graph Testing

Model your app as states and transitions. VenomQA explores **all paths** automatically.

```python
graph = StateGraph(name="todo_app")
graph.add_node("empty", initial=True)
graph.add_node("has_items")

graph.add_edge("empty", "has_items",
               action=create_item)
graph.add_edge("has_items", "empty",
               action=delete_all)

# Finds bugs humans miss
result = graph.explore(client)
```

</div>

</div>

---

## Core Concepts

### Journeys

A **Journey** is a complete user scenario - login, perform actions, verify results. Steps execute sequentially, passing context between them.

```python
def login(client, context):
    response = client.post("/auth/login", json={"email": "test@example.com"})
    context["token"] = response.json()["token"]  # Pass to next steps
    return response

def create_order(client, context):
    return client.post("/orders", json={"item": "widget"})

journey = Journey(
    name="order_flow",
    steps=[
        Step(name="login", action=login),
        Step(name="create_order", action=create_order),
    ]
)
```

### Checkpoints & Branches

**Checkpoint** saves the database state. **Branch** forks execution to test multiple paths from the same starting point.

```
    login
      |
      v
  add_to_cart
      |
      v
  [CHECKPOINT: cart_ready]
      |
   ___________
  |     |     |
  v     v     v
VISA  PayPal  Declined
  |     |     |
  v     v     v
verify verify verify
```

Each branch starts from the **exact same database state**. No flaky tests from inconsistent data.

### Invariants

Rules that must **always** be true, checked after every action:

```python
graph.add_invariant(
    name="count_consistent",
    check=lambda client, db, ctx: (
        client.get("/items").json()["count"] ==
        db.query("SELECT COUNT(*) FROM items")[0]
    ),
    description="API count must match database"
)
```

---

## 5-Minute Quick Start

<div class="feature-card" markdown>

<span class="step-number">1</span> **Install VenomQA**

```bash
pip install venomqa
```

<span class="step-number">2</span> **See it work (optional)**

```bash
venomqa demo
```

<span class="step-number">3</span> **Create your project**

```bash
mkdir my-tests && cd my-tests
venomqa init
```

<span class="step-number">4</span> **Configure** `venomqa.yaml`

```yaml
base_url: "http://localhost:8000"  # Your API
timeout: 30
```

<span class="step-number">5</span> **Write a journey** in `journeys/my_test.py`

```python
from venomqa import Journey, Step

def health_check(client, ctx):
    return client.get("/health")

def list_items(client, ctx):
    return client.get("/items")

journey = Journey(
    name="my_test",
    steps=[
        Step(name="health", action=health_check),
        Step(name="list", action=list_items),
    ]
)
```

<span class="step-number">6</span> **Run it**

```bash
venomqa run my_test
```

</div>

---

## Architecture Overview

```
USER                           VENOMQA                          YOUR API
 |                                |                                |
 |  venomqa run my_journey        |                                |
 |------------------------------->|                                |
 |                                |                                |
 |                    +-----------+-----------+                    |
 |                    |                       |                    |
 |                    v                       v                    |
 |              +-----------+          +-----------+               |
 |              |  Journey  |          |  State    |               |
 |              |  Runner   |          |  Graph    |               |
 |              +-----+-----+          +-----+-----+               |
 |                    |                      |                     |
 |                    v                      v                     |
 |              +----------------------------------+                |
 |              |           HTTP Client            |                |
 |              |  (retry, circuit breaker, logs)  |                |
 |              +----------------+-----------------+                |
 |                               |                                 |
 |                               | GET /items                      |
 |                               |-------------------------------->|
 |                               |                                 |
 |                               |<--- 200 OK [{...}]              |
 |                               |                                 |
 |              +----------------+-----------------+                |
 |              |          Assertions              |                |
 |              |  (HTTP, Schema, Database, Timing)|                |
 |              +----------------+-----------------+                |
 |                               |                                 |
 |              +----------------+-----------------+                |
 |              |           Reporters              |                |
 |              | (HTML, JSON, JUnit, Slack, etc.) |                |
 |              +----------------------------------+                |
 |                               |                                 |
 |<------ Results + Report ------|                                 |
```

---

## Key Features

<div class="feature-grid">

<div class="feature-card" markdown>
### State Branching
Save database checkpoints, fork to test multiple paths from same state.
</div>

<div class="feature-card" markdown>
### Invariant Checking
Rules that must always be true - catch inconsistencies across features.
</div>

<div class="feature-card" markdown>
### Auto Path Exploration
State graphs automatically find all reachable paths. Find bugs humans miss.
</div>

<div class="feature-card" markdown>
### Rich Debugging
Full request/response logs, timing, suggestions on failure.
</div>

<div class="feature-card" markdown>
### Multiple Reporters
HTML, JSON, JUnit XML, Markdown, Slack, Discord notifications.
</div>

<div class="feature-card" markdown>
### Ports & Adapters
Swap backends (Postgres, Redis, S3) without changing tests.
</div>

<div class="feature-card" markdown>
### External Service Mocking
Built-in mocks for Stripe, Twilio, SendGrid, S3.
</div>

<div class="feature-card" markdown>
### CI/CD Ready
GitHub Actions, GitLab CI, Jenkins integration out of the box.
</div>

</div>

---

## CLI Commands

```bash
venomqa demo              # See it work (no config needed)
venomqa init              # Create project structure
venomqa run               # Run all journeys
venomqa run my_journey    # Run specific journey
venomqa run --verbose     # Detailed output
venomqa run --debug       # Full request/response logs
venomqa list              # List available journeys
venomqa smoke-test        # Quick API health check
venomqa doctor            # Diagnose setup issues
```

---

## Installation Options

```bash
# Basic
pip install venomqa

# With PostgreSQL state management
pip install "venomqa[postgres]"

# With Redis adapters
pip install "venomqa[redis]"

# Everything
pip install "venomqa[all]"
```

**Requirements:** Python 3.10+

---

## What's Next?

<div class="feature-grid">

<div class="feature-card" markdown>
### [Quickstart Guide](getting-started/quickstart.md)
Step-by-step setup for your first journey.
</div>

<div class="feature-card" markdown>
### [Core Concepts](concepts/index.md)
Deep dive into Journeys, State Graphs, and Invariants.
</div>

<div class="feature-card" markdown>
### [Examples](examples/index.md)
Real-world examples: CRUD, Auth, E-commerce.
</div>

<div class="feature-card" markdown>
### [API Reference](reference/api.md)
Complete documentation for all classes.
</div>

</div>

---

<div style="text-align: center; padding: 2rem 0;">

**Built by [Naman Agarwal](https://github.com/namanagarwal)**

[GitHub](https://github.com/namanag97/venomqa) | [PyPI](https://pypi.org/project/venomqa/) | [Issues](https://github.com/namanag97/venomqa/issues)

</div>
