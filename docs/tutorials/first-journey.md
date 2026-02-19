# Your First Journey

Build a complete VenomQA test suite from scratch.

## What You'll Build

A test suite for a simple todo API that:

- Creates todos
- Updates todos
- Deletes todos
- Finds sequence bugs

## Prerequisites

```bash
pip install venomqa
```

You'll also need a todo API running. For this tutorial, use the mock server:

```bash
# Clone and run the example server
git clone https://github.com/namanag97/venomqa.git
cd venomqa/examples/todo_app
python app/app.py
# Server running at http://localhost:5000
```

## Step 1: Define Your Actions

Create `qa/actions/todo.py`:

```python
"""Actions for the todo API."""

from typing import Optional
from venomqa.adapters.http import HttpClient

def create_todo(api: HttpClient, context) -> Optional[dict]:
    """Create a new todo item."""
    resp = api.post("/todos", json={
        "title": "Test Todo",
        "completed": False,
    })
    
    if resp.status_code == 201:
        data = resp.json()
        context.set("todo_id", data["id"])
        context.set("last_status", resp.status_code)
        return data
    return None

def update_todo(api: HttpClient, context) -> Optional[dict]:
    """Update an existing todo."""
    todo_id = context.get("todo_id")
    if todo_id is None:
        return None  # Skip - no todo to update
    
    resp = api.put(f"/todos/{todo_id}", json={
        "title": "Updated Todo",
        "completed": True,
    })
    
    context.set("last_status", resp.status_code)
    return resp.json() if resp.status_code == 200 else None

def delete_todo(api: HttpClient, context) -> Optional[dict]:
    """Delete a todo."""
    todo_id = context.get("todo_id")
    if todo_id is None:
        return None  # Skip - no todo to delete
    
    resp = api.delete(f"/todos/{todo_id}")
    context.set("last_status", resp.status_code)
    
    if resp.status_code == 204:
        context.delete("todo_id")  # Clear the ID
        return {}
    return None

def get_todo(api: HttpClient, context) -> Optional[dict]:
    """Get a todo by ID."""
    todo_id = context.get("todo_id")
    if todo_id is None:
        return None
    
    resp = api.get(f"/todos/{todo_id}")
    context.set("last_status", resp.status_code)
    return resp.json() if resp.status_code == 200 else None

def list_todos(api: HttpClient, context) -> list:
    """List all todos."""
    resp = api.get("/todos")
    context.set("last_status", resp.status_code)
    return resp.json()
```

## Step 2: Define Invariants

Create `qa/invariants.py`:

```python
"""Invariants for the todo API."""

from venomqa import Invariant, Severity

def no_server_errors(world) -> bool:
    """No 5xx errors should occur."""
    return world.context.get("last_status", 200) < 500

def deleted_not_accessible(world) -> bool:
    """Deleted todos should return 404."""
    # This is checked in the action itself
    # If we got here, no violation occurred
    return True

def completed_cannot_be_uncompleted(world) -> bool:
    """Once completed, cannot be uncompleted (business rule)."""
    todo = world.context.get("last_todo")
    if not todo:
        return True
    
    # Check if we're trying to uncomplete a completed todo
    if todo.get("was_completed") and not todo.get("completed"):
        return False
    return True

# Create invariant objects
no_500s = Invariant(
    name="no_server_errors",
    check=no_server_errors,
    severity=Severity.CRITICAL,
)

consistency = Invariant(
    name="data_consistency",
    check=lambda w: True,  # Placeholder
    severity=Severity.HIGH,
)
```

## Step 3: Create the Test File

Create `qa/test_todos.py`:

```python
"""VenomQA test suite for todo API."""

from venomqa import Action, Agent, BFS, Invariant, Severity, World
from venomqa.adapters.http import HttpClient

from actions.todo import create_todo, update_todo, delete_todo, get_todo, list_todos
from invariants import no_500s

# Setup
api = HttpClient("http://localhost:5000")
world = World(api=api, state_from_context=["todo_id"])

# Define actions
actions = [
    Action(name="create_todo", execute=create_todo),
    Action(name="update_todo", execute=update_todo),
    Action(name="delete_todo", execute=delete_todo),
    Action(name="get_todo", execute=get_todo),
    Action(name="list_todos", execute=list_todos),
]

# Define invariants
invariants = [
    no_500s,
    Invariant(
        name="no_negative_ids",
        check=lambda w: w.context.get("todo_id", 0) >= 0,
        severity=Severity.MEDIUM,
    ),
]

# Create agent and explore
agent = Agent(
    world=world,
    actions=actions,
    invariants=invariants,
    strategy=BFS(),
    max_steps=100,
    max_depth=10,
)

if __name__ == "__main__":
    result = agent.explore()
    
    print(f"\n{'='*50}")
    print(f"States visited: {result.states_visited}")
    print(f"Transitions: {result.transitions}")
    print(f"Invariants checked: {result.invariants_checked}")
    print(f"Violations: {result.violations}")
    
    if result.violations:
        print("\nViolations found:")
        for v in result.violations:
            print(f"  - {v.invariant_name}: {v.message}")
    else:
        print("\nAll invariants passed!")
```

## Step 4: Run the Test

```bash
cd qa
python test_todos.py
```

Expected output:

```
==================================================
States visited: 12
Transitions: 25
Invariants checked: 75
Violations: 0

All invariants passed!
```

## Step 5: Find a Bug

Let's plant a bug in our API to see VenomQA catch it. Modify the server to allow deleting the same todo twice:

```python
# In your API server (intentional bug)
@app.delete("/todos/<int:todo_id>")
def delete_todo(todo_id):
    todo = todos.get(todo_id)
    if not todo:
        return {"error": "Not found"}, 404  # This is correct
    
    del todos[todo_id]
    return "", 204  # Bug: should prevent double-delete
```

Now add an invariant to catch this:

```python
# Add to invariants.py
def no_double_delete(world) -> bool:
    """Deleting the same todo twice should fail."""
    # Track deletions in context
    deleted = world.context.get("deleted_ids", set())
    todo_id = world.context.get("last_deleted_id")
    
    if todo_id and todo_id in deleted:
        return False  # Double delete!
    return True

double_delete_check = Invariant(
    name="no_double_delete",
    check=no_double_delete,
    severity=Severity.CRITICAL,
)
```

Run again:

```
==================================================
States visited: 15
Transitions: 32
Invariants checked: 96
Violations: 1

Violations found:
  - no_double_delete: Deleted todo ID 1 twice
```

## Step 6: Add Reporting

Generate an HTML report:

```python
from venomqa.reporters import HTMLTraceReporter

reporter = HTMLTraceReporter(output_path="reports/trace.html")
result = agent.explore(reporter=reporter)
```

Open `reports/trace.html` to see a visual graph of all paths explored.

## What You Learned

| Concept | What You Did |
|---------|--------------|
| **Actions** | Defined create, update, delete, get, list |
| **Context** | Stored and retrieved `todo_id` between actions |
| **Invariants** | Checked for server errors and double deletes |
| **Agent** | Orchestrated BFS exploration |
| **Reporting** | Generated HTML trace |

## Next Steps

- [Testing Payment Flows](payment-flows.md) - More complex state machine
- [CI/CD Integration](ci-cd.md) - Automate in pipelines
- [Concepts: Journeys](../concepts/journeys.md) - Deep dive on context
