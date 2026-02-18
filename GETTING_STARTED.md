# Getting Started with VenomQA

VenomQA is an autonomous API testing agent. Instead of writing linear test scripts, you define **actions** (what your API can do) and **invariants** (rules that must always hold), and VenomQA explores every possible sequence to find bugs.

## Prerequisites

- Python 3.10+
- Docker (recommended)
- Your API running locally

## Installation

```bash
pip install venomqa
```

## Quick Start

```bash
venomqa init
```

This walks you through setup and creates a `venomqa/` directory with your configuration.

---

## Understanding VenomQA's Database Requirement

**VenomQA needs access to the same database your API uses.**

Here's why: Your API stores state in a database. When you call `POST /users`, it creates a row. When you call `DELETE /users/1`, it removes that row.

VenomQA explores by branching. To test both `create → update` AND `create → delete` from the same state, it needs to:

1. Run `create_user` → database now has a user row
2. Run `update_user` → check invariants
3. **ROLLBACK the database** → user row is removed
4. Run `delete_user` → test this path from the same starting point

```
                    [Initial State]
                          │
                    create_user
                          │
                    [State S1: user exists]
                          │
         ┌────────────────┼────────────────┐
         │                │                │
    update_user      delete_user      get_user
         │                │                │
    [Check]          [Check]          [Check]
         │                │                │
    ROLLBACK         ROLLBACK         ROLLBACK
    to S1            to S1            to S1
```

**Without database access, VenomQA can only test ONE linear path.**

---

## Setup Scenarios

### Scenario 1: Your API runs in Docker with PostgreSQL

This is the most common setup. Your `docker-compose.yml` looks something like:

```yaml
# Your existing docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://myuser:mypass@db:5432/myapp
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: myuser
      POSTGRES_PASSWORD: mypass
      POSTGRES_DB: myapp
    ports:
      - "5432:5432"  # Expose to host!
```

**Key point:** The database port must be exposed to the host (`5432:5432`) so VenomQA can connect.

**VenomQA configuration:**

```yaml
# venomqa/venomqa.yaml
base_url: "http://localhost:8000"
db_url: "postgresql://myuser:mypass@localhost:5432/myapp"
```

**How it works:**
1. Your API writes to `db:5432` (inside Docker network)
2. VenomQA connects to `localhost:5432` (same database, exposed port)
3. Both are accessing the same PostgreSQL instance

### Scenario 2: Your API uses SQLite

```yaml
# venomqa/venomqa.yaml
base_url: "http://localhost:8000"
db_url: "/path/to/your/app.db"
db_type: sqlite
```

VenomQA will read/write the same `.db` file your API uses.

### Scenario 3: Stateless API (no database)

If your API doesn't persist state (e.g., a calculator API), use context-based tracking:

```yaml
# venomqa/venomqa.yaml
base_url: "http://localhost:8000"
state_from_context: ["session_id", "result"]
```

This is limited — VenomQA can only distinguish states based on values you track in context.

---

## Step-by-Step: Testing a Real API

Let's walk through testing a user management API.

### Step 1: Start your API

```bash
docker-compose up -d
```

Your API is now running at `http://localhost:8000` with a database at `localhost:5432`.

### Step 2: Initialize VenomQA

```bash
venomqa init
```

Answer the questions:
- API URL: `http://localhost:8000`
- Database: PostgreSQL
- Database URL: `postgresql://myuser:mypass@localhost:5432/myapp`

### Step 3: Write actions

Create `venomqa/actions/user_actions.py`:

```python
"""Actions for testing the user API."""


def create_user(api, context):
    """Create a new user."""
    resp = api.post("/users", json={
        "name": "Test User",
        "email": "test@example.com"
    })

    if resp.status_code != 201:
        raise AssertionError(f"Expected 201, got {resp.status_code}: {resp.text}")

    data = resp.json()
    context.set("user_id", data["id"])
    return resp


def get_user(api, context):
    """Fetch the created user."""
    user_id = context.get("user_id")
    resp = api.get(f"/users/{user_id}")

    if resp.status_code != 200:
        raise AssertionError(f"Expected 200, got {resp.status_code}")

    return resp


def delete_user(api, context):
    """Delete the created user."""
    user_id = context.get("user_id")
    resp = api.delete(f"/users/{user_id}")

    if resp.status_code not in (200, 204):
        raise AssertionError(f"Expected 200/204, got {resp.status_code}")

    context.delete("user_id")
    return resp


def list_users(api, context):
    """List all users."""
    resp = api.get("/users")

    if resp.status_code != 200:
        raise AssertionError(f"Expected 200, got {resp.status_code}")

    users = resp.json()
    context.set("user_count", len(users))
    return resp
```

### Step 4: Write invariants

Add to `venomqa/actions/user_actions.py`:

```python
def list_returns_array(world):
    """GET /users must always return a JSON array."""
    resp = world.api.get("/users")
    if resp.status_code != 200:
        return False
    return isinstance(resp.json(), list)


def deleted_user_returns_404(world):
    """A deleted user should not be retrievable."""
    user_id = world.context.get("user_id")
    if user_id is not None:
        return True  # User still exists, nothing to check

    # If we had a user but it's gone, verify server agrees
    last_deleted = world.context.get("_last_deleted_id")
    if last_deleted is None:
        return True

    resp = world.api.get(f"/users/{last_deleted}")
    return resp.status_code == 404
```

### Step 5: Create an exploration

Create `venomqa/journeys/explore_users.py`:

```python
"""Explore the user API."""

import os
from venomqa import Action, Invariant, Agent, World, DFS, Severity
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter

from actions.user_actions import (
    create_user, get_user, delete_user, list_users,
    list_returns_array, deleted_user_returns_404
)

# Connect to the SAME database your API uses
api = HttpClient("http://localhost:8000")
db = PostgresAdapter(os.environ["DATABASE_URL"])

agent = Agent(
    world=World(api=api, systems={"db": db}),
    actions=[
        Action(name="create_user", execute=create_user, expected_status=[201]),
        Action(name="get_user", execute=get_user, expected_status=[200],
               preconditions=["create_user"]),
        Action(name="delete_user", execute=delete_user, expected_status=[200, 204],
               preconditions=["create_user"]),
        Action(name="list_users", execute=list_users, expected_status=[200]),
    ],
    invariants=[
        Invariant(
            name="list_returns_array",
            check=list_returns_array,
            message="GET /users must return a JSON array",
            severity=Severity.CRITICAL,
        ),
        Invariant(
            name="deleted_returns_404",
            check=deleted_user_returns_404,
            message="Deleted users must return 404",
            severity=Severity.HIGH,
        ),
    ],
    strategy=DFS(),  # Use DFS with PostgreSQL (BFS doesn't work with PG savepoints)
    max_steps=100,
)

if __name__ == "__main__":
    print("Starting exploration...")
    result = agent.explore()

    print(f"\nStates visited: {result.states_visited}")
    print(f"Transitions: {result.transitions_taken}")
    print(f"Violations: {len(result.violations)}")

    for v in result.violations:
        print(f"\n[{v.severity.value}] {v.invariant_name}")
        print(f"  {v.message}")
        print(f"  Path: {' -> '.join(t.action_name for t in v.reproduction_path)}")
```

### Step 6: Run the exploration

```bash
export DATABASE_URL="postgresql://myuser:mypass@localhost:5432/myapp"
cd venomqa
python3 journeys/explore_users.py
```

VenomQA will:
1. Try every sequence of actions (create, get, delete, list in all orders)
2. Rollback the database between branches
3. Check invariants after each action
4. Report any violations with exact reproduction paths

---

## Common Issues

### "Cannot connect to database"

Make sure:
1. The database port is exposed in docker-compose (`5432:5432`)
2. Your `db_url` uses `localhost`, not the Docker service name
3. The database is running (`docker-compose ps`)

### "VenomQA is only testing one path"

This happens when database rollback isn't working. Check:
1. You're using `systems={"db": db}` in World
2. The database URL is correct
3. You have permission to run SAVEPOINT/ROLLBACK
4. You're using `strategy=DFS()` with PostgreSQL — BFS does not work with PostgreSQL savepoints

### "Actions fail randomly"

Actions should be idempotent and validate responses:
- Don't assume success — check status codes
- Use `preconditions` to ensure dependencies run first
- Clean up context when deleting resources

---

## Next Steps

- Run `venomqa doctor` to check your environment
- Run `venomqa llm-docs` to get full API reference for AI assistants
- Read the [API Reference](https://venomqa.dev/docs/api)
- See [examples/](./examples/) for more complex scenarios
