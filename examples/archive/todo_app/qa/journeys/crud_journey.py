"""CRUD journey - test full Create, Read, Update, Delete cycle."""

from venomqa import Journey, Step, Checkpoint, Branch, Path

from ..actions import create_todo, get_todo, list_todos, update_todo, delete_todo, health_check

crud_journey = Journey(
    name="crud_operations",
    description="Complete CRUD operations journey for Todo API",
    steps=[
        Step(
            name="health_check",
            action=health_check,
            description="Verify API is healthy",
        ),
        Step(
            name="create_todo",
            action=create_todo,
            description="Create a new todo item",
        ),
        Checkpoint(name="todo_created"),
        Step(
            name="get_todo",
            action=get_todo,
            description="Fetch the created todo",
        ),
        Step(
            name="list_todos",
            action=list_todos,
            description="List all todos",
        ),
        Step(
            name="update_todo",
            action=lambda client, ctx: update_todo(
                client, ctx, title="Updated Todo Title", description="Updated description"
            ),
            description="Update the todo title",
        ),
        Checkpoint(name="todo_updated"),
        Step(
            name="delete_todo",
            action=delete_todo,
            description="Delete the todo",
        ),
        Step(
            name="verify_deleted",
            action=get_todo,
            description="Verify todo no longer exists",
            expect_failure=True,
        ),
    ],
)

crud_with_branches_journey = Journey(
    name="crud_with_branches",
    description="CRUD operations with branching paths",
    steps=[
        Step(
            name="create_todo",
            action=create_todo,
            description="Create initial todo",
        ),
        Checkpoint(name="initial_state"),
        Step(
            name="update_to_completed",
            action=lambda client, ctx: update_todo(
                client, ctx, title="Completed Task", completed=True
            ),
            description="Mark todo as completed",
        ),
        Checkpoint(name="completed_state"),
        Branch(
            checkpoint_name="completed_state",
            paths=[
                Path(
                    name="mark_incomplete_again",
                    steps=[
                        Step(
                            name="update_incomplete",
                            action=lambda client, ctx: update_todo(client, ctx, completed=False),
                        ),
                    ],
                ),
                Path(
                    name="delete_completed",
                    steps=[
                        Step(
                            name="delete_todo",
                            action=delete_todo,
                        ),
                    ],
                ),
            ],
        ),
    ],
)
