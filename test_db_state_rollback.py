#!/usr/bin/env python3
"""Test database state rollback with checkpoints.

This is a critical test - VenomQA claims to support database checkpoints
and rollback. This test verifies if that actually works.
"""

import sys
sys.path.insert(0, '.')

from venomqa import Client, Journey, Step, Checkpoint, Branch, Path
from venomqa.runner import JourneyRunner
from venomqa.state import MemoryStateManager

BASE_URL = "http://localhost:5001"


def test_db_state_rollback_without_state_manager():
    """Test what happens WITHOUT a state manager."""
    print("\n" + "="*60)
    print("TEST A: Branch paths WITHOUT state manager")
    print("="*60)
    print("Expected: Both paths modify the SAME database record")

    def create_todo(client, context):
        response = client.post("/todos", json={"title": "Original Title", "completed": False})
        context["todo_id"] = response.json().get("id")
        print(f"  [CREATE] Created todo {context['todo_id']}: 'Original Title', completed=False")
        return response

    def path_a_complete(client, context):
        todo_id = context.get("todo_id")
        response = client.put(f"/todos/{todo_id}", json={"completed": True})
        print(f"  [PATH A] Set todo {todo_id} completed=True")
        # Verify the state
        verify = client.get(f"/todos/{todo_id}")
        print(f"  [PATH A] Verify: completed={verify.json().get('completed')}")
        return response

    def path_b_check_state(client, context):
        todo_id = context.get("todo_id")
        response = client.get(f"/todos/{todo_id}")
        state = response.json()
        completed = state.get("completed")
        print(f"  [PATH B] Check state: completed={completed}")
        # If state was rolled back, completed should be False
        # If not rolled back, it will be True from Path A
        if completed:
            print("  [PATH B] State NOT rolled back - saw Path A's changes!")
        else:
            print("  [PATH B] State was rolled back - did not see Path A's changes")
        return response

    journey = Journey(
        name="no_state_manager_test",
        steps=[
            Step(name="create", action=create_todo),
            Checkpoint(name="after_create"),
            Branch(
                checkpoint_name="after_create",
                paths=[
                    Path(name="path_a", steps=[
                        Step(name="complete_todo", action=path_a_complete),
                    ]),
                    Path(name="path_b", steps=[
                        Step(name="check_state", action=path_b_check_state),
                    ]),
                ]
            ),
        ]
    )

    client = Client(base_url=BASE_URL)
    runner = JourneyRunner(client=client)  # NO state manager
    result = runner.run(journey)

    print(f"\n  Journey Result: {'PASSED' if result.success else 'FAILED'}")

    # Cleanup
    todo_id = None
    for rec in client.history:
        if rec.operation.startswith("POST") and rec.response_body:
            todo_id = rec.response_body.get("id")
    if todo_id:
        client.delete(f"/todos/{todo_id}")

    return result


def test_db_state_rollback_with_memory_manager():
    """Test with MemoryStateManager (not a real DB state manager)."""
    print("\n" + "="*60)
    print("TEST B: Branch paths WITH MemoryStateManager")
    print("="*60)
    print("Note: Memory state manager only manages in-memory context,")
    print("      NOT actual database state.")

    def create_todo(client, context):
        response = client.post("/todos", json={"title": "Memory Test", "completed": False})
        context["todo_id"] = response.json().get("id")
        print(f"  [CREATE] Created todo {context['todo_id']}")
        return response

    def path_a_modify(client, context):
        todo_id = context.get("todo_id")
        response = client.put(f"/todos/{todo_id}", json={"completed": True})
        print(f"  [PATH A] Modified todo {todo_id}")
        return response

    def path_b_verify(client, context):
        todo_id = context.get("todo_id")
        response = client.get(f"/todos/{todo_id}")
        completed = response.json().get("completed")
        print(f"  [PATH B] Todo {todo_id} completed={completed}")
        if completed:
            print("  [PATH B] DB state NOT rolled back (Memory manager doesn't do DB rollback)")
        return response

    journey = Journey(
        name="memory_state_test",
        steps=[
            Step(name="create", action=create_todo),
            Checkpoint(name="after_create"),
            Branch(
                checkpoint_name="after_create",
                paths=[
                    Path(name="path_a", steps=[
                        Step(name="modify", action=path_a_modify),
                    ]),
                    Path(name="path_b", steps=[
                        Step(name="verify", action=path_b_verify),
                    ]),
                ]
            ),
        ]
    )

    client = Client(base_url=BASE_URL)
    state_manager = MemoryStateManager("memory://test")
    runner = JourneyRunner(client=client, state_manager=state_manager)
    result = runner.run(journey)

    print(f"\n  Journey Result: {'PASSED' if result.success else 'FAILED'}")

    return result


def test_real_db_state_requirements():
    """Document what would be needed for real DB state rollback."""
    print("\n" + "="*60)
    print("ANALYSIS: Database State Rollback Requirements")
    print("="*60)

    print("""
For REAL database state rollback, VenomQA would need:

1. PostgreSQLStateManager connected to the SAME database
   as the Flask app (postgresql://todouser:todopass@localhost:5432/todos)

2. Both the test runner AND the Flask app must use the
   SAME database connection or transactions must be coordinated

3. PostgreSQL SAVEPOINT mechanism:
   - BEGIN transaction
   - SAVEPOINT checkpoint_name (at checkpoint)
   - ... run path ...
   - ROLLBACK TO SAVEPOINT checkpoint_name (after path)

Current status:
- The Todo app uses its OWN database connection
- VenomQA's state manager would use a SEPARATE connection
- SAVEPOINTS don't work across connections!

This means:
- TRUE database rollback requires the app to support it
- OR the test must control the app's transactions
- OR use Docker snapshots/volumes

Let's verify by checking if PostgreSQLStateManager is available...
    """)

    try:
        from venomqa.state import PostgreSQLStateManager
        print("PostgreSQLStateManager is available")

        # Try to connect to the todo app's database
        db_url = "postgresql://todouser:todopass@localhost:5432/todos"
        try:
            mgr = PostgreSQLStateManager(db_url)
            mgr.connect()
            print(f"Connected to database: {db_url}")
            print(f"Connection active: {mgr.is_connected()}")

            # Create a checkpoint
            mgr.checkpoint("test_checkpoint")
            print("Created checkpoint: test_checkpoint")

            # List checkpoints
            checkpoints = mgr.get_active_checkpoints()
            print(f"Active checkpoints: {checkpoints}")

            mgr.disconnect()
            print("Disconnected from database")

        except Exception as e:
            print(f"Could not connect to database: {e}")

    except ImportError as e:
        print(f"PostgreSQLStateManager not available: {e}")
        print("You may need: pip install 'venomqa[postgres]'")

    return True


def main():
    print("\n" + "#"*60)
    print("# Database State Rollback Investigation")
    print("#"*60)

    # Check app is running
    try:
        import requests
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"\nTodo app healthy: {response.json()}")
    except Exception as e:
        print(f"\nERROR: Cannot connect: {e}")
        return

    test_db_state_rollback_without_state_manager()
    test_db_state_rollback_with_memory_manager()
    test_real_db_state_requirements()

    print("\n" + "="*60)
    print("CONCLUSION")
    print("="*60)
    print("""
VenomQA's checkpoint/rollback behavior:

1. WITHOUT state_manager: Context snapshot is restored between paths,
   but DATABASE STATE IS NOT ROLLED BACK.

2. WITH MemoryStateManager: Same as above - only context is restored.

3. WITH PostgreSQLStateManager: Creates SAVEPOINTs in a separate
   connection, which CANNOT roll back changes made by the app's
   own connection.

For TRUE database state rollback, you would need:
- A test database that the test framework controls
- The app to run in a transaction-per-request mode
- OR: Docker volume snapshots between paths
- OR: Truncate and re-seed between paths

The current VenomQA implementation correctly handles:
- Context/variable state rollback between paths
- The CONCEPT of checkpoints for documentation

But does NOT provide:
- Automatic database state rollback in real-world scenarios
    """)


if __name__ == "__main__":
    main()
