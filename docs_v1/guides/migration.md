# Migration Guide

This guide helps you migrate from the old VenomQA API to v1.

## Overview

v1 simplifies the API from ~300 exports to ~18 exports. The core concepts remain the same, but the implementation is cleaner and more consistent.

## Quick Comparison

| Old API | v1 API |
|---------|--------|
| `from venomqa import Journey, JourneyRunner` | `from venomqa import Journey, explore` |
| `StateManager` | `Rollbackable` protocol |
| Multiple client types | `HttpClient` |
| Complex configuration | Simple function arguments |

## Step-by-Step Migration

### 1. Update Imports

**Before:**
```python
from venomqa import (
    Journey, JourneyRunner, StateManager,
    ApiClient, DatabasePort, CachePort,
)
```

**After:**
```python
from venomqa import (
    Journey, Step, JourneyCheckpoint, explore,
    World, Agent, Invariant,
)
from venomqa.adapters import (
    HttpClient, PostgresAdapter, RedisAdapter,
)
```

### 2. Convert Journey Definitions

**Before:**
```python
journey = Journey(
    name="checkout",
    config=JourneyConfig(...),
    steps=[
        JourneyStep(name="login", action=login_fn, ...),
        JourneyCheckpoint("logged_in"),
    ],
)
```

**After:**
```python
journey = Journey(
    name="checkout",
    steps=[
        Step("login", login_action),
        Checkpoint("logged_in"),
    ],
)
```

### 3. Convert Actions

**Before:**
```python
def login_action(context):
    response = context.client.post("/login", json={"user": "test"})
    return ActionResult(response)
```

**After:**
```python
def login_action(api):
    return api.post("/login", json={"user": "test"})
```

Or using the decorator:
```python
from venomqa import action

@action(name="login", description="Log in a user")
def login(api):
    return api.post("/login", json={"user": "test"})
```

### 4. Convert Invariants

**Before:**
```python
class OrderCountInvariant(InvariantBase):
    def check(self, context):
        db_count = context.db.query_count("orders")
        api_count = len(context.client.get("/orders").json())
        return db_count == api_count
```

**After:**
```python
from venomqa import invariant, Severity

@invariant(
    name="order_count_matches",
    message="DB count must match API",
    severity=Severity.CRITICAL,
)
def order_count_inv(world):
    db_count = world.systems["db"].execute("SELECT COUNT(*) FROM orders")[0][0]
    api_count = len(world.api.get("/orders").response.json())
    return db_count == api_count
```

### 5. Convert StateManager to Rollbackable

If you have a custom StateManager, use the bridge:

```python
from venomqa.bridge import adapt_state_manager

old_manager = MyLegacyStateManager()
rollbackable = adapt_state_manager(old_manager, "db")

world = World(api=http_client, systems={"db": rollbackable})
```

### 6. Convert Journey Runner

**Before:**
```python
runner = JourneyRunner(
    journey=journey,
    client=ApiClient("http://localhost:8000"),
    state_manager=db_manager,
    cache_manager=redis_manager,
)
result = runner.run()
```

**After:**
```python
result = explore(
    base_url="http://localhost:8000",
    journey=journey,
    db_url="postgres://localhost/test",
    redis_url="redis://localhost:6379",
)
```

Or with more control:
```python
from venomqa import World, Agent, BFS
from venomqa.adapters import HttpClient, PostgresAdapter

api = HttpClient("http://localhost:8000")
world = World(
    api=api,
    systems={"db": PostgresAdapter("postgres://localhost/test")},
)

agent = Agent(
    world=world,
    actions=[login, checkout, ...],
    invariants=[order_inv, ...],
    strategy=BFS(),
)

result = agent.explore()
```

## Using the Bridge for Gradual Migration

You can use both APIs during migration:

```python
# Old journey still works
from venomqa import Journey as OldJourney

# Convert when ready
from venomqa.bridge.journey import adapt_journey

old_journey = OldJourney(...)
new_journey = adapt_journey(old_journey)

# Run with new API
result = explore("http://localhost:8000", new_journey)
```

## Key Differences

### 1. Simpler State Management

v1 uses the `Rollbackable` protocol instead of complex port/adapter hierarchies:

```python
class Rollbackable(Protocol):
    def checkpoint(self, name: str) -> SystemCheckpoint: ...
    def rollback(self, checkpoint: SystemCheckpoint) -> None: ...
    def observe(self) -> Observation: ...
```

### 2. Explicit World Object

The `World` object replaces implicit context:

```python
world = World(
    api=HttpClient(...),
    systems={
        "db": PostgresAdapter(...),
        "cache": RedisAdapter(...),
        "queue": MockQueue(),
    },
)
```

### 3. Graph-Based Exploration

v1 explicitly builds a state graph during exploration:

```python
result = agent.explore()
print(f"Visited {result.states_visited} states")
print(f"Took {result.transitions_taken} transitions")
print(f"Coverage: {result.coverage_percent}%")
```

### 4. Better Violation Tracking

Violations include reproduction paths:

```python
for violation in result.violations:
    print(f"{violation.severity}: {violation.message}")
    print("Reproduction path:")
    for transition in violation.reproduction_path:
        print(f"  -> {transition.action_name}")
```

## Deprecation Timeline

1. **v1.0**: Both old and new APIs available
2. **v1.1**: Old API shows deprecation warnings
3. **v2.0**: Old API removed

## Getting Help

If you encounter issues during migration:

1. Check this guide
2. See the [v1 documentation](../index.md)
3. File an issue on GitHub
