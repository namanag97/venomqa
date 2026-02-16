# Quickstart

Get VenomQA exploring your API in 5 minutes.

## Installation

```bash
pip install venomqa
```

For PostgreSQL support:
```bash
pip install venomqa[postgres]
```

## Minimal Example

```python
from venomqa import World, Agent, Action, Invariant
from venomqa.adapters import HttpClient, PostgresAdapter

# 1. Create the World
world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://user:pass@localhost/testdb"),
    },
)

# 2. Define Actions
actions = [
    Action(
        name="list_users",
        execute=lambda api: api.get("/users"),
    ),
    Action(
        name="create_user",
        execute=lambda api: api.post("/users", json={
            "name": "Test User",
            "email": "test@example.com",
        }),
    ),
]

# 3. Define Invariants
invariants = [
    Invariant(
        name="user_count_consistent",
        check=lambda world: (
            world.systems["db"].query("SELECT COUNT(*) FROM users")[0][0]
            == len(world.api.get("/users").json())
        ),
        message="Database user count must match API response",
    ),
]

# 4. Create Agent and Explore
agent = Agent(world=world, actions=actions, invariants=invariants)
result = agent.explore()

# 5. Report Results
print(f"States explored: {result.states_visited}")
print(f"Actions executed: {result.transitions_taken}")
print(f"Violations found: {len(result.violations)}")

for violation in result.violations:
    print(f"  BUG: {violation.invariant_name}")
    print(f"       After: {violation.action.name if violation.action else 'initial'}")
    print(f"       {violation.message}")
```

## Step-by-Step Breakdown

### Step 1: Create the World

The World contains all systems VenomQA can interact with:

```python
world = World(
    api=HttpClient("http://localhost:8000"),  # Your API
    systems={
        "db": PostgresAdapter("postgres://..."),  # Your database
    },
)
```

The `api` is how VenomQA executes actions. The `systems` are what VenomQA observes and rolls back.

### Step 2: Define Actions

Actions are things a user could do:

```python
Action(
    name="create_user",
    execute=lambda api: api.post("/users", json={"name": "Test"}),
)
```

Add preconditions for actions that require certain state:

```python
Action(
    name="delete_user",
    execute=lambda api: api.delete("/users/1"),
    preconditions=[
        lambda state: state.observations["db"].data.get("user_count", 0) > 0,
    ],
)
```

### Step 3: Define Invariants

Invariants are rules that must always be true:

```python
Invariant(
    name="no_duplicate_emails",
    check=lambda world: (
        world.systems["db"].query(
            "SELECT email, COUNT(*) FROM users GROUP BY email HAVING COUNT(*) > 1"
        ) == []
    ),
    message="Each email must be unique",
)
```

### Step 4: Explore

Create an Agent and call `explore()`:

```python
agent = Agent(world=world, actions=actions, invariants=invariants)
result = agent.explore()
```

The Agent will:
- Try every action from every reachable state
- Roll back to explore alternate paths
- Check all invariants after every action
- Record any violations

### Step 5: Report

The `ExplorationResult` contains everything:

```python
# Did we find bugs?
if result.violations:
    for v in result.violations:
        print(f"BUG: {v.invariant_name}")
        print(f"  Reproduction: {v.reproduction_path}")

# Statistics
print(f"Coverage: {result.coverage_percent:.1f}%")
print(f"Time: {result.duration_ms:.0f}ms")
```

## Adding More Systems

### With Redis Cache

```python
from venomqa.adapters import RedisAdapter

world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://..."),
        "cache": RedisAdapter("redis://localhost:6379"),
    },
)

# Now invariants can check cache too
Invariant(
    name="user_cached_after_fetch",
    check=lambda world: (
        # After fetching user 1, they should be in cache
        world.systems["cache"].get("user:1") is not None
        if world.systems["db"].query("SELECT * FROM users WHERE id=1")
        else True
    ),
)
```

### With Mock Queue

```python
from venomqa.adapters import MockQueue

world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://..."),
        "queue": MockQueue(),
    },
)

# Check that actions enqueue jobs
Invariant(
    name="order_creates_job",
    check=lambda world: (
        world.systems["queue"].observe().data["pending"] > 0
        if world.systems["db"].query("SELECT * FROM orders WHERE status='paid'")
        else True
    ),
)
```

### With Mock Email

```python
from venomqa.adapters import MockMail

world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db": PostgresAdapter("postgres://..."),
        "mail": MockMail(),
    },
)

# Check that signup sends welcome email
Invariant(
    name="signup_sends_email",
    check=lambda world: (
        world.systems["mail"].observe().data["count"] > 0
        if world.systems["db"].query("SELECT * FROM users")
        else True
    ),
)
```

## Using the DSL

For simpler scenarios, use the Journey DSL:

```python
from venomqa import Journey, Step, Checkpoint, Branch, Path, explore

journey = Journey(
    name="user_flow",
    steps=[
        Step("signup", lambda api: api.post("/signup", json={...})),
        Checkpoint("after_signup"),
        Branch(
            from_checkpoint="after_signup",
            paths=[
                Path("complete_profile", [
                    Step("add_avatar", lambda api: api.post("/avatar", ...)),
                ]),
                Path("skip_profile", [
                    Step("go_to_dashboard", lambda api: api.get("/dashboard")),
                ]),
            ],
        ),
    ],
)

result = explore(
    "http://localhost:8000",
    journey,
    db_url="postgres://...",
)
```

## Running in CI

```yaml
# .github/workflows/venomqa.yml
name: VenomQA
on: [push]

jobs:
  explore:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v3

      - name: Start API
        run: docker-compose up -d api

      - name: Run VenomQA
        run: |
          pip install venomqa[postgres]
          python explore.py

      - name: Upload Results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: venomqa-results
          path: venomqa-results/
```

## Next Steps

- [Writing Actions](writing-actions.md) — Define what VenomQA can do
- [Writing Invariants](writing-invariants.md) — Define what must be true
- [How Rollback Works](../concepts/rollback.md) — Understand the core mechanism
- [Adapters Reference](../adapters/index.md) — Configure databases, caches, etc.
