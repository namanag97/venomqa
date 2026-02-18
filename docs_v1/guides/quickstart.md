# Quickstart

Get VenomQA exploring your API in 5 minutes.

## Try It First

Before writing any code, see VenomQA find a real bug:

```bash
pip install venomqa
venomqa demo
```

Then scaffold a project with working examples:

```bash
venomqa init --with-sample
```

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
# explore.py
import os
from venomqa import World, Agent, BFS, Action, Invariant, Severity
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter

# 1. Create the World
api = HttpClient("http://localhost:8000")
db = PostgresAdapter(os.environ["DATABASE_URL"])

world = World(
    api=api,
    systems={
        "db": db,
    },
)

# 2. Define Actions — signature is always (api, context)
def list_users(api, context):
    resp = api.get("/users")
    resp.expect_status(200)
    context.set("users", resp.json())
    return resp

def create_user(api, context):
    resp = api.post("/users", json={
        "name": "Test User",
        "email": "test@example.com",
    })
    resp.expect_status(201)
    context.set("user_id", resp.json().get("id"))
    return resp

# 3. Define Invariants — receive a single World argument
def user_count_consistent(world):
    # Make a live API call to verify server state
    resp = world.api.get("/users")
    if resp.status_code != 200:
        return False
    api_count = len(resp.json())
    db_count = world.systems["db"].query("SELECT COUNT(*) FROM users")[0][0]
    return db_count == api_count

# 4. Create Agent and Explore
agent = Agent(
    world=world,
    actions=[
        Action(name="list_users",  execute=list_users),
        Action(name="create_user", execute=create_user),
    ],
    invariants=[
        Invariant(
            name="user_count_consistent",
            check=user_count_consistent,
            message="Database user count must match API response",
            severity=Severity.CRITICAL,
        ),
    ],
    strategy=BFS(),
    max_steps=200,
)

result = agent.explore()

# 5. Report Results
print(f"States explored:   {result.states_visited}")
print(f"Actions executed:  {result.transitions_taken}")
print(f"Action coverage:   {result.action_coverage_percent:.0f}%")
print(f"Violations found:  {len(result.violations)}")

for violation in result.violations:
    path = " → ".join(t.action_name for t in violation.reproduction_path)
    print(f"  [{violation.severity.value.upper()}] {violation.invariant_name}: {violation.message}")
    print(f"    Reproduction: {path}")
```

Run it directly:

```bash
python3 explore.py
```

Or via the CLI:

```bash
venomqa explore explore.py
```

## Step-by-Step Breakdown

### Step 1: Create the World

The World contains all systems VenomQA can interact with:

```python
world = World(
    api=HttpClient("http://localhost:8000"),  # Your API
    systems={
        "db": PostgresAdapter(os.environ["DATABASE_URL"]),  # Your database
    },
)
```

The `api` is how VenomQA executes actions. The `systems` are what VenomQA observes and rolls back between exploration branches.

**CRITICAL**: Connect to the **exact same database** your API writes to. VenomQA wraps the entire exploration in a transaction and rolls back when branching.

### Step 2: Define Actions

Actions are things a user could do. The execute function always takes `(api, context)`:

```python
def create_user(api, context):
    resp = api.post("/users", json={"name": "Test"})
    resp.expect_status(201)
    context.set("user_id", resp.json().get("id"))
    return resp

Action(name="create_user", execute=create_user)
```

Add preconditions as a list of action names that must have run first:

```python
def delete_user(api, context):
    user_id = context.get("user_id")
    return api.delete(f"/users/{user_id}")

Action(
    name="delete_user",
    execute=delete_user,
    preconditions=["create_user"],  # Only runs after create_user has succeeded
)
```

### Step 3: Define Invariants

Invariants are rules that must always be true. They receive the `World` object:

```python
def no_duplicate_emails(world):
    rows = world.systems["db"].query(
        "SELECT email, COUNT(*) FROM users GROUP BY email HAVING COUNT(*) > 1"
    )
    return rows == []

Invariant(
    name="no_duplicate_emails",
    check=no_duplicate_emails,
    message="Each email must be unique",
    severity=Severity.CRITICAL,
)
```

### Step 4: Explore

Create an Agent and call `explore()`:

```python
agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    strategy=BFS(),
    max_steps=200,
)
result = agent.explore()
```

The Agent will:
- Try every action from every reachable state
- Roll back the database to explore alternate paths
- Check all invariants after every action
- Record any violations with the exact reproduction path

### Step 5: Report

The `ExplorationResult` contains everything:

```python
# Did we find bugs?
if result.violations:
    for v in result.violations:
        path = " → ".join(t.action_name for t in v.reproduction_path)
        print(f"[{v.severity.value.upper()}] {v.invariant_name}: {v.message}")
        print(f"  Reproduction: {path}")

# Statistics
print(f"Action coverage: {result.action_coverage_percent:.1f}%")
print(f"Time:            {result.duration_ms:.0f}ms")
print(f"Success:         {result.success}")
```

## No Database? Context-Based Mode

If your API is stateless or you cannot access the database:

```python
# VenomQA tracks these context keys to distinguish states
world = World(
    api=HttpClient("http://localhost:8000"),
    state_from_context=["order_id", "order_count", "user_id"],
)
```

## Adding More Systems

### With Mock Queue

```python
from venomqa.adapters import MockQueue

world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db":    PostgresAdapter(os.environ["DATABASE_URL"]),
        "queue": MockQueue(name="tasks"),
    },
)

# Check that paid orders enqueue a job
def order_creates_job(world):
    rows = world.systems["db"].query("SELECT * FROM orders WHERE status='paid'")
    if not rows:
        return True  # No paid orders yet — invariant doesn't apply
    return world.systems["queue"].pending_count > 0

Invariant(
    name="order_creates_job",
    check=order_creates_job,
    message="Paid orders must enqueue a processing job",
    severity=Severity.HIGH,
)
```

### With Mock Email

```python
from venomqa.adapters import MockMail

world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db":   PostgresAdapter(os.environ["DATABASE_URL"]),
        "mail": MockMail(),
    },
)

# Check that signup sends a welcome email
def signup_sends_email(world):
    rows = world.systems["db"].query("SELECT * FROM users")
    if not rows:
        return True  # No users yet
    return world.systems["mail"].sent_count > 0

Invariant(
    name="signup_sends_email",
    check=signup_sends_email,
    message="User signup must send a welcome email",
    severity=Severity.MEDIUM,
)
```

### With Redis Cache

```python
from venomqa.adapters.redis import RedisAdapter

world = World(
    api=HttpClient("http://localhost:8000"),
    systems={
        "db":    PostgresAdapter(os.environ["DATABASE_URL"]),
        "cache": RedisAdapter("redis://localhost:6379"),
    },
)
```

## Validation Helpers

Use `expect_*` helpers in actions — VenomQA catches `AssertionError` as violations:

```python
resp.expect_status(201)              # raises if not 201
resp.expect_status(200, 201, 204)    # raises if not any of these
resp.expect_success()                # raises if not 2xx/3xx
data = resp.expect_json()            # raises if not JSON
data = resp.expect_json_field("id")  # raises if "id" missing, returns dict
items = resp.expect_json_list()      # raises if not array
resp.status_code                     # returns 0 on network error (safe)
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
        env:
          DATABASE_URL: postgresql://postgres:test@localhost/mydb
        run: |
          pip install venomqa[postgres]
          python3 explore.py

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
- [Adapters Reference](../adapters/index.md) — Configure databases, caches, and mock systems
