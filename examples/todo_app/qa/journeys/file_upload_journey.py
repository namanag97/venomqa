"""File upload journey - test file attachment operations."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from venomqa import Journey, Step, Checkpoint

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))
from todo_actions import (
    create_todo,
    upload_attachment,
    download_attachment,
    delete_attachment,
    delete_todo,
)

file_upload_journey = Journey(
    name="file_upload_operations",
    description="Test file upload, download, and deletion for todo attachments",
    steps=[
        Step(
            name="create_todo_for_attachment",
            action=create_todo,
            description="Create todo to attach files to",
        ),
        Checkpoint(name="todo_ready"),
        Step(
            name="upload_text_file",
            action=lambda client, ctx: upload_attachment(
                client, ctx, filename="notes.txt", content=b"Important notes for this todo"
            ),
            description="Upload a text file attachment",
        ),
        Checkpoint(name="file_uploaded"),
        Step(
            name="download_attachment",
            action=download_attachment,
            description="Download the uploaded file",
        ),
        Step(
            name="upload_image_file",
            action=lambda client, ctx: upload_attachment(
                client, ctx, filename="screenshot.png", content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            ),
            description="Upload an image file",
        ),
        Step(
            name="delete_first_attachment",
            action=delete_attachment,
            description="Delete the first attachment",
        ),
        Step(
            name="cleanup_todo",
            action=delete_todo,
            description="Delete the todo",
        ),
    ],
)

multiple_uploads_journey = Journey(
    name="multiple_file_uploads",
    description="Test uploading multiple files to a single todo",
    steps=[
        Step(
            name="create_todo",
            action=create_todo,
            description="Create todo for multiple attachments",
        ),
        Checkpoint(name="todo_created"),
        Step(
            name="upload_file_1",
            action=lambda client, ctx: upload_attachment(
                client, ctx, filename="doc1.pdf", content=b"PDF content 1"
            ),
            description="Upload first document",
        ),
        Step(
            name="upload_file_2",
            action=lambda client, ctx: upload_attachment(
                client, ctx, filename="doc2.pdf", content=b"PDF content 2"
            ),
            description="Upload second document",
        ),
        Step(
            name="upload_file_3",
            action=lambda client, ctx: upload_attachment(
                client, ctx, filename="image.jpg", content=b"JPEG content"
            ),
            description="Upload third document",
        ),
        Checkpoint(name="files_uploaded"),
        Step(
            name="verify_attachments",
            action=lambda client, ctx: client.get(f"/todos/{ctx.get('todo_id')}"),
            description="Verify all attachments are listed",
        ),
        Step(
            name="cleanup",
            action=delete_todo,
            description="Clean up todo",
        ),
    ],
)
