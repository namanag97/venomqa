"""Comprehensive journey - tests all states and combined flows."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from venomqa import Journey, Step, Checkpoint, Branch, Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))
from todo_actions import (
    create_todo,
    get_todo,
    list_todos,
    update_todo,
    delete_todo,
    upload_attachment,
    download_attachment,
    delete_attachment,
    health_check,
)


# Combined journey that tests all API states with branching
comprehensive_journey = Journey(
    name="comprehensive_api_test",
    description="Full API test covering all endpoints with state branching",
    tags=["comprehensive", "smoke", "integration"],
    steps=[
        # Phase 1: Health and initial state
        Step(
            name="verify_api_health",
            action=health_check,
            description="Verify API is healthy before testing",
        ),
        Step(
            name="list_initial_todos",
            action=list_todos,
            description="List todos to establish initial state",
        ),

        # Phase 2: Create a todo
        Step(
            name="create_base_todo",
            action=lambda client, ctx: create_todo(
                client, ctx,
                title="Comprehensive Test Todo",
                description="Created for comprehensive testing"
            ),
            description="Create base todo for all subsequent tests",
        ),
        Checkpoint(name="todo_created"),

        Step(
            name="verify_todo_created",
            action=get_todo,
            description="Verify todo was created correctly",
        ),

        # Phase 3: Branch to test different update scenarios
        Branch(
            checkpoint_name="todo_created",
            paths=[
                # Path 1: Update title only
                Path(
                    name="update_title_flow",
                    description="Test updating only the title",
                    steps=[
                        Step(
                            name="update_title",
                            action=lambda client, ctx: update_todo(
                                client, ctx,
                                title="Updated Title Only"
                            ),
                        ),
                        Step(
                            name="verify_title_update",
                            action=get_todo,
                        ),
                    ],
                ),
                # Path 2: Update description only
                Path(
                    name="update_description_flow",
                    description="Test updating only the description",
                    steps=[
                        Step(
                            name="update_description",
                            action=lambda client, ctx: update_todo(
                                client, ctx,
                                description="Updated description only"
                            ),
                        ),
                        Step(
                            name="verify_description_update",
                            action=get_todo,
                        ),
                    ],
                ),
                # Path 3: Mark as completed
                Path(
                    name="mark_completed_flow",
                    description="Test marking todo as completed",
                    steps=[
                        Step(
                            name="mark_completed",
                            action=lambda client, ctx: update_todo(
                                client, ctx,
                                completed=True
                            ),
                        ),
                        Step(
                            name="verify_completed",
                            action=get_todo,
                        ),
                        Step(
                            name="filter_completed",
                            action=lambda client, ctx: list_todos(
                                client, ctx, completed=True
                            ),
                        ),
                    ],
                ),
                # Path 4: Full update
                Path(
                    name="full_update_flow",
                    description="Test updating all fields",
                    steps=[
                        Step(
                            name="full_update",
                            action=lambda client, ctx: update_todo(
                                client, ctx,
                                title="Fully Updated Todo",
                                description="All fields updated",
                                completed=True
                            ),
                        ),
                        Step(
                            name="verify_full_update",
                            action=get_todo,
                        ),
                    ],
                ),
            ],
        ),

        # Phase 4: File attachment tests (continues from after branching)
        Step(
            name="create_todo_for_files",
            action=lambda client, ctx: create_todo(
                client, ctx,
                title="File Attachment Test Todo"
            ),
            description="Create fresh todo for file tests",
        ),
        Checkpoint(name="ready_for_files"),

        Step(
            name="upload_text_attachment",
            action=lambda client, ctx: upload_attachment(
                client, ctx,
                filename="test_notes.txt",
                content=b"These are test notes for the comprehensive journey."
            ),
            description="Upload a text file attachment",
        ),
        Step(
            name="download_uploaded_file",
            action=download_attachment,
            description="Download the uploaded file",
        ),
        Step(
            name="upload_second_file",
            action=lambda client, ctx: upload_attachment(
                client, ctx,
                filename="data.json",
                content=b'{"test": "data", "comprehensive": true}'
            ),
            description="Upload a second file",
        ),
        Checkpoint(name="files_uploaded"),

        # Branch for file operations
        Branch(
            checkpoint_name="files_uploaded",
            paths=[
                # Path 1: Delete first attachment
                Path(
                    name="delete_attachment_flow",
                    steps=[
                        Step(
                            name="delete_attachment",
                            action=delete_attachment,
                        ),
                        Step(
                            name="verify_todo_after_delete",
                            action=get_todo,
                        ),
                    ],
                ),
                # Path 2: Keep attachments and verify
                Path(
                    name="keep_attachments_flow",
                    steps=[
                        Step(
                            name="verify_attachments",
                            action=get_todo,
                        ),
                        Step(
                            name="list_after_uploads",
                            action=list_todos,
                        ),
                    ],
                ),
            ],
        ),

        # Phase 5: Cleanup and final verification
        Step(
            name="final_list",
            action=list_todos,
            description="Final list of all todos",
        ),
    ],
)


# Search and filter journey
search_filter_journey = Journey(
    name="search_and_filter",
    description="Test search and filter functionality",
    tags=["search", "filter"],
    steps=[
        Step(
            name="create_todo_alpha",
            action=lambda client, ctx: create_todo(
                client, ctx,
                title="Alpha Task",
                description="First priority task"
            ),
        ),
        Step(
            name="create_todo_beta",
            action=lambda client, ctx: create_todo(
                client, ctx,
                title="Beta Task",
                description="Second priority task"
            ),
        ),
        Step(
            name="create_completed_todo",
            action=lambda client, ctx: create_todo(
                client, ctx,
                title="Completed Task",
                completed=True
            ),
        ),
        Checkpoint(name="todos_created"),
        Step(
            name="search_alpha",
            action=lambda client, ctx: list_todos(client, ctx, search="Alpha"),
            description="Search for 'Alpha' in todos",
        ),
        Step(
            name="filter_completed",
            action=lambda client, ctx: list_todos(client, ctx, completed=True),
            description="Filter completed todos",
        ),
        Step(
            name="filter_incomplete",
            action=lambda client, ctx: list_todos(client, ctx, completed=False),
            description="Filter incomplete todos",
        ),
        Step(
            name="search_priority",
            action=lambda client, ctx: list_todos(client, ctx, search="priority"),
            description="Search for 'priority' in description",
        ),
        Step(
            name="paginate_results",
            action=lambda client, ctx: list_todos(client, ctx, page=1, limit=2),
            description="Test pagination with limit",
        ),
    ],
)


# Lifecycle journey - full create to delete
lifecycle_journey = Journey(
    name="todo_lifecycle",
    description="Test complete todo lifecycle from creation to deletion",
    tags=["lifecycle", "crud"],
    steps=[
        Step(
            name="create_lifecycle_todo",
            action=lambda client, ctx: create_todo(
                client, ctx,
                title="Lifecycle Test",
                description="Testing full lifecycle"
            ),
        ),
        Step(name="read_created", action=get_todo),
        Step(
            name="update_in_progress",
            action=lambda client, ctx: update_todo(
                client, ctx,
                title="Lifecycle Test - In Progress",
                description="Now working on this"
            ),
        ),
        Step(name="read_in_progress", action=get_todo),
        Step(
            name="mark_done",
            action=lambda client, ctx: update_todo(
                client, ctx,
                completed=True
            ),
        ),
        Step(name="read_completed", action=get_todo),
        Step(name="delete_completed", action=delete_todo),
        Step(
            name="verify_deleted",
            action=get_todo,
            expect_failure=True,
        ),
    ],
)
