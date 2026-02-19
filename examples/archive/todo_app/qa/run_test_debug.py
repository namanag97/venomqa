#!/usr/bin/env python3
"""Run todo app journeys manually with debug output."""
import sys
import os

sys.path.insert(0, '/Users/namanagarwal/venomQA')
sys.path.insert(0, '/Users/namanagarwal/venomQA/examples/todo_app/qa')

from venomqa import Client, JourneyRunner
from venomqa import Journey, Step, Checkpoint

# Import actions directly
sys.path.insert(0, '/Users/namanagarwal/venomQA/examples/todo_app/qa/actions')
import todo_actions_debug as actions

# Define journey inline with debug actions
crud_journey = Journey(
    name="crud_operations",
    description="Complete CRUD operations journey for Todo API",
    steps=[
        Step(
            name="health_check",
            action=actions.health_check,
            description="Verify API is healthy",
        ),
        Step(
            name="create_todo",
            action=actions.create_todo,
            description="Create a new todo item",
        ),
        Checkpoint(name="todo_created"),
        Step(
            name="get_todo",
            action=actions.get_todo,
            description="Fetch the created todo",
        ),
        Step(
            name="list_todos",
            action=actions.list_todos,
            description="List all todos",
        ),
        Step(
            name="update_todo",
            action=lambda client, ctx: actions.update_todo(
                client, ctx, title="Completed Task", completed=True
            ),
            description="Update the todo title",
        ),
        Checkpoint(name="todo_updated"),
        Step(
            name="delete_todo",
            action=actions.delete_todo,
            description="Delete the todo",
        ),
        Step(
            name="verify_deleted",
            action=actions.get_todo,
            description="Verify todo no longer exists",
            expect_failure=True,
        ),
    ],
)

# Create client
client = Client(base_url="http://localhost:5001")

# Create runner
runner = JourneyRunner(client=client)

# Run the journey
print("Running CRUD Journey with Debug...")
print("=" * 60)
result = runner.run(crud_journey)

# Print results
print(f"\nJourney: {result.journey_name}")
print(f"Status: {'PASSED' if result.success else 'FAILED'}")
print(f"Steps: {result.passed_steps}/{result.total_steps} passed")
print(f"Duration: {result.duration_seconds:.2f}s")

sys.exit(0 if result.success else 1)
