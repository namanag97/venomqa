"""Todo actions - reusable API interactions for VenomQA tests."""


def create_todo(client, context, title=None, description=None, completed=None):
    title = title or context.get("todo_title", "Test Todo")
    data = {"title": title}
    if description is not None:
        data["description"] = description
    if completed is not None:
        data["completed"] = completed
    print(f"[create_todo] Sending: {data}")
    response = client.post("/todos", json=data)
    print(f"[create_todo] Response: {response.status_code} - {response.json()}")
    # Store the todo_id in context for future steps
    if response.status_code == 201 or response.status_code == 200:
        todo_id = response.json().get("id")
        context["todo_id"] = todo_id
        print(f"[create_todo] Stored todo_id: {todo_id}")
    return response


def update_todo(client, context, todo_id=None, title=None, description=None, completed=None):
    todo_id = todo_id or context.get("todo_id")
    print(f"[update_todo] todo_id={todo_id}, title={title}, description={description}, completed={completed}")
    data = {}
    if title is not None:
        data["title"] = title
    if description is not None:
        data["description"] = description
    if completed is not None:
        data["completed"] = completed
    print(f"[update_todo] Sending PUT to /todos/{todo_id} with data: {data}")
    response = client.put(f"/todos/{todo_id}", json=data)
    print(f"[update_todo] Response: {response.status_code}")
    try:
        print(f"[update_todo] Body: {response.json()}")
    except:
        print(f"[update_todo] Body: {response.text[:200]}")
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


def delete_todo(client, context, todo_id=None):
    todo_id = todo_id or context.get("todo_id")
    return client.delete(f"/todos/{todo_id}")


def health_check(client, context):
    return client.get("/health")
