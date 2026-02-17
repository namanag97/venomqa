# VenomQA Test Suite

Autonomous API exploration — define actions and invariants, let VenomQA find every bug sequence.

## Directory Structure

```
qa/
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

1. **Edit `venomqa.yaml`** — set `base_url` to your API
2. **Write actions** in `actions/` — signature: `def my_action(api, context)`
3. **Run an exploration**:
   ```bash
   python3 journeys/sample_journey.py
   ```

## Actions (v1 API)

```python
# actions/my_actions.py

def create_user(api, context):
    resp = api.post("/users", json={"name": "Alice"})
    context.set("user_id", resp.json()["id"])   # ← .set(), not context["key"] =
    return resp

def get_user(api, context):
    user_id = context.get("user_id")            # ← .get(), not context["key"]
    return api.get(f"/users/{user_id}")
```

## Invariants

```python
from venomqa.v1 import Invariant, Severity

def user_id_is_set(world):          # receives World, not (state, ctx)
    return world.context.has("user_id")

Invariant(
    name="user_id_set",
    check=user_id_is_set,
    message="user_id must exist after login",   # ← 'message', not 'description'
    severity=Severity.CRITICAL,
)
```

## Run an exploration

```python
from venomqa.v1 import Action, Invariant, Agent, World, BFS, Severity
from venomqa.v1.adapters.http import HttpClient
from actions.my_actions import create_user, get_user

agent = Agent(
    world=World(api=HttpClient("http://localhost:8000")),
    actions=[
        Action(name="create_user", execute=create_user, expected_status=[201]),
        Action(name="get_user",    execute=get_user,    expected_status=[200]),
    ],
    invariants=[...],
    strategy=BFS(),
    max_steps=200,
)
result = agent.explore()
```

## Using an AI assistant

See `llm-context.md` in this directory — paste it into Claude, ChatGPT, or
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
   and tries the next action — so each path starts from the same state.

4. **Invariants**: Checked after EVERY action. If any invariant returns False,
   VenomQA records a **violation** with the exact reproduction path.

**Example exploration:**
```
Step 1: create_user                     → check invariants
Step 2: create_user → create_repo       → check invariants
Step 3: create_user → login             → check invariants
Step 4: create_user → create_repo → ... → check invariants
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
    -> create_refund            ← violation triggered here

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
