# VenomQA v1 Quickstart Examples

These examples demonstrate the v1 API: **Actions**, **Invariants**, **Agent**, and **World**.

## Quick Start

```python
from venomqa import Action, Agent, World, BFS, Invariant, Severity
from venomqa.adapters.http import HttpClient

# Define actions - signature is always (api, context)
def login(api, context):
    resp = api.post("/auth/login", json={"email": "test@example.com", "password": "pass"})
    context.set("token", resp.json().get("token"))
    return resp

def list_orders(api, context):
    resp = api.get("/orders")
    context.set("orders", resp.json())
    return resp

# Define invariants - rules that must always hold
def orders_is_array(world):
    orders = world.context.get("orders")
    return orders is None or isinstance(orders, list)

# Create agent and explore
api = HttpClient("http://localhost:8000")
world = World(api=api)

agent = Agent(
    world=world,
    actions=[
        Action(name="login", execute=login),
        Action(name="list_orders", execute=list_orders),
    ],
    invariants=[
        Invariant(name="orders_is_array", check=orders_is_array,
                  message="Orders must be an array", severity=Severity.CRITICAL),
    ],
    strategy=BFS(),
    max_steps=100,
)

result = agent.explore()
print(f"States visited: {result.states_visited}")
print(f"Violations: {len(result.violations)}")
```

## Examples

1. **simple_test.py** - Basic exploration with actions and invariants
2. **with_mock_systems.py** - Using mock adapters (queue, mail, storage) for isolated testing

## Running

```bash
# Simple test (requires running API at localhost:8000)
python3 examples/v1_quickstart/simple_test.py

# Mock systems (no external dependencies - runs immediately)
python3 examples/v1_quickstart/with_mock_systems.py
```

## Core Concepts

| Concept | Description |
|---------|-------------|
| `Action` | Callable `(api, context) -> response` — one API operation |
| `Invariant` | Rule `(world) -> bool` checked after every action |
| `World` | Sandbox: HTTP client + rollbackable systems + shared context |
| `Agent` | Orchestrates BFS/DFS exploration with checkpoints |
| `Context` | Key-value store: `context.set()` / `context.get()` |

## Key Patterns

```python
# Action with expected status
Action(name="create", execute=create_item, expected_status=[201])

# Action with precondition (only runs after create_item)
Action(name="get", execute=get_item, preconditions=["create_item"])

# Invariant with severity
Invariant(name="no_errors", check=no_server_errors,
          message="No 5xx responses", severity=Severity.CRITICAL)
```
