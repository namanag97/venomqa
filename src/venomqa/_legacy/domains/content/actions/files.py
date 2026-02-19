"""File actions for content management.

Reusable file management actions.
"""

from venomqa.http import Client


class FileActions:
    def __init__(self, base_url: str, storage_url: str | None = None):
        self.client = Client(base_url=base_url)
        self.storage_client = Client(base_url=storage_url or base_url, timeout=300)

    def upload(
        self, file_content: bytes, filename: str, content_type: str, token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        files = {"file": (filename, file_content, content_type)}
        return self.storage_client.post("/api/files/upload", files=files, headers=headers)

    def get(self, file_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.get(f"/api/files/{file_id}", headers=headers)

    def download(self, file_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.get(f"/api/files/{file_id}/download", headers=headers)

    def delete(self, file_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.delete(f"/api/files/{file_id}", headers=headers)

    def list(self, page: int = 1, per_page: int = 20, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.get(
            "/api/files", params={"page": page, "per_page": per_page}, headers=headers
        )

    def copy(self, file_id: str, destination: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.post(
            f"/api/files/{file_id}/copy", json={"destination": destination}, headers=headers
        )

    def move(self, file_id: str, destination: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.storage_client.post(
            f"/api/files/{file_id}/move", json={"destination": destination}, headers=headers
        )


def upload_file(client, context):
    actions = FileActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url"),
    )
    response = actions.upload(
        file_content=context.get("file_content", b"Test content"),
        filename=context.get("filename", "test.txt"),
        content_type=context.get("content_type", "text/plain"),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        context["file_id"] = response.json().get("id")
    return response


def get_file(client, context):
    actions = FileActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url"),
    )
    return actions.get(file_id=context["file_id"], token=context.get("token"))


def download_file(client, context):
    actions = FileActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url"),
    )
    return actions.download(file_id=context["file_id"], token=context.get("token"))


def delete_file(client, context):
    actions = FileActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url"),
    )
    return actions.delete(file_id=context["file_id"], token=context.get("token"))


def list_files(client, context):
    actions = FileActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url"),
    )
    return actions.list(
        page=context.get("page", 1),
        per_page=context.get("per_page", 20),
        token=context.get("token"),
    )


def copy_file(client, context):
    actions = FileActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url"),
    )
    return actions.copy(
        file_id=context["file_id"],
        destination=context.get("destination", "/copies/"),
        token=context.get("token"),
    )


def move_file(client, context):
    actions = FileActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        storage_url=context.get("storage_url"),
    )
    return actions.move(
        file_id=context["file_id"],
        destination=context.get("destination", "/archived/"),
        token=context.get("token"),
    )
