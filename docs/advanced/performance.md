# Performance Tuning

Optimize exploration speed, memory usage, and CI integration.

## Overview

VenomQA explores state spaces that can grow exponentially. This guide covers strategies to keep exploration fast and efficient.

## Key Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| States/sec | States explored per second | > 10/sec |
| Memory | RAM usage during exploration | < 1GB |
| Coverage | Action coverage achieved | > 80% |
| Time to Bug | Steps until first violation | < 100 steps |

## Exploration Strategy Selection

Different strategies have different performance characteristics:

| Strategy | Memory | Speed | Best For |
|----------|--------|-------|----------|
| **DFS** | Low | Fast | Deep exploration, PostgresAdapter |
| **BFS** | Medium | Fast | Shortest reproduction paths |
| **CoverageGuided** | Low | Medium | Maximum action coverage |
| **Random** | Low | Fast | Quick fuzzing |
| **MCTS** | Medium | Medium | Bug-focused exploration |
| **Weighted** | Low | Fast | Prioritized actions |

!!! warning "PostgreSQL + BFS incompatibility"
    PostgreSQL SAVEPOINTs are stack-based. Use **DFS** strategy with PostgresAdapter to avoid "savepoint does not exist" errors.

```python
from venomqa import Agent, DFS

agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    strategy=DFS(),  # Use DFS with PostgreSQL
    max_steps=500,
)
```

## Controlling Exploration Depth

### Step Limits

```python
agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    max_steps=100,  # Stop after 100 actions
)
```

### Coverage Targets

Stop when action coverage reaches a threshold:

```python
agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    coverage_target=0.8,  # Stop at 80% action coverage
)
```

### Action Preconditions

Limit actions to valid states:

```python
from venomqa import Action

refund_order = Action(
    name="refund_order",
    execute=refund_fn,
    preconditions=["create_order"],  # Only valid after create_order
    max_calls=2,  # Call at most twice per state
)
```

## State Pruning

### Deduplication with Context

Tell VenomQA what defines a "unique" state:

```python
world = World(
    api=api,
    state_from_context=["user_id", "order_id", "order_status"],
)
```

Without this, VenomQA may explore identical logical states multiple times.

### Observation Filtering

Customize what goes into state observations:

```python
from venomqa.adapters.postgres import PostgresAdapter

db = PostgresAdapter(
    "postgresql://localhost/test",
    observe_tables=["orders", "users"],  # Only track these
)

# Add custom observation for key state
db.add_observation_query(
    "max_order_id",
    "SELECT COALESCE(MAX(id), 0) FROM orders",
)
```

### Loop Detection

VenomQA automatically detects actions that don't change state:

```
Loop detected: 'check_status' from state abc123 has been called 3 times
without changing state. This action likely needs a precondition guard.
```

Fix with preconditions:

```python
check_status = Action(
    name="check_status",
    execute=check_fn,
    preconditions=["create_order"],  # Only valid when order exists
)
```

## Memory Optimization

### Reduce State Storage

```python
# Bad: Storing full response in context
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order", resp.json())  # Full object
    return resp

# Good: Only store what's needed
def create_order(api, context):
    resp = api.post("/orders", json={"amount": 100})
    context.set("order_id", resp.json()["id"])  # Just the ID
    return resp
```

### Clear Unused Context

```python
def cleanup_order(api, context):
    order_id = context.get("order_id")
    api.delete(f"/orders/{order_id}")
    context.delete("order_id")  # Free memory
```

### Database Connection Pooling

```python
from psycopg_pool import ConnectionPool

pool = ConnectionPool("postgresql://localhost/test", min_size=2, max_size=10)

db = PostgresAdapter(pool)
```

## Parallel Exploration

!!! note
    Parallel exploration requires careful state isolation. Each worker needs its own database connection or transaction.

### Multiple Agents

Run independent explorations in parallel:

```python
import concurrent.futures
from venomqa import Agent, Random

def run_exploration(seed: int) -> ExplorationResult:
    strategy = Random(seed=seed)
    agent = Agent(
        world=World(api=api, systems={"db": PostgresAdapter(db_url)}),
        actions=actions,
        invariants=invariants,
        strategy=strategy,
        max_steps=100,
    )
    return agent.explore()

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(run_exploration, range(4)))

# Aggregate violations
all_violations = [v for r in results for v in r.violations]
```

### Sharded State Space

Divide actions across workers:

```python
def explore_actions(action_subset: list[Action]) -> ExplorationResult:
    agent = Agent(
        world=World(api=api, systems={"db": PostgresAdapter(db_url)}),
        actions=action_subset,
        invariants=invariants,
        strategy=BFS(),
        max_steps=200,
    )
    return agent.explore()

# Split actions into chunks
chunks = [actions[i::4] for i in range(4)]

with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(explore_actions, chunks))
```

## CI/CD Optimization

### Fast Fail

Stop on first critical violation:

```python
class FailFastAgent:
    """Wrapper that exits on CRITICAL violations."""
    
    def __init__(self, agent: Agent):
        self.agent = agent
    
    def explore(self) -> ExplorationResult:
        result = self.agent.explore()
        if result.critical_violations:
            # Exit immediately with non-zero code
            import sys
            print(f"CRITICAL: {len(result.critical_violations)} violations found")
            sys.exit(1)
        return result
```

### Time Limits

```python
import signal

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Exploration timed out")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(300)  # 5 minutes

try:
    result = agent.explore()
finally:
    signal.alarm(0)
```

### Incremental Exploration

```python
import hashlib

def get_state_fingerprint(actions: list[Action]) -> str:
    """Generate fingerprint for action definitions."""
    content = "".join(f"{a.name}:{a.preconditions}" for a in actions)
    return hashlib.md5(content.encode()).hexdigest()[:8]

def run_incremental(agent: Agent, cache_dir: str = ".venomqa_cache"):
    """Skip exploration if actions haven't changed."""
    import os
    import json
    
    fingerprint = get_state_fingerprint(agent.graph.actions)
    cache_file = f"{cache_dir}/{fingerprint}.json"
    
    if os.path.exists(cache_file):
        print("Skipping: actions unchanged")
        return json.load(open(cache_file))
    
    result = agent.explore()
    
    os.makedirs(cache_dir, exist_ok=True)
    json.dump({"violations": len(result.violations)}, open(cache_file, "w"))
    
    return result
```

### Matrix Configuration

```yaml
# .github/workflows/venomqa.yml
jobs:
  explore:
    strategy:
      matrix:
        strategy: [dfs, bfs, coverage]
        max_steps: [100, 500, 1000]
        exclude:
          - strategy: bfs
            max_steps: 1000  # Too slow
    runs-on: ubuntu-latest
    steps:
      - run: venomqa explore --strategy ${{ matrix.strategy }} --max-steps ${{ matrix.max_steps }}
```

## Benchmarks

### Test Environment

- Python 3.11
- PostgreSQL 15
- 8 CPU cores, 16GB RAM
- Local network

### Simple API (5 actions)

| Strategy | Steps | States | Time | Memory |
|----------|-------|--------|------|--------|
| DFS | 50 | 12 | 0.8s | 45MB |
| BFS | 50 | 12 | 0.9s | 48MB |
| CoverageGuided | 50 | 14 | 1.1s | 42MB |
| Random | 50 | 18 | 0.7s | 40MB |

### Medium API (15 actions)

| Strategy | Steps | States | Time | Memory |
|----------|-------|--------|------|--------|
| DFS | 200 | 45 | 4.2s | 120MB |
| BFS | 200 | 43 | 4.8s | 180MB |
| CoverageGuided | 200 | 52 | 5.1s | 95MB |
| Random | 200 | 67 | 3.9s | 88MB |

### Complex API (30 actions)

| Strategy | Steps | States | Time | Memory |
|----------|-------|--------|------|--------|
| DFS | 500 | 89 | 18s | 340MB |
| BFS | 500 | 85 | 24s | 520MB |
| CoverageGuided | 500 | 112 | 22s | 280MB |
| Random | 500 | 156 | 15s | 210MB |

### PostgreSQL vs SQLite

| Database | 100 Steps | 500 Steps | Notes |
|----------|-----------|-----------|-------|
| PostgreSQL | 2.1s | 12s | Requires DFS strategy |
| SQLite | 4.8s | 38s | File copy overhead |
| In-Memory | 0.3s | 1.8s | No rollback guarantee |

## Performance Checklist

- [ ] Use appropriate strategy (DFS for PostgreSQL)
- [ ] Set `max_steps` or `coverage_target`
- [ ] Add `state_from_context` for deduplication
- [ ] Use action `preconditions` to prune invalid paths
- [ ] Store minimal data in context
- [ ] Consider parallel exploration for large state spaces
- [ ] Profile with `progress_every=N` to monitor progress

## Profiling

Enable progress output:

```python
agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    max_steps=500,
    progress_every=50,  # Print every 50 steps
)

result = agent.explore()
```

Output:

```
  step 50/500 | states 12 | coverage 60% | violations 0
  step 100/500 | states 23 | coverage 80% | violations 1
  step 150/500 | states 31 | coverage 93% | violations 1
```

## Troubleshooting Slow Exploration

### Symptoms and Fixes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Exploration never finishes | Infinite loop | Add preconditions |
| Memory grows unbounded | State explosion | Add `state_from_context` |
| Steps execute but no new states | Poor state hashing | Improve observations |
| DB operations slow | Missing indexes | Index observed tables |
| API timeouts | Slow endpoints | Mock external services |
