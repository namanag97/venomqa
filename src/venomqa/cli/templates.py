"""Template strings for VenomQA CLI init command.

These templates are used to generate initial project files when running
`venomqa init`. Separating them from commands.py keeps the main CLI
module focused on command logic.
"""

VENOMQA_YAML_TEMPLATE = """# VenomQA Configuration
# Documentation: https://venomqa.dev/docs/configuration

# ============================================================================
# WHY DATABASE ACCESS IS REQUIRED
# ============================================================================
#
# Your API stores state in a database. When VenomQA explores different action
# sequences, it needs to ROLLBACK that database between branches so each path
# starts from the same state.
#
# Example: To test both "create -> update" AND "create -> delete", VenomQA:
#   1. Runs create_user (database now has user row)
#   2. Runs update_user, checks invariants
#   3. ROLLBACK database (user row removed)
#   4. Runs delete_user from same starting point
#
# Connect to the SAME database your API writes to:
#   $ export DATABASE_URL="postgresql://user:pass@localhost:5432/yourdb"
# ============================================================================

# Target API configuration
base_url: "http://localhost:8000"
timeout: 30

# REQUIRED for state exploration - set this to your API's database
# db_url: "postgresql://user:pass@localhost:5432/testdb"
db_url: "${DATABASE_URL}"  # Uses environment variable

# Test execution settings
verbose: false
fail_fast: false
capture_logs: true
log_lines: 50

# Report settings
report_dir: "reports"

# Docker Compose file for test infrastructure
docker_compose_file: "docker-compose.qa.yml"

# Notifications configuration (optional)
# notifications:
#   channels:
#     - type: slack
#       name: slack-qa
#       webhook_url: ${SLACK_WEBHOOK}
#       on: [failure, recovery]
#     - type: discord
#       name: discord-qa
#       webhook_url: ${DISCORD_WEBHOOK}
#       on: [failure]

# Port configurations for dependency injection (optional)
ports: []
  # - name: database
  #   adapter_type: postgres
  #   config:
  #     host: localhost
  #     port: 5432
  #     database: test_db
  # - name: time
  #   adapter_type: controllable_time
  # - name: cache
  #   adapter_type: redis
  #   config:
  #     host: localhost
  #     port: 6379
"""

DOCKER_COMPOSE_QA_TEMPLATE = """# VenomQA Docker Compose for QA environment
# Documentation: https://venomqa.dev/docs/docker

services:
  # Example: Test database
  # db:
  #   image: postgres:16
  #   environment:
  #     POSTGRES_USER: test
  #     POSTGRES_PASSWORD: test
  #     POSTGRES_DB: testdb
  #   ports:
  #     - "5432:5432"
  #   healthcheck:
  #     test: ["CMD-SHELL", "pg_isready -U test"]
  #     interval: 5s
  #     timeout: 5s
  #     retries: 5

  # Example: Your application under test
  # app:
  #   image: your-app:latest
  #   ports:
  #     - "8000:8000"
  #   environment:
  #     DATABASE_URL: postgresql://test:test@db:5432/testdb
  #   depends_on:
  #     db:
  #       condition: service_healthy

  # Example: Redis cache for testing
  # redis:
  #   image: redis:7-alpine
  #   ports:
  #     - "6379:6379"

  # Add your test services here
  placeholder:
    image: alpine:latest
    command: ["echo", "Add your services above"]
"""

ACTIONS_INIT_PY = '''"""Reusable actions for VenomQA tests (v1 API).

Actions are plain functions with signature (api, context).
  - api      : HttpClient  -- use .get() .post() .put() .patch() .delete()
  - context  : Context     -- use .get(key) / .set(key, val) -- NOT context[key]

Example:
    from venomqa import Action

    def add_to_cart(api, context):
        product_id = context.get("product_id")
        resp = api.post("/api/cart/items", json={"product_id": product_id, "quantity": 1})
        context.set("cart_id", resp.json()["id"])
        return resp

    action = Action(name="add_to_cart", execute=add_to_cart, expected_status=[201])
"""
'''

FIXTURES_INIT_PY = '''"""Test fixtures for QA tests.

Fixtures provide test data and dependencies using dependency injection.
Use the @fixture decorator with optional `depends` for dependencies.

Example:
    from venomqa.plugins import fixture

    @fixture
    def db():
        from venomqa.adapters import get_adapter
        return get_adapter("postgres")(host="localhost", database="test")

    @fixture(depends=["db"])
    def user(db):
        return db.insert("users", {"email": "test@example.com", "name": "Test User"})
"""
'''

JOURNEYS_INIT_PY = '''"""VenomQA exploration definitions (v1 API).

Define actions and invariants, then run Agent.explore() to exhaustively
test every reachable state sequence -- no linear test scripts needed.

Example:
    from venomqa import Action, Invariant, Agent, World, BFS, Severity
    from venomqa.adapters.http import HttpClient

    def create_item(api, context):
        resp = api.post("/items", json={"name": "test"})
        context.set("item_id", resp.json()["id"])
        return resp

    def list_items(api, context):
        resp = api.get("/items")
        context.set("items", resp.json())
        return resp

    def list_is_valid(world):
        items = world.context.get("items") or []
        return isinstance(items, list)

    agent = Agent(
        world=World(api=HttpClient("http://localhost:8000")),
        actions=[
            Action(name="create_item", execute=create_item, expected_status=[201]),
            Action(name="list_items",  execute=list_items,  expected_status=[200]),
        ],
        invariants=[
            Invariant(name="list_valid", check=list_is_valid,
                      message="GET /items must return a list", severity=Severity.CRITICAL),
        ],
        strategy=BFS(),
        max_steps=200,
    )
    result = agent.explore()
"""
'''

SAMPLE_ACTION_PY = '''"""Sample actions for your VenomQA tests (v1 API).

Each action has signature: (api, context)
  - api      : HttpClient -- .get() .post() .put() .patch() .delete()
  - context  : Context   -- .get(key) / .set(key, val)  <- NOT context[key]

CRITICAL: Actions MUST validate responses using expect_* helpers:
  - resp.expect_status(201)         # raises if not 201
  - resp.expect_json_field("id")    # raises if field missing
  - resp.expect_json_list()         # raises if not array

Modify these for your specific API, then register them in an Agent.
"""


def health_check(api, context):
    """Check API health status."""
    resp = api.get("/health")
    resp.expect_status(200)  # raises AssertionError if not 200
    return resp


def list_items(api, context):
    """List all items and store in context.

    Uses expect_json_list() to validate the response is an array.
    """
    resp = api.get("/api/items")
    resp.expect_status(200)
    items = resp.expect_json_list()  # raises if not a list

    context.set("items", items)
    context.set("item_count", len(items))
    return resp


def create_item(api, context):
    """Create a new item and store its ID in context.

    Uses expect_json_field() to validate required fields exist.
    """
    resp = api.post("/api/items", json={
        "name": "VenomQA Test Item",
        "description": "Created by VenomQA",
    })
    resp.expect_status(200, 201)                    # 200 or 201
    data = resp.expect_json_field("id")             # raises if "id" missing

    context.set("item_id", data["id"])
    return resp


def get_item(api, context):
    """Fetch a single item by ID.

    GOOD PATTERN: Use Action(preconditions=["create_item"]) instead of
    checking context.has() inside the action.
    """
    item_id = context.get("item_id")
    resp = api.get(f"/api/items/{item_id}")
    resp.expect_status(200)

    data = resp.expect_json()
    if data.get("id") != item_id:
        raise AssertionError(f"Wrong item returned: expected {item_id}, got {data}")

    return resp


def delete_item(api, context):
    """Delete the item created by create_item.

    GOOD PATTERN: This action should use preconditions=["create_item"]
    so VenomQA only runs it after create_item has succeeded.

    BAD PATTERN (DON'T DO THIS):
        if item_id is None:
            return api.get("/noop")   # Silent no-op - hides bugs!
    """
    item_id = context.get("item_id")
    resp = api.delete(f"/api/items/{item_id}")
    resp.expect_status(200, 204)  # raises if not 200 or 204

    # Clean up context so we know item is gone
    context.delete("item_id")
    return resp
'''


def get_readme_template(base_path: str) -> str:
    """Generate README content for an initialized project."""
    return f'''# VenomQA Test Suite

Autonomous API exploration -- define actions and invariants, let VenomQA find every bug sequence.

## Directory Structure

```
{base_path}/
|-- venomqa.yaml              # API URL and settings
|-- llm-context.md            # Paste this into any AI assistant for help
|-- actions/                  # Your action functions
|   +-- __init__.py
|   +-- sample_actions.py     # (if --with-sample)
|-- journeys/                 # Exploration scripts
|   +-- __init__.py
|   +-- sample_journey.py     # (if --with-sample)
|-- fixtures/                 # Shared test data
|   +-- __init__.py
+-- reports/                  # Generated reports
```

## Quick Start

**CRITICAL**: VenomQA needs database rollback to explore branches.

1. **Identify your API's database** -- PostgreSQL, SQLite, or none?
2. **Edit `venomqa.yaml`** -- set `base_url` AND `db_url` (same DB your API uses)
3. **Write actions** in `actions/` -- signature: `def my_action(api, context)`
4. **Run an exploration**:
   ```bash
   python3 journeys/sample_journey.py
   ```

Why database access is required: VenomQA explores by branching. To test both
`create -> update` AND `create -> delete` from the same state, it must:
1. Create -> reach state S1
2. Update -> explore branch A
3. **ROLLBACK to S1** <- requires database access
4. Delete -> explore branch B

## Actions (v1 API)

Actions MUST validate responses. Don't assume success!

```python
# actions/my_actions.py

def create_user(api, context):
    resp = api.post("/users", json={{"name": "Alice"}})

    # GOOD: Validate before using response
    if resp.status_code != 201:
        raise AssertionError(f"Create failed: {{resp.status_code}} - {{resp.text}}")
    data = resp.json()
    if "id" not in data:
        raise AssertionError(f"Missing 'id' in response: {{data}}")

    context.set("user_id", data["id"])   # <- .set(), not context["key"] =
    return resp

def get_user(api, context):
    user_id = context.get("user_id")     # <- .get(), not context["key"]
    resp = api.get(f"/users/{{user_id}}")

    if resp.status_code != 200:
        raise AssertionError(f"Get user failed: {{resp.status_code}}")
    return resp
```

## Invariants

Invariants should make LIVE API calls to verify server state, not just check context.

```python
from venomqa import Invariant, Severity

def users_list_is_valid(world):
    # GOOD: Make a live API call to verify server state
    resp = world.api.get("/users")
    if resp.status_code != 200:
        return False
    data = resp.json()
    return isinstance(data, list)   # Must be a list

def user_exists_on_server(world):
    # GOOD: Cross-check client state against server
    user_id = world.context.get("user_id")
    if user_id is None:
        return True   # Nothing to check yet
    resp = world.api.get(f"/users/{{user_id}}")
    return resp.status_code == 200

Invariant(
    name="users_list_valid",
    check=users_list_is_valid,
    message="GET /users must return valid JSON array",   # <- 'message', not 'description'
    severity=Severity.CRITICAL,
)
```

## Run an exploration

**CRITICAL**: VenomQA needs database rollback to explore branches.
Without it, VenomQA can only test ONE linear path.

```python
import os
from venomqa import Action, Invariant, Agent, World, DFS, Severity
from venomqa.adapters.http import HttpClient
from venomqa.adapters.postgres import PostgresAdapter  # or SQLiteAdapter
from actions.my_actions import create_user, get_user

# Connect to the SAME database your API writes to
api = HttpClient("http://localhost:8000")
db = PostgresAdapter(os.environ["DATABASE_URL"])

agent = Agent(
    world=World(api=api, systems={{"db": db}}),  # <- REQUIRED for state exploration
    actions=[
        Action(name="create_user", execute=create_user, expected_status=[201]),
        Action(name="get_user",    execute=get_user,    expected_status=[200],
               preconditions=["create_user"]),  # <- only run after create_user
    ],
    invariants=[...],
    strategy=DFS(),   # <- use DFS with PostgreSQL
    max_steps=200,
)
result = agent.explore()
```

**No database?** Use `state_from_context=["user_id", ...]` for limited context-based exploration.

## Using an AI assistant

See `llm-context.md` in this directory -- paste it into Claude, ChatGPT, or
Cursor so the AI knows the exact VenomQA API and won't give you wrong code.

Or regenerate it any time:
```bash
venomqa llm-docs -o llm-context.md
```

## How State Traversal Works

VenomQA explores your API by trying every possible sequence of actions,
using checkpoints to branch and rollback between paths:

```
                    [Initial State]
                          |
         +----------------+----------------+
         |                |                |
     create_user      list_items      delete_item
         |                |                |
    [Checkpoint]     [Checkpoint]    (no-op: nothing to delete)
         |                |
    +----+----+      +----+----+
    |         |      |         |
create_repo  login  create   list
    |         |     _item    _items
   ...       ...     |         |
                [Checkpoint]   ...
                    |
              +-----+-----+
              |           |
          delete_item  update_item
              |           |
             ...         ...
```

**Key concepts:**

1. **BFS (Breadth-First Search)**: Explores all 1-action sequences, then all
   2-action sequences, etc. Finds shallow bugs fast.

2. **Checkpoints**: Before branching, VenomQA saves the current state (database
   snapshot, context values, etc.)

3. **Rollback**: After exploring one branch, VenomQA rolls back to the checkpoint
   and tries the next action -- so each path starts from the same state.

4. **Invariants**: Checked after EVERY action. If any invariant returns False,
   VenomQA records a **violation** with the exact reproduction path.

**Example exploration:**
```
Step 1: create_user                     -> check invariants
Step 2: create_user -> create_repo      -> check invariants
Step 3: create_user -> login            -> check invariants
Step 4: create_user -> create_repo -> ... -> check invariants
```

## Understanding Violations

When a violation is found, VenomQA shows:

```
[CRITICAL] refund_cannot_exceed_payment
  Message: Refunded amount exceeds original payment. Billing bug!

  Reproduction Path:
    -> create_customer
    -> create_payment_intent
    -> confirm_payment
    -> create_refund            <- violation triggered here

  Request: POST http://localhost:8000/refunds
  Response: 200
  Body: {{"amount": 2000, ...}}
```

**Severity levels:**
- `CRITICAL`: Data corruption, security breach, money issues
- `HIGH`: Major feature broken
- `MEDIUM`: Partial functionality loss
- `LOW`: Minor issues

## Common mistakes

| Wrong | Correct |
|-------|---------|
| `def action(ctx, api)` | `def action(api, context)` |
| `context["key"] = val` | `context.set("key", val)` |
| `Invariant(description=...)` | `Invariant(message=...)` |
| `def check(state, ctx)` | `def check(world)` |
| `reporter.report(result, path=...)` | `open(f).write(reporter.report(result))` |
'''


SAMPLE_JOURNEY_PY = '''"""Sample VenomQA exploration (v1 API).

Demonstrates basic CRUD exploration -- VenomQA tries every sequence of
actions and checks the invariants after each step.

CRITICAL: VenomQA needs database rollback to explore state graphs.
Without it, VenomQA can only test ONE linear path. See options below.

Run with: python3 journeys/sample_journey.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so 'from actions...' imports work when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from venomqa import Action, Invariant, Agent, World, BFS, DFS, Severity
from venomqa.adapters.http import HttpClient

from actions.sample_actions import (
    health_check, list_items, create_item, get_item, delete_item
)


# --- Invariants: rules that must always hold -----------------------------------

def list_always_returns_array(world):
    """GET /api/items must always return a JSON array.

    GOOD PATTERN: Make a live API call to verify server state.
    Don't just check context - the server might be inconsistent.
    """
    resp = world.api.get("/api/items")
    if resp.status_code != 200:
        return False  # Invariant failed: API is broken
    data = resp.json()
    return isinstance(data, list)


def item_count_matches_server(world):
    """Context item_count must match actual server count.

    GOOD PATTERN: Cross-check client state against server state.
    This catches bugs where the client thinks something happened but it didn't.
    """
    expected = world.context.get("item_count")
    if expected is None:
        return True  # list_items hasn't run yet

    resp = world.api.get("/api/items")
    if resp.status_code != 200:
        return False
    actual = len(resp.json())
    return actual == expected


def deleted_item_not_retrievable(world):
    """After delete, the item should return 404.

    GOOD PATTERN: Test negative conditions, not just positive.
    """
    # Only check if we just deleted something
    if world.context.has("item_id"):
        return True  # Item still exists, nothing to check

    # If we had an item_id but it's now gone, verify server agrees
    deleted_id = world.context.get("_last_deleted_id")
    if deleted_id is None:
        return True

    resp = world.api.get(f"/api/items/{deleted_id}")
    return resp.status_code == 404


# --- Database setup ------------------------------------------------------------
#
# VenomQA explores state graphs by ROLLING BACK the database after each branch.
# You MUST connect to the SAME database your API uses.
#
# Choose ONE of these options:

def setup_with_postgres():
    """Option 1: PostgreSQL (most common for production APIs)"""
    from venomqa.adapters.postgres import PostgresAdapter

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: Set DATABASE_URL to your PostgreSQL connection string")
        print("  export DATABASE_URL='postgresql://user:pass@localhost:5432/yourdb'")
        sys.exit(1)

    api = HttpClient("http://localhost:8000")
    db = PostgresAdapter(db_url)

    # CRITICAL: use DFS() with PostgreSQL (BFS doesn't work with PG savepoints)
    return World(api=api, systems={"db": db}), DFS()


def setup_with_sqlite():
    """Option 2: SQLite (simpler, works with BFS)"""
    from venomqa.adapters.sqlite import SQLiteAdapter

    db_path = os.environ.get("SQLITE_PATH", "/path/to/your/api.db")

    api = HttpClient("http://localhost:8000")
    db = SQLiteAdapter(db_path)

    return World(api=api, systems={"db": db}), BFS()


def setup_with_context_only():
    """Option 3: No database - uses context for state identity.

    WARNING: This is a LIMITED mode for APIs that don't have a database.
    State exploration is based on context values only, not actual DB state.
    Use this only if your API is stateless or you're just testing the basics.
    """
    api = HttpClient("http://localhost:8000")

    # Track these context keys to distinguish states
    # Each unique combination = a different state
    return World(
        api=api,
        state_from_context=["item_id", "item_count"],  # context-based state
    ), BFS()


# --- Run exploration -----------------------------------------------------------

if __name__ == "__main__":
    # CHANGE THIS: Pick your setup based on your database
    # world, strategy = setup_with_postgres()
    # world, strategy = setup_with_sqlite()
    world, strategy = setup_with_context_only()  # Default: limited mode

    # Check if API is reachable before starting
    print("Checking API connectivity...")
    try:
        resp = world.api.get("/health")
        if resp.status_code >= 500:
            print()
            print("ERROR: API is not healthy")
            print(f"  GET /health returned {resp.status_code}")
            print()
            print("This sample expects a running API at http://localhost:8000")
            print()
            print("To customize for YOUR API:")
            print("  1. Edit actions/sample_actions.py - change endpoints")
            print("  2. Edit this file - update action list")
            print()
            sys.exit(1)
    except Exception as e:
        print()
        print("ERROR: Cannot connect to API at http://localhost:8000")
        print(f"  {e}")
        print()
        print("Either:")
        print("  1. Start your API: docker compose up")
        print("  2. Or customize actions/sample_actions.py for your API")
        print()
        sys.exit(1)

    print("API is reachable. Starting exploration...")
    print()

    agent = Agent(
        world=world,
        actions=[
            Action(name="health_check", execute=health_check, expected_status=[200]),
            Action(name="list_items",   execute=list_items,   expected_status=[200]),
            Action(name="create_item",  execute=create_item,  expected_status=[200, 201]),
            Action(
                name="get_item",
                execute=get_item,
                expected_status=[200],
                preconditions=["create_item"],  # Only run after create_item
            ),
            Action(
                name="delete_item",
                execute=delete_item,
                preconditions=["create_item"],  # Only run after create_item
            ),
        ],
        invariants=[
            Invariant(
                name="list_returns_array",
                check=list_always_returns_array,
                message="GET /api/items must return JSON array",
                severity=Severity.CRITICAL,
            ),
            Invariant(
                name="count_matches_server",
                check=item_count_matches_server,
                message="Client item_count must match server",
                severity=Severity.HIGH,
            ),
            Invariant(
                name="deleted_is_404",
                check=deleted_item_not_retrievable,
                message="Deleted items must return 404",
                severity=Severity.HIGH,
            ),
        ],
        strategy=strategy,
        max_steps=200,
        progress_every=20,  # Print progress every 20 steps
    )

    print("Starting exploration...")
    print(f"  Strategy: {type(strategy).__name__}")
    print(f"  Max steps: {agent.max_steps}")
    print()

    result = agent.explore()

    # --- Report results ---
    from venomqa.reporters import ConsoleReporter, HTMLTraceReporter

    # Console output (default)
    ConsoleReporter().report(result)

    # HTML trace (visual graph of exploration)
    html = HTMLTraceReporter().report(result)
    with open("exploration_trace.html", "w") as f:
        f.write(html)
    print()
    print("HTML trace saved to: exploration_trace.html")
    print("Open in browser to see the state graph visualization.")
            print(f"      {v.message}")
    else:
        print()
        print("All invariants passed.")

    # Exit with error if violations found (useful for CI)
    sys.exit(1 if result.violations else 0)
'''


# For backwards compatibility with old template name
VENVOMQA_YAML_TEMPLATE = VENOMQA_YAML_TEMPLATE
