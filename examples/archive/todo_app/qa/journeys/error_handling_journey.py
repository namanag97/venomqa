"""Error handling journey - test API error responses."""

from venomqa import Journey, Step

from ..actions import get_todo, update_todo, delete_todo, create_todo, upload_attachment

error_handling_journey = Journey(
    name="error_handling",
    description="Test API error responses for invalid requests",
    steps=[
        Step(
            name="get_nonexistent_todo",
            action=lambda client, ctx: client.get("/todos/99999"),
            description="Request a non-existent todo",
            expect_failure=True,
        ),
        Step(
            name="update_nonexistent_todo",
            action=lambda client, ctx: client.put("/todos/99999", json={"title": "Updated"}),
            description="Update a non-existent todo",
            expect_failure=True,
        ),
        Step(
            name="delete_nonexistent_todo",
            action=lambda client, ctx: client.delete("/todos/99999"),
            description="Delete a non-existent todo",
            expect_failure=True,
        ),
        Step(
            name="create_todo_missing_title",
            action=lambda client, ctx: client.post("/todos", json={"description": "No title"}),
            description="Create todo without required title",
            expect_failure=True,
        ),
        Step(
            name="create_todo_empty_title",
            action=lambda client, ctx: client.post("/todos", json={"title": ""}),
            description="Create todo with empty title",
            expect_failure=True,
        ),
        Step(
            name="create_todo_long_title",
            action=lambda client, ctx: client.post("/todos", json={"title": "x" * 201}),
            description="Create todo with title exceeding max length",
            expect_failure=True,
        ),
    ],
)

validation_errors_journey = Journey(
    name="validation_errors",
    description="Test validation error responses",
    steps=[
        Step(
            name="invalid_json_body",
            action=lambda client, ctx: client.post(
                "/todos",
                content="not valid json",
                headers={"Content-Type": "application/json"},
            ),
            description="Send invalid JSON body",
            expect_failure=True,
        ),
        Step(
            name="missing_content_type",
            action=lambda client, ctx: client.post("/todos", content=b"some data"),
            description="POST without content type",
            expect_failure=True,
        ),
        Step(
            name="upload_to_nonexistent_todo",
            action=lambda client, ctx: client.post(
                "/todos/99999/attachments",
                files={"file": ("test.txt", b"content", "text/plain")},
            ),
            description="Upload file to non-existent todo",
            expect_failure=True,
        ),
        Step(
            name="create_todo_for_upload_test",
            action=create_todo,
            description="Create a todo for upload validation test",
        ),
        Step(
            name="upload_without_file",
            action=lambda client, ctx: client.post(f"/todos/{ctx.get('todo_id')}/attachments"),
            description="Upload request without file",
            expect_failure=True,
        ),
    ],
)

def create_multiple_todos(client, context):
    """Create multiple todos for pagination testing."""
    for i in range(5):
        create_todo(client, context, title=f"Todo {i}")
    return client.get("/todos")  # Return list to verify creation


pagination_journey = Journey(
    name="pagination_tests",
    description="Test pagination parameters",
    steps=[
        Step(
            name="create_multiple_todos",
            action=create_multiple_todos,
            description="Create multiple todos for pagination",
        ),
        Step(
            name="list_page_one",
            action=lambda client, ctx: client.get("/todos", params={"page": 1, "limit": 2}),
            description="Get first page",
        ),
        Step(
            name="list_page_two",
            action=lambda client, ctx: client.get("/todos", params={"page": 2, "limit": 2}),
            description="Get second page",
        ),
        Step(
            name="list_large_page",
            action=lambda client, ctx: client.get("/todos", params={"page": 100, "limit": 2}),
            description="Request page beyond available data",
        ),
    ],
)
