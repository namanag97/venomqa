# Tutorials

Step-by-step guides for common testing scenarios.

## Available Tutorials

<div class="grid cards" markdown>

-   :material-play-circle:{ .lg .middle } __Your First Journey__

    ---

    Build a complete test suite from scratch. Learn actions, invariants, and exploration.

    [:octicons-arrow-right-24: Start tutorial](first-journey.md)

-   :material-credit-card:{ .lg .middle } __Testing Payment Flows__

    ---

    Test e-commerce checkout, refunds, and payment state machines.

    [:octicons-arrow-right-24: Start tutorial](payment-flows.md)

-   :material-rocket-launch:{ .lg .middle } __CI/CD Integration__

    ---

    Run VenomQA in GitHub Actions, GitLab CI, and Jenkins pipelines.

    [:octicons-arrow-right-24: Start tutorial](ci-cd.md)

</div>

## Prerequisites

Before starting tutorials, you should have:

- **Python 3.10+** installed
- **VenomQA installed**: `pip install venomqa`
- **A test API** (or use the mock server in examples)

## Learning Path

```
1. Your First Journey
   └─ Learn: Actions, Context, Invariants, Agent
   
2. Testing Payment Flows
   └─ Learn: State machines, Database rollback, Complex invariants
   
3. CI/CD Integration
   └─ Learn: Automation, Reporting, Team workflows
```

## Quick Reference

### Minimal Example

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["id"])

def create(api, context):
    resp = api.post("/items", json={"name": "test"})
    context.set("id", resp.json()["id"])
    return resp

def delete(api, context):
    id = context.get("id")
    return api.delete(f"/items/{id}") if id else None

result = Agent(
    world=world,
    actions=[Action("create", create), Action("delete", delete)],
    invariants=[Invariant("no_500s", lambda w: True, Severity.CRITICAL)],
    strategy=BFS(),
    max_steps=50,
).explore()

print(f"States: {result.states_visited}, Violations: {result.violations}")
```

### CLI Quick Start

```bash
# Install
pip install venomqa

# Run demo
venomqa demo

# Check environment
venomqa doctor

# Generate from OpenAPI
venomqa scaffold openapi spec.json

# Run exploration
venomqa run qa/
```

## Need Help?

- **Documentation**: Browse the sidebar for detailed guides
- **Examples**: See `examples/` in the repository
- **Issues**: Report bugs on [GitHub](https://github.com/namanag97/venomqa/issues)
