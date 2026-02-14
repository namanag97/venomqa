"""File upload journeys for content management.

Demonstrates:
- Single and bulk uploads
- Image processing with resize
- Multi-port testing (api:8000, storage:8003)

This module provides journeys for testing file upload functionality including
single file uploads, bulk uploads, and image processing with transformations.
"""

from __future__ import annotations

from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.client import Client


class FileUploadActions:
    """Actions for file upload operations.

    Provides methods for uploading, retrieving, and managing files
    through the storage service API.

    Args:
        base_url: Base URL for the main API service.
        storage_url: Optional URL for the storage service. Defaults to base_url.
    """

    def __init__(self, base_url: str, storage_url: str | None = None) -> None:
        self.client = Client(base_url=base_url, timeout=300)
        self.storage_client = Client(base_url=storage_url or base_url, timeout=300)

    def upload_file(
        self, file_content: bytes, filename: str, content_type: str, token: str | None = None
    ) -> Any:
        """Upload a single file to the storage service.

        Args:
            file_content: Binary content of the file to upload.
            filename: Name of the file.
            content_type: MIME type of the file.
            token: Optional authentication token.

        Returns:
            Response object from the upload request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        files = {"file": (filename, file_content, content_type)}
        return self.storage_client.post("/api/files/upload", files=files, headers=headers)

    def upload_multiple(self, files_data: list, token: str | None = None) -> Any:
        """Upload multiple files in a single request.

        Args:
            files_data: List of file dictionaries with 'filename', 'content', and 'content_type'.
            token: Optional authentication token.

        Returns:
            Response object from the upload request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        files = [("files", (f["filename"], f["content"], f["content_type"])) for f in files_data]
        return self.storage_client.post("/api/files/upload-multiple", files=files, headers=headers)

    def get_file(self, file_id: str, token: str | None = None) -> Any:
        """Retrieve file metadata by ID.

        Args:
            file_id: Unique identifier of the file.
            token: Optional authentication token.

        Returns:
            Response object containing file metadata.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.get(f"/api/files/{file_id}", headers=headers)

    def download_file(self, file_id: str, token: str | None = None) -> Any:
        """Download file content by ID.

        Args:
            file_id: Unique identifier of the file.
            token: Optional authentication token.

        Returns:
            Response object containing file binary content.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.get(f"/api/files/{file_id}/download", headers=headers)

    def delete_file(self, file_id: str, token: str | None = None) -> Any:
        """Delete a file by ID.

        Args:
            file_id: Unique identifier of the file to delete.
            token: Optional authentication token.

        Returns:
            Response object from the delete request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.delete(f"/api/files/{file_id}", headers=headers)

    def process_image(self, file_id: str, operations: list, token: str | None = None) -> Any:
        """Apply image processing operations to a file.

        Args:
            file_id: Unique identifier of the image file.
            operations: List of image operations to apply (e.g., resize, thumbnail).
            token: Optional authentication token.

        Returns:
            Response object containing processing results.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.post(
            f"/api/files/{file_id}/process",
            json={"operations": operations},
            headers=headers,
        )

    def list_files(self, page: int = 1, per_page: int = 20, token: str | None = None) -> Any:
        """List files with pagination.

        Args:
            page: Page number for pagination.
            per_page: Number of files per page.
            token: Optional authentication token.

        Returns:
            Response object containing paginated file list.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.get(
            "/api/files", params={"page": page, "per_page": per_page}, headers=headers
        )


def login_user(client: Client, context: dict) -> Any:
    """Authenticate user and store token in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from login request.
    """
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "user@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def upload_single_file(client: Client, context: dict) -> Any:
    """Upload a single file and store file_id in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from upload request.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    content = context.get("file_content", b"Test file content for upload")
    response = actions.upload_file(
        file_content=content,
        filename=context.get("filename", "test.txt"),
        content_type=context.get("content_type", "text/plain"),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["file_id"] = data.get("id")
        assert data.get("size") == len(content), "File size should match content length"
    return response


def upload_multiple_files(client: Client, context: dict) -> Any:
    """Upload multiple files in bulk and store uploaded_ids in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from bulk upload request.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    files_data = [
        {"filename": "file1.txt", "content": b"Content 1", "content_type": "text/plain"},
        {"filename": "file2.txt", "content": b"Content 2", "content_type": "text/plain"},
        {"filename": "file3.txt", "content": b"Content 3", "content_type": "text/plain"},
    ]
    response = actions.upload_multiple(files_data=files_data, token=context.get("token"))
    if response.status_code in [200, 201]:
        data = response.json()
        context["uploaded_ids"] = [f.get("id") for f in data.get("files", [])]
        assert len(data.get("files", [])) == 3, "Should upload 3 files"
    return response


def get_file_metadata(client: Client, context: dict) -> Any:
    """Retrieve and verify file metadata.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing file_id.

    Returns:
        Response object with file metadata.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    response = actions.get_file(file_id=context["file_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("id") == context["file_id"], "File ID should match"
    return response


def download_file(client: Client, context: dict) -> Any:
    """Download file content by ID.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing file_id.

    Returns:
        Response object with file binary content.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    return actions.download_file(file_id=context["file_id"], token=context.get("token"))


def delete_file(client: Client, context: dict) -> Any:
    """Delete file by ID.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing file_id.

    Returns:
        Response object from delete request.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    return actions.delete_file(file_id=context["file_id"], token=context.get("token"))


def upload_image(client: Client, context: dict) -> Any:
    """Upload an image file for processing tests.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from upload request.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    content = context.get("image_content", b"FAKE_IMAGE_DATA")
    response = actions.upload_file(
        file_content=content,
        filename=context.get("image_filename", "test.jpg"),
        content_type="image/jpeg",
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["file_id"] = response.json().get("id")
    return response


def resize_image(client: Client, context: dict) -> Any:
    """Apply resize operation to uploaded image.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing file_id.

    Returns:
        Response object from processing request.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    response = actions.process_image(
        file_id=context["file_id"],
        operations=[{"type": "resize", "width": 800, "height": 600}],
        token=context.get("token"),
    )
    if response.status_code == 200:
        data = response.json()
        assert data.get("processed") is True, "Image should be processed"
    return response


def create_thumbnail(client: Client, context: dict) -> Any:
    """Generate thumbnail from uploaded image.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing file_id.

    Returns:
        Response object from thumbnail generation request.
    """
    actions = FileUploadActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url", "http://localhost:8003"),
    )
    response = actions.process_image(
        file_id=context["file_id"],
        operations=[{"type": "thumbnail", "size": 150}],
        token=context.get("token"),
    )
    if response.status_code == 200:
        context["thumbnail_id"] = response.json().get("thumbnail_id")
    return response


single_upload_flow = Journey(
    name="content_single_file_upload",
    description="Upload, verify, and delete a single file",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="upload_file", action=upload_single_file),
        Checkpoint(name="file_uploaded"),
        Step(name="get_metadata", action=get_file_metadata),
        Step(name="download_file", action=download_file),
        Step(name="delete_file", action=delete_file),
        Checkpoint(name="file_deleted"),
    ],
)

bulk_upload_flow = Journey(
    name="content_bulk_file_upload",
    description="Upload multiple files at once",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="upload_multiple", action=upload_multiple_files),
        Checkpoint(name="files_uploaded"),
        Step(name="delete_files", action=delete_file),
    ],
)

image_upload_with_resize_flow = Journey(
    name="content_image_upload_with_resize",
    description="Upload image and process with resize operations",
    steps=[
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="upload_image", action=upload_image),
        Checkpoint(name="image_uploaded"),
        Branch(
            checkpoint_name="image_uploaded",
            paths=[
                Path(
                    name="resize_path",
                    steps=[
                        Step(name="resize", action=resize_image),
                        Step(name="verify_resized", action=get_file_metadata),
                    ],
                ),
                Path(
                    name="thumbnail_path",
                    steps=[
                        Step(name="create_thumbnail", action=create_thumbnail),
                        Step(name="verify_thumbnail", action=get_file_metadata),
                    ],
                ),
            ],
        ),
    ],
)
