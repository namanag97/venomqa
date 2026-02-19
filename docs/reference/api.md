# API Reference

Complete reference for VenomQA's Python API.

## Core Classes

### Action

Represents a single operation that can be performed on the API.

```python
from venomqa import Action

action = Action(
    name="create_order",           # Unique identifier
    execute=create_order_fn,        # Callable: (api, context) -> response
    precondition=None,              # Optional: (context) -> bool
    cleanup=None,                   # Optional: (api, context) -> None
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | `str` | Yes | Unique action identifier |
| `execute` | `Callable[[HttpClient, Context], Optional[Any]]` | Yes | Function to execute |
| `precondition` | `Callable[[Context], bool]` | No | Skip if returns False |
| `cleanup` | `Callable[[HttpClient, Context], None]` | No | Cleanup after execution |

**Execute Function Signature:**

```python
def execute(api: HttpClient, context: Context) -> Optional[Any]:
    """
    Execute the action.
    
    Args:
        api: HTTP client for making requests
        context: Key-value store for passing data between actions
    
    Returns:
        Response data, or None to skip this action
    """
    pass
```

---

### Invariant

A rule that must hold after every action.

```python
from venomqa import Invariant, Severity

invariant = Invariant(
    name="no_over_refund",
    check=lambda world: get_refunded() <= get_total(),
    severity=Severity.CRITICAL,
    description="Refunds cannot exceed order total",
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | `str` | Yes | Unique invariant identifier |
| `check` | `Callable[[World], bool]` | Yes | Returns True if invariant holds |
| `severity` | `Severity` | No | CRITICAL, HIGH, MEDIUM, LOW (default: MEDIUM) |
| `description` | `str` | No | Human-readable description |

**Severity Levels:**

| Level | Meaning | Default Behavior |
|-------|---------|------------------|
| `CRITICAL` | Must fix immediately | Fail exploration |
| `HIGH` | Important issue | Log and continue |
| `MEDIUM` | Standard issue | Log and continue |
| `LOW` | Minor issue | Log only |

---

### World

The sandbox containing API client, systems, and context.

```python
from venomqa import World
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter

# Option 1: Context-only state
world = World(
    api=HttpClient("http://localhost:8000"),
    state_from_context=["order_id", "user_id"],
)

# Option 2: With database rollback
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgresql://localhost/test"),
    },
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `api` | `HttpClient` | Yes | HTTP client for API calls |
| `systems` | `Dict[str, SystemAdapter]` | No | Database/cache adapters |
| `state_from_context` | `List[str]` | No | Context keys for state extraction |

**Methods:**

```python
# Checkpoint/rollback
checkpoint_id = world.checkpoint()
world.rollback(checkpoint_id)

# Context access
world.context.set("key", value)
value = world.context.get("key")
world.context.has("key")

# Serialization
snapshot = world.serialize()
world.deserialize(snapshot)
```

---

### Agent

Orchestrates exploration of the state graph.

```python
from venomqa import Agent, BFS

agent = Agent(
    world=world,
    actions=[action1, action2],
    invariants=[invariant1],
    strategy=BFS(),
    max_steps=100,
    max_depth=20,
    fail_fast=True,
    seed=42,
)

result = agent.explore()
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `world` | `World` | Yes | The sandbox |
| `actions` | `List[Action]` | Yes | Available actions |
| `invariants` | `List[Invariant]` | No | Rules to check |
| `strategy` | `Strategy` | No | Exploration strategy (default: BFS) |
| `max_steps` | `int` | No | Maximum actions to execute (default: 1000) |
| `max_depth` | `int` | No | Maximum path depth (default: infinite) |
| `fail_fast` | `bool` | No | Stop on first CRITICAL violation (default: True) |
| `seed` | `int` | No | Random seed for reproducibility |

**Methods:**

```python
# Run exploration
result = agent.explore()

# With reporter
result = agent.explore(reporter=my_reporter)
```

---

### Context

Key-value store for passing data between actions.

```python
# Set value
context.set("order_id", "abc123")

# Get value (returns None if not set)
order_id = context.get("order_id")

# Get with default
order_id = context.get("order_id", default="unknown")

# Check existence
if context.has("order_id"):
    ...

# Delete
context.delete("order_id")

# Clear all
context.clear()

# Get all keys
keys = context.keys()
```

---

### Result

The result of an exploration run.

```python
result = agent.explore()

# Properties
result.states_visited     # Number of unique states
result.transitions        # Number of action executions
result.invariants_checked # Number of invariant checks
result.violations        # List of Violation objects
result.paths_explored    # Number of complete paths
result.duration_seconds  # Time taken

# Methods
result.summary()         # Human-readable summary
result.to_dict()         # Serialize to dict
result.to_json()         # Serialize to JSON
```

---

## Strategies

### BFS (Breadth-First Search)

Explores states level by level, finding shortest paths to bugs.

```python
from venomqa import BFS

strategy = BFS()
```

### DFS (Depth-First Search)

Goes deep before backtracking, good for finding deep state issues.

```python
from venomqa import DFS

strategy = DFS(max_depth=50)
```

### CoverageGuided

Prioritizes unexplored code paths (requires coverage instrumentation).

```python
from venomqa import CoverageGuided

strategy = CoverageGuided(
    target_coverage=0.95,
    seed_corpus=[],
)
```

---

## Enums

### Severity

```python
from venomqa import Severity

Severity.CRITICAL  # Must fix
Severity.HIGH      # Important
Severity.MEDIUM    # Standard
Severity.LOW       # Minor
```

---

## Exceptions

### VenomQAError

Base exception for all VenomQA errors.

```python
from venomqa import VenomQAError
```

### InvariantViolation

Raised when an invariant fails.

```python
from venomqa import InvariantViolation

try:
    agent.explore()
except InvariantViolation as e:
    print(f"Invariant {e.invariant_name} failed: {e.message}")
```

### ExplorationError

Raised when exploration cannot continue.

```python
from venomqa import ExplorationError
```

---

## Complete Example

```python
from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

# Setup
api = HttpClient("http://localhost:8000")
world = World(api=api, state_from_context=["order_id"])

# Actions
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])
    context.set("last_status", resp.status_code)
    return resp

def refund_order(api, context):
    order_id = context.get("order_id")
    if not order_id:
        return None
    resp = api.post(f"/orders/{order_id}/refund")
    context.set("last_status", resp.status_code)
    return resp

# Invariants
no_500s = Invariant(
    name="no_server_errors",
    check=lambda w: w.context.get("last_status", 200) < 500,
    severity=Severity.CRITICAL,
)

# Run
agent = Agent(
    world=world,
    actions=[
        Action("create_order", create_order),
        Action("refund_order", refund_order),
    ],
    invariants=[no_500s],
    strategy=BFS(),
    max_steps=50,
)

result = agent.explore()
print(result.summary())
```

## Next Steps

- [CLI Reference](cli.md) - Command-line interface
- [Adapters](adapters.md) - HTTP and database adapters
- [Reporters](reporters.md) - Output formats
