"""Todo actions - reusable API interactions for VenomQA tests."""


def create_todo(client, context, title=None, description=None, completed=None):
    title = title or context.get("todo_title", "Test Todo")
    data = {"title": title}
    if description is not None:
        data["description"] = description
    if completed is not None:
        data["completed"] = completed
    response = client.post("/todos", json=data)
    # Store the todo_id in context for future steps
    if response.status_code in [200, 201]:
        todo_id = response.json().get("id")
        context["todo_id"] = todo_id
    return response


def get_todo(client, context, todo_id=None):
    todo_id = todo_id or context.get("todo_id")
    return client.get(f"/todos/{todo_id}")


def list_todos(client, context, page=1, limit=10, completed=None, search=None):
    params = {"page": page, "limit": limit}
    if completed is not None:
        params["completed"] = str(completed).lower()
    if search:
        params["search"] = search
    return client.get("/todos", params=params)


def update_todo(client, context, todo_id=None, title=None, description=None, completed=None):
    todo_id = todo_id or context.get("todo_id")
    data = {}
    if title is not None:
        data["title"] = title
    if description is not None:
        data["description"] = description
    if completed is not None:
        data["completed"] = completed
    return client.put(f"/todos/{todo_id}", json=data)


def delete_todo(client, context, todo_id=None):
    todo_id = todo_id or context.get("todo_id")
    return client.delete(f"/todos/{todo_id}")


def upload_attachment(client, context, todo_id=None, filename="test.txt", content=b"test content"):
    todo_id = todo_id or context.get("todo_id")
    files = {"file": (filename, content, "text/plain")}
    response = client.post(f"/todos/{todo_id}/attachments", files=files)
    # Store attachment_id in context
    if response.status_code in [200, 201]:
        attachment_id = response.json().get("id")
        context["attachment_id"] = attachment_id
        # Also store in a list for multiple uploads
        if "attachment_ids" not in context:
            context["attachment_ids"] = []
        context["attachment_ids"].append(attachment_id)
    return response


def download_attachment(client, context, todo_id=None, file_id=None):
    todo_id = todo_id or context.get("todo_id")
    file_id = file_id or context.get("attachment_id")
    return client.get(f"/todos/{todo_id}/attachments/{file_id}")


def delete_attachment(client, context, todo_id=None, file_id=None):
    todo_id = todo_id or context.get("todo_id")
    file_id = file_id or context.get("attachment_id")
    return client.delete(f"/todos/{todo_id}/attachments/{file_id}")


def health_check(client, context):
    return client.get("/health")
