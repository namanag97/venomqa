---
hide:
  - navigation
  - toc
---

<div class="hero" markdown>

# VenomQA

**Stateful Journey Testing for Modern APIs**

Test complex user flows with automatic state exploration and branch testing

<div class="button-group">
[Get Started](getting-started/quickstart.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/venomqa/venomqa){ .md-button .md-button--secondary }
</div>

</div>

---

## Why VenomQA?

Traditional API testing tools treat each test in isolation. But real users don't work that way---they follow complex journeys through your application, and bugs often emerge from specific state combinations.

**VenomQA is different.**

| Traditional Testing | VenomQA |
|---------------------|---------|
| Tests are independent | Tests are **stateful journeys** |
| Each test starts fresh | **Checkpoint** and restore database state |
| One path per test | **Branch** to explore multiple paths from one checkpoint |
| Manual test data setup | **Automatic state isolation** between branches |
| Fragile, dependent tests | **Deterministic, repeatable** test flows |

---

## Key Features

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### State Branching

Save a database checkpoint, then fork execution to test multiple scenarios from the exact same starting state. No more flaky tests from inconsistent data.

</div>

<div class="feature-card" markdown>

### Path Exploration

Automatically explore every branch of your user flows. Test the happy path, error paths, and edge cases---all from one journey definition.

</div>

<div class="feature-card" markdown>

### Ports & Adapters

Clean architecture with swappable backends. Swap Redis for Memcached, PostgreSQL for MySQL, or use mocks---all without changing your tests.

</div>

<div class="feature-card" markdown>

### Rich Reporting

Get detailed reports with request/response logs, stack traces, and fix suggestions when things fail. Export to Markdown, JSON, JUnit XML, or HTML.

</div>

<div class="feature-card" markdown>

### Infrastructure as Code

Docker Compose integration spins up isolated test environments. Every test run starts with a clean slate.

</div>

<div class="feature-card" markdown>

### CI/CD Ready

Native support for GitHub Actions, GitLab CI, Jenkins, and more. JUnit XML reports integrate seamlessly with your pipeline.

</div>

</div>

---

## Quick Example

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path

def login(client, context):
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "secret123"
    })
    context["token"] = response.json()["token"]
    return response

def create_order(client, context):
    return client.post("/api/orders", json={
        "item_id": 1,
        "quantity": 2
    })

def pay_with_card(client, context):
    return client.post("/api/payments", json={
        "method": "credit_card",
        "card_token": "tok_visa"
    })

def pay_with_wallet(client, context):
    return client.post("/api/payments", json={
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

Run it:

```bash
venomqa run checkout_flow
```

---

## Who is VenomQA for?

=== "QA Engineers"

    You're tired of maintaining flaky end-to-end tests. You want tests that are reliable, repeatable, and actually catch bugs. VenomQA's state checkpointing ensures every test starts from a known state.

=== "Backend Developers"

    You need to test complex API flows---authentication, authorization, multi-step transactions---but setting up test data for each scenario is painful. Define the journey once, branch at checkpoints, test all paths.

=== "Platform Engineers"

    You want API tests that integrate with your CI/CD pipeline. VenomQA outputs JUnit XML, has a clean CLI, and manages its own infrastructure with Docker Compose.

=== "Teams with Complex Logic"

    Your application has lots of "if this, then that" logic. Testing all paths manually is impossible. VenomQA lets you define branches and automatically explores all of them.

---

## Installation

```bash
pip install venomqa
```

With optional dependencies:

```bash
pip install "venomqa[postgres]"   # PostgreSQL state management
pip install "venomqa[redis]"      # Redis cache/queue adapters
pip install "venomqa[all]"        # Everything
```

**Requirements:** Python 3.10+

---

## What's Next?

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### [Quickstart](getting-started/quickstart.md)

Get up and running in 5 minutes with your first journey.

</div>

<div class="feature-card" markdown>

### [Core Concepts](concepts/index.md)

Understand Journeys, Checkpoints, Branches, and State Management.

</div>

<div class="feature-card" markdown>

### [Tutorials](tutorials/index.md)

Step-by-step guides for common testing scenarios.

</div>

<div class="feature-card" markdown>

### [API Reference](reference/api.md)

Complete API documentation for all public classes and functions.

</div>

</div>

---

<div style="text-align: center; margin-top: 3rem;" markdown>

**Built with care by [Naman Agarwal](https://github.com/namanagarwal) and contributors**

[GitHub](https://github.com/venomqa/venomqa) | [PyPI](https://pypi.org/project/venomqa/) | [Discord](https://discord.gg/venomqa)

</div>
