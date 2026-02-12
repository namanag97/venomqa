import base64
import hashlib
import os
from pathlib import Path
from typing import Optional
from venomqa import Journey, Step, Checkpoint
from venomqa.clients import HTTPClient


class FileUploadActions:
    def __init__(self, base_url: str):
        self.client = HTTPClient(base_url=base_url, timeout=300)

    def upload_single(
        self,
        file_path: str,
        field_name: str = "file",
        additional_data: Optional[dict] = None,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with open(file_path, "rb") as f:
            files = {field_name: (Path(file_path).name, f)}
            data = additional_data or {}
            return self.client.post(
                "/api/files/upload",
                files=files,
                data=data,
                headers=headers,
            )

    def upload_bytes(
        self,
        content: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        files = {"file": (filename, content, content_type)}
        return self.client.post("/api/files/upload", files=files, headers=headers)

    def upload_multiple(
        self,
        file_paths: list[str],
        field_name: str = "files",
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        files = []
        for path in file_paths:
            with open(path, "rb") as f:
                files.append((field_name, (Path(path).name, f.read())))

        return self.client.post("/api/files/upload-multiple", files=files, headers=headers)

    def upload_chunked(
        self,
        file_path: str,
        chunk_size: int = 1024 * 1024,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        file_size = os.path.getsize(file_path)
        file_hash = hashlib.md5()
        upload_id = None

        with open(file_path, "rb") as f:
            chunk_index = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                file_hash.update(chunk)

                response = self.client.post(
                    "/api/files/upload-chunk",
                    files={"chunk": (f"chunk_{chunk_index}", chunk)},
                    data={
                        "upload_id": upload_id or "",
                        "chunk_index": chunk_index,
                        "total_chunks": (file_size + chunk_size - 1) // chunk_size,
                        "filename": Path(file_path).name,
                    },
                    headers=headers,
                )

                if response.status_code == 200:
                    upload_id = response.json().get("upload_id")

                chunk_index += 1

        final_response = self.client.post(
            "/api/files/complete-upload",
            json={
                "upload_id": upload_id,
                "filename": Path(file_path).name,
                "md5_hash": file_hash.hexdigest(),
            },
            headers=headers,
        )
        return final_response

    def download_file(self, file_id: str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(f"/api/files/{file_id}/download", headers=headers)

    def get_file_metadata(self, file_id: str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.get(f"/api/files/{file_id}", headers=headers)

    def delete_file(self, file_id: str, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.client.delete(f"/api/files/{file_id}", headers=headers)

    def list_files(
        self,
        page: int = 1,
        per_page: int = 20,
        mime_type: Optional[str] = None,
        token: Optional[str] = None,
    ):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        params = {"page": page, "per_page": per_page}
        if mime_type:
            params["mime_type"] = mime_type
        return self.client.get("/api/files", params=params, headers=headers)


def login_for_upload(client, context):
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "test@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def create_test_file(client, context):
    test_dir = Path(context.get("test_dir", "/tmp/venomqa_test_files"))
    test_dir.mkdir(parents=True, exist_ok=True)

    content = b"This is test file content for VenomQA upload testing.\n" * 100
    file_path = test_dir / "test_upload.txt"
    file_path.write_bytes(content)

    context["test_file_path"] = str(file_path)
    context["test_file_content"] = content
    context["test_file_hash"] = hashlib.md5(content).hexdigest()
    return {"status": "created", "path": str(file_path)}


def upload_single_file(client, context):
    actions = FileUploadActions(context.get("base_url", "http://localhost:8000"))
    response = actions.upload_single(
        file_path=context["test_file_path"],
        additional_data={"description": "Test upload", "tags": "test,upload"},
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["uploaded_file_id"] = response.json().get("id")
    return response


def upload_bytes_file(client, context):
    actions = FileUploadActions(context.get("base_url", "http://localhost:8000"))
    response = actions.upload_bytes(
        content=context["test_file_content"],
        filename="bytes_upload.txt",
        content_type="text/plain",
        token=context.get("token"),
    )
    return response


def upload_multiple_files(client, context):
    actions = FileUploadActions(context.get("base_url", "http://localhost:8000"))

    test_dir = Path(context.get("test_dir", "/tmp/venomqa_test_files"))
    file_paths = []
    for i in range(3):
        file_path = test_dir / f"multi_upload_{i}.txt"
        file_path.write_bytes(f"Multi-upload test file {i}\n".encode() * 50)
        file_paths.append(str(file_path))

    context["multi_upload_paths"] = file_paths
    return actions.upload_multiple(file_paths=file_paths, token=context.get("token"))


def upload_large_file_chunked(client, context):
    actions = FileUploadActions(context.get("base_url", "http://localhost:8000"))

    test_dir = Path(context.get("test_dir", "/tmp/venomqa_test_files"))
    test_dir.mkdir(parents=True, exist_ok=True)

    large_file = test_dir / "large_file.bin"
    chunk_size = 1024 * 1024
    with open(large_file, "wb") as f:
        for _ in range(10):
            f.write(os.urandom(chunk_size))

    context["large_file_path"] = str(large_file)
    return actions.upload_chunked(
        file_path=str(large_file),
        chunk_size=chunk_size,
        token=context.get("token"),
    )


def download_uploaded_file(client, context):
    actions = FileUploadActions(context.get("base_url", "http://localhost:8000"))
    return actions.download_file(file_id=context["uploaded_file_id"], token=context.get("token"))


def get_file_info(client, context):
    actions = FileUploadActions(context.get("base_url", "http://localhost:8000"))
    return actions.get_file_metadata(
        file_id=context["uploaded_file_id"], token=context.get("token")
    )


def delete_uploaded_file(client, context):
    actions = FileUploadActions(context.get("base_url", "http://localhost:8000"))
    return actions.delete_file(file_id=context["uploaded_file_id"], token=context.get("token"))


def cleanup_test_files(client, context):
    test_dir = Path(context.get("test_dir", "/tmp/venomqa_test_files"))
    if test_dir.exists():
        for file_path in test_dir.iterdir():
            file_path.unlink()
        test_dir.rmdir()
    return {"status": "cleaned"}


single_file_upload_flow = Journey(
    name="single_file_upload",
    description="Upload a single file and verify",
    steps=[
        Step(name="login", action=login_for_upload),
        Checkpoint(name="authenticated"),
        Step(name="create_test_file", action=create_test_file),
        Step(name="upload_file", action=upload_single_file),
        Checkpoint(name="file_uploaded"),
        Step(name="get_metadata", action=get_file_info),
        Step(name="download_file", action=download_uploaded_file),
        Step(name="delete_file", action=delete_uploaded_file),
        Step(name="cleanup", action=cleanup_test_files),
    ],
)


multiple_file_upload_flow = Journey(
    name="multiple_file_upload",
    description="Upload multiple files at once",
    steps=[
        Step(name="login", action=login_for_upload),
        Checkpoint(name="authenticated"),
        Step(name="upload_multiple", action=upload_multiple_files),
        Step(name="cleanup", action=cleanup_test_files),
    ],
)


chunked_upload_flow = Journey(
    name="chunked_file_upload",
    description="Upload large file in chunks",
    steps=[
        Step(name="login", action=login_for_upload),
        Checkpoint(name="authenticated"),
        Step(name="upload_chunked", action=upload_large_file_chunked),
        Step(name="cleanup", action=cleanup_test_files),
    ],
)


file_upload_lifecycle_flow = Journey(
    name="file_upload_lifecycle",
    description="Complete file upload lifecycle",
    steps=[
        Step(name="login", action=login_for_upload),
        Checkpoint(name="authenticated"),
        Step(name="create_test_file", action=create_test_file),
        Step(name="upload", action=upload_single_file),
        Checkpoint(name="uploaded"),
        Step(name="verify_metadata", action=get_file_info),
        Step(name="download_verify", action=download_uploaded_file),
        Step(name="delete", action=delete_uploaded_file),
        Checkpoint(name="deleted"),
        Step(name="cleanup_temp_files", action=cleanup_test_files),
    ],
)
