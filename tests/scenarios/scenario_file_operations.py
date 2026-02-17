"""File Operations Scenario - Tests upload, storage, and cleanup.

This scenario verifies VenomQA's ability to:
- Upload various file types
- Verify file storage and retrieval
- Test file cleanup operations
- Handle large files and edge cases

Requires: todo_app or full_featured_app with file upload support
"""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from venomqa import Branch, Checkpoint, Journey, Step
from venomqa import Path as JourneyPath
from venomqa.core.context import ExecutionContext
from venomqa.files import (
    FileHandler,
)

# =============================================================================
# File Generation Helpers
# =============================================================================


def generate_test_file(
    file_type: str, size_kb: int = 10, name: str | None = None
) -> tuple[bytes, str, str]:
    """Generate a test file of specified type and size.

    Returns:
        Tuple of (content_bytes, filename, content_type)
    """
    timestamp = int(time.time())

    if file_type == "text":
        content = ("Test content. " * 100)[:size_kb * 1024]
        return content.encode(), name or f"test_{timestamp}.txt", "text/plain"

    elif file_type == "json":
        data = {
            "test_id": timestamp,
            "data": ["item"] * (size_kb * 10),
            "nested": {"values": list(range(size_kb))},
        }
        import json

        content = json.dumps(data, indent=2)
        return content.encode(), name or f"data_{timestamp}.json", "application/json"

    elif file_type == "csv":
        rows = ["id,name,value"]
        for i in range(size_kb * 50):
            rows.append(f"{i},item_{i},{i * 1.5}")
        content = "\n".join(rows)
        return content.encode(), name or f"data_{timestamp}.csv", "text/csv"

    elif file_type == "binary":
        content = os.urandom(size_kb * 1024)
        return content, name or f"binary_{timestamp}.bin", "application/octet-stream"

    elif file_type == "image":
        # Create minimal PNG
        png_header = bytes(
            [
                0x89,
                0x50,
                0x4E,
                0x47,
                0x0D,
                0x0A,
                0x1A,
                0x0A,
            ]
        )
        content = png_header + os.urandom(max(0, size_kb * 1024 - len(png_header)))
        return content, name or f"image_{timestamp}.png", "image/png"

    else:
        content = b"Default content" * (size_kb * 64)
        return content, name or f"file_{timestamp}.dat", "application/octet-stream"


# =============================================================================
# Setup Actions
# =============================================================================


def setup_file_test(client: Any, context: ExecutionContext) -> Any:
    """Initialize file operation test state."""
    # Create temp directory for test files
    temp_dir = Path(tempfile.mkdtemp(prefix="venomqa_file_test_"))
    context["temp_dir"] = str(temp_dir)

    # Initialize file handler
    handler = FileHandler(
        temp_dir=temp_dir,
        chunk_size=8192,
    )
    context["file_handler"] = handler

    # Track uploaded files for cleanup
    context["uploaded_files"] = []
    context["uploaded_file_ids"] = []
    context["file_hashes"] = {}
    context["test_start_time"] = time.time()

    return {
        "status": "initialized",
        "temp_dir": str(temp_dir),
    }


def create_todo_for_attachments(client: Any, context: ExecutionContext) -> Any:
    """Create a todo item to attach files to."""
    response = client.post(
        "/todos",
        json={
            "title": "File test todo",
            "description": "Todo for testing file attachments",
        },
    )

    if response.status_code in [200, 201]:
        context["todo_id"] = response.json().get("id")

    return response


# =============================================================================
# File Upload Actions
# =============================================================================


def upload_text_file(client: Any, context: ExecutionContext) -> Any:
    """Upload a text file."""
    content, filename, content_type = generate_test_file("text", size_kb=5)

    # Calculate hash for verification
    file_hash = hashlib.sha256(content).hexdigest()
    context["file_hashes"][filename] = file_hash

    todo_id = context.get("todo_id")
    if not todo_id:
        return {"status": "error", "message": "No todo for attachment"}

    # Use multipart upload
    files = {"file": (filename, io.BytesIO(content), content_type)}

    response = client.post(
        f"/todos/{todo_id}/attachments",
        files=files,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        file_id = data.get("id") or data.get("file_id")
        context["uploaded_files"].append(
            {
                "filename": filename,
                "file_id": file_id,
                "size": len(content),
                "hash": file_hash,
                "type": "text",
            }
        )
        context["uploaded_file_ids"].append(file_id)
        context["last_uploaded_file_id"] = file_id

    return response


def upload_json_file(client: Any, context: ExecutionContext) -> Any:
    """Upload a JSON file."""
    content, filename, content_type = generate_test_file("json", size_kb=10)

    file_hash = hashlib.sha256(content).hexdigest()
    context["file_hashes"][filename] = file_hash

    todo_id = context.get("todo_id")
    if not todo_id:
        return {"status": "error", "message": "No todo"}

    files = {"file": (filename, io.BytesIO(content), content_type)}

    response = client.post(
        f"/todos/{todo_id}/attachments",
        files=files,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        file_id = data.get("id") or data.get("file_id")
        context["uploaded_files"].append(
            {
                "filename": filename,
                "file_id": file_id,
                "size": len(content),
                "hash": file_hash,
                "type": "json",
            }
        )
        context["uploaded_file_ids"].append(file_id)

    return response


def upload_csv_file(client: Any, context: ExecutionContext) -> Any:
    """Upload a CSV file."""
    content, filename, content_type = generate_test_file("csv", size_kb=20)

    file_hash = hashlib.sha256(content).hexdigest()
    context["file_hashes"][filename] = file_hash

    todo_id = context.get("todo_id")
    if not todo_id:
        return {"status": "error", "message": "No todo"}

    files = {"file": (filename, io.BytesIO(content), content_type)}

    response = client.post(
        f"/todos/{todo_id}/attachments",
        files=files,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        file_id = data.get("id") or data.get("file_id")
        context["uploaded_files"].append(
            {
                "filename": filename,
                "file_id": file_id,
                "size": len(content),
                "hash": file_hash,
                "type": "csv",
            }
        )
        context["uploaded_file_ids"].append(file_id)

    return response


def upload_binary_file(client: Any, context: ExecutionContext) -> Any:
    """Upload a binary file."""
    content, filename, content_type = generate_test_file("binary", size_kb=50)

    file_hash = hashlib.sha256(content).hexdigest()
    context["file_hashes"][filename] = file_hash

    todo_id = context.get("todo_id")
    if not todo_id:
        return {"status": "error", "message": "No todo"}

    files = {"file": (filename, io.BytesIO(content), content_type)}

    response = client.post(
        f"/todos/{todo_id}/attachments",
        files=files,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        file_id = data.get("id") or data.get("file_id")
        context["uploaded_files"].append(
            {
                "filename": filename,
                "file_id": file_id,
                "size": len(content),
                "hash": file_hash,
                "type": "binary",
            }
        )
        context["uploaded_file_ids"].append(file_id)

    return response


def upload_image_file(client: Any, context: ExecutionContext) -> Any:
    """Upload an image file."""
    content, filename, content_type = generate_test_file("image", size_kb=100)

    file_hash = hashlib.sha256(content).hexdigest()
    context["file_hashes"][filename] = file_hash

    todo_id = context.get("todo_id")
    if not todo_id:
        return {"status": "error", "message": "No todo"}

    files = {"file": (filename, io.BytesIO(content), content_type)}

    response = client.post(
        f"/todos/{todo_id}/attachments",
        files=files,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        file_id = data.get("id") or data.get("file_id")
        context["uploaded_files"].append(
            {
                "filename": filename,
                "file_id": file_id,
                "size": len(content),
                "hash": file_hash,
                "type": "image",
            }
        )
        context["uploaded_file_ids"].append(file_id)

    return response


def upload_large_file(client: Any, context: ExecutionContext) -> Any:
    """Upload a large file (1MB+)."""
    content, filename, content_type = generate_test_file("binary", size_kb=1024)

    file_hash = hashlib.sha256(content).hexdigest()
    context["file_hashes"][filename] = file_hash
    context["large_file_size"] = len(content)

    todo_id = context.get("todo_id")
    if not todo_id:
        return {"status": "error", "message": "No todo"}

    files = {"file": (filename, io.BytesIO(content), content_type)}

    response = client.post(
        f"/todos/{todo_id}/attachments",
        files=files,
        timeout=120.0,  # Longer timeout for large file
    )

    if response.status_code in [200, 201]:
        data = response.json()
        file_id = data.get("id") or data.get("file_id")
        context["uploaded_files"].append(
            {
                "filename": filename,
                "file_id": file_id,
                "size": len(content),
                "hash": file_hash,
                "type": "large",
            }
        )
        context["uploaded_file_ids"].append(file_id)
        context["large_file_id"] = file_id

    return response


# =============================================================================
# File Download/Verification Actions
# =============================================================================


def download_and_verify_file(client: Any, context: ExecutionContext) -> Any:
    """Download a file and verify its hash."""
    file_id = context.get("last_uploaded_file_id")
    if not file_id:
        return {"status": "skip", "message": "No file to download"}

    # Find the file info
    uploaded_files = context.get("uploaded_files", [])
    file_info = None
    for f in uploaded_files:
        if f.get("file_id") == file_id:
            file_info = f
            break

    if not file_info:
        return {"status": "error", "message": "File info not found"}

    todo_id = context.get("todo_id")
    response = client.get(f"/todos/{todo_id}/attachments/{file_id}")

    if response.status_code == 200:
        content = response.content
        downloaded_hash = hashlib.sha256(content).hexdigest()
        expected_hash = file_info.get("hash")

        hash_match = downloaded_hash == expected_hash

        assert hash_match, (
            f"Hash mismatch: expected {expected_hash}, got {downloaded_hash}"
        )

        return {
            "status": "verified",
            "hash_match": hash_match,
            "size": len(content),
        }

    return response


def verify_all_uploaded_files(client: Any, context: ExecutionContext) -> Any:
    """Verify all uploaded files can be retrieved."""
    todo_id = context.get("todo_id")
    uploaded_files = context.get("uploaded_files", [])

    verification_results = []

    for file_info in uploaded_files:
        file_id = file_info.get("file_id")

        response = client.get(f"/todos/{todo_id}/attachments/{file_id}")

        result = {
            "filename": file_info.get("filename"),
            "file_id": file_id,
            "exists": response.status_code == 200,
        }

        if response.status_code == 200:
            downloaded_hash = hashlib.sha256(response.content).hexdigest()
            result["hash_match"] = downloaded_hash == file_info.get("hash")
            result["size_match"] = len(response.content) == file_info.get("size")

        verification_results.append(result)

    context["verification_results"] = verification_results

    # Assert all files verified
    all_exist = all(r["exists"] for r in verification_results)
    all_hash_match = all(r.get("hash_match", False) for r in verification_results)

    assert all_exist, "Not all files exist"
    assert all_hash_match, "Not all file hashes match"

    return {
        "status": "all_verified",
        "files_checked": len(verification_results),
        "all_exist": all_exist,
        "all_hash_match": all_hash_match,
    }


def list_todo_attachments(client: Any, context: ExecutionContext) -> Any:
    """List all attachments for the todo."""
    todo_id = context.get("todo_id")

    response = client.get(f"/todos/{todo_id}/attachments")

    if response.status_code == 200:
        attachments = response.json()
        context["listed_attachments"] = attachments

        # Verify count matches uploaded count
        expected_count = len(context.get("uploaded_files", []))
        actual_count = len(attachments) if isinstance(attachments, list) else 0

        assert actual_count == expected_count, (
            f"Attachment count mismatch: expected {expected_count}, got {actual_count}"
        )

    return response


# =============================================================================
# File Deletion/Cleanup Actions
# =============================================================================


def delete_single_file(client: Any, context: ExecutionContext) -> Any:
    """Delete a single uploaded file."""
    uploaded_files = context.get("uploaded_files", [])

    if not uploaded_files:
        return {"status": "skip", "message": "No files to delete"}

    # Delete the first file
    file_to_delete = uploaded_files[0]
    file_id = file_to_delete.get("file_id")
    todo_id = context.get("todo_id")

    response = client.delete(f"/todos/{todo_id}/attachments/{file_id}")

    if response.status_code in [200, 204]:
        context["deleted_files"] = context.get("deleted_files", [])
        context["deleted_files"].append(file_id)

        # Remove from uploaded list
        context["uploaded_files"] = [
            f for f in uploaded_files if f.get("file_id") != file_id
        ]

    return response


def verify_file_deleted(client: Any, context: ExecutionContext) -> Any:
    """Verify deleted file is no longer accessible."""
    deleted_files = context.get("deleted_files", [])

    if not deleted_files:
        return {"status": "skip", "message": "No deleted files to verify"}

    todo_id = context.get("todo_id")
    verification_results = []

    for file_id in deleted_files:
        response = client.get(f"/todos/{todo_id}/attachments/{file_id}")

        # Should return 404
        is_deleted = response.status_code == 404

        verification_results.append(
            {
                "file_id": file_id,
                "is_deleted": is_deleted,
                "status_code": response.status_code,
            }
        )

    all_deleted = all(r["is_deleted"] for r in verification_results)

    assert all_deleted, "Not all deleted files returned 404"

    return {
        "status": "deletion_verified",
        "files_verified": len(verification_results),
        "all_deleted": all_deleted,
    }


def cleanup_all_files(client: Any, context: ExecutionContext) -> Any:
    """Clean up all remaining uploaded files."""
    uploaded_files = context.get("uploaded_files", [])
    todo_id = context.get("todo_id")

    deleted_count = 0
    failed_count = 0

    for file_info in uploaded_files:
        file_id = file_info.get("file_id")
        response = client.delete(f"/todos/{todo_id}/attachments/{file_id}")

        if response.status_code in [200, 204]:
            deleted_count += 1
        else:
            failed_count += 1

    context["uploaded_files"] = []

    return {
        "status": "cleanup_complete",
        "deleted": deleted_count,
        "failed": failed_count,
    }


def cleanup_temp_directory(client: Any, context: ExecutionContext) -> Any:
    """Clean up temporary test directory."""
    temp_dir = context.get("temp_dir")

    if temp_dir:
        import shutil

        try:
            shutil.rmtree(temp_dir)
            context["temp_dir"] = None
            return {"status": "temp_cleaned", "path": temp_dir}
        except Exception as e:
            return {"status": "cleanup_failed", "error": str(e)}

    return {"status": "no_temp_dir"}


def cleanup_todo(client: Any, context: ExecutionContext) -> Any:
    """Delete the test todo."""
    todo_id = context.get("todo_id")

    if todo_id:
        response = client.delete(f"/todos/{todo_id}")
        return response

    return {"status": "no_todo_to_delete"}


# =============================================================================
# Report Generation
# =============================================================================


def generate_file_report(client: Any, context: ExecutionContext) -> Any:
    """Generate file operations report."""
    elapsed_time = time.time() - context.get("test_start_time", 0)

    # Calculate total bytes uploaded
    uploaded_files = context.get("uploaded_files", [])
    total_bytes = sum(f.get("size", 0) for f in uploaded_files)

    report = {
        "summary": {
            "elapsed_seconds": elapsed_time,
            "files_uploaded": len(context.get("uploaded_file_ids", [])),
            "files_deleted": len(context.get("deleted_files", [])),
            "total_bytes_uploaded": total_bytes,
            "verification_passed": all(
                r.get("hash_match", False)
                for r in context.get("verification_results", [])
            ),
        },
        "uploaded_files": uploaded_files,
        "verification_results": context.get("verification_results", []),
    }

    context["file_report"] = report
    return report


# =============================================================================
# Journey Definitions
# =============================================================================

file_operations_journey = Journey(
    name="file_operations_scenario",
    description="Tests file upload, storage, verification, and cleanup",
    tags=["stress-test", "files", "upload"],
    timeout=300.0,
    steps=[
        Step(
            name="setup",
            action=setup_file_test,
            description="Initialize file test",
        ),
        Step(
            name="create_todo",
            action=create_todo_for_attachments,
            description="Create todo for attachments",
        ),
        Checkpoint(name="ready"),
        # Upload various file types
        Step(
            name="upload_text",
            action=upload_text_file,
            description="Upload text file",
        ),
        Step(
            name="upload_json",
            action=upload_json_file,
            description="Upload JSON file",
        ),
        Step(
            name="upload_csv",
            action=upload_csv_file,
            description="Upload CSV file",
        ),
        Step(
            name="upload_binary",
            action=upload_binary_file,
            description="Upload binary file",
        ),
        Step(
            name="upload_image",
            action=upload_image_file,
            description="Upload image file",
        ),
        Checkpoint(name="files_uploaded"),
        # Verify uploads
        Step(
            name="download_verify",
            action=download_and_verify_file,
            description="Download and verify file hash",
        ),
        Step(
            name="verify_all",
            action=verify_all_uploaded_files,
            description="Verify all uploaded files",
        ),
        Step(
            name="list_attachments",
            action=list_todo_attachments,
            description="List todo attachments",
        ),
        Checkpoint(name="verified"),
        # Deletion testing
        Step(
            name="delete_single",
            action=delete_single_file,
            description="Delete single file",
        ),
        Step(
            name="verify_deleted",
            action=verify_file_deleted,
            description="Verify file deleted",
        ),
        Checkpoint(name="deletion_tested"),
        # Cleanup
        Step(
            name="cleanup_files",
            action=cleanup_all_files,
            description="Clean up remaining files",
        ),
        Step(
            name="cleanup_temp",
            action=cleanup_temp_directory,
            description="Clean up temp directory",
        ),
        Step(
            name="cleanup_todo",
            action=cleanup_todo,
            description="Delete test todo",
        ),
        Step(
            name="generate_report",
            action=generate_file_report,
            description="Generate file operations report",
        ),
    ],
)

file_cleanup_journey = Journey(
    name="file_cleanup_scenario",
    description="Tests file cleanup and large file handling",
    tags=["stress-test", "files", "cleanup"],
    timeout=300.0,
    steps=[
        Step(name="setup", action=setup_file_test),
        Step(name="create_todo", action=create_todo_for_attachments),
        Checkpoint(name="ready"),
        # Upload large file
        Step(
            name="upload_large",
            action=upload_large_file,
            description="Upload 1MB+ file",
            timeout=120.0,
        ),
        # Upload multiple small files
        Step(name="upload_text_1", action=upload_text_file),
        Step(name="upload_text_2", action=upload_text_file),
        Step(name="upload_text_3", action=upload_text_file),
        Checkpoint(name="uploaded"),
        # Verify all
        Step(name="verify_all", action=verify_all_uploaded_files),
        Checkpoint(name="verified"),
        Branch(
            checkpoint_name="verified",
            paths=[
                JourneyPath(
                    name="cleanup_path",
                    steps=[
                        Step(name="cleanup_files", action=cleanup_all_files),
                        Step(name="verify_empty", action=list_todo_attachments),
                    ],
                ),
            ],
        ),
        Step(name="cleanup_temp", action=cleanup_temp_directory),
        Step(name="cleanup_todo", action=cleanup_todo),
        Step(name="report", action=generate_file_report),
    ],
)
