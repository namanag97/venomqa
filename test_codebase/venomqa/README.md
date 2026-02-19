# VenomQA Test Suite

Autonomous API exploration -- define actions and invariants, let VenomQA find every bug sequence.

## Directory Structure

```
venomqa/
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
    resp = api.post("/users", json={"name": "Alice"})

    # GOOD: Validate before using response
    if resp.status_code != 201:
        raise AssertionError(f"Create failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    if "id" not in data:
        raise AssertionError(f"Missing 'id' in response: {data}")

    context.set("user_id", data["id"])   # <- .set(), not context["key"] =
    return resp

def get_user(api, context):
    user_id = context.get("user_id")     # <- .get(), not context["key"]
    resp = api.get(f"/users/{user_id}")

    if resp.status_code != 200:
        raise AssertionError(f"Get user failed: {resp.status_code}")
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
    resp = world.api.get(f"/users/{user_id}")
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
    world=World(api=api, systems={"db": db}),  # <- REQUIRED for state exploration
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
  Body: {"amount": 2000, ...}
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
