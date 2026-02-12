"""
VenomQA Actions for the Full-Featured App.

These actions demonstrate how to write reusable test actions
that can be composed into journeys.
"""

import json
from datetime import datetime
from typing import Any


def create_user(
    client,
    context,
    email: str | None = None,
    name: str = "Test User",
    password: str = "password123",
):
    """Create a new user via API."""
    user_email = email or f"test_{datetime.now().timestamp()}@example.com"
    response = client.post(
        "/api/users",
        json={"email": user_email, "name": name, "password": password},
    )
    if response.ok:
        data = response.json()
        context.set("user_id", data["id"])
        context.set("user_email", data["email"])
    return response


def get_user(client, context, user_id: int | None = None):
    """Get user by ID."""
    uid = user_id or context.get("user_id")
    return client.get(f"/api/users/{uid}")


def create_item(
    client,
    context,
    name: str | None = None,
    description: str = "Test item description",
    price: float = 99.99,
    quantity: int = 1,
):
    """Create a new item via API."""
    item_name = name or f"Test Item {datetime.now().timestamp()}"
    response = client.post(
        "/api/items",
        json={"name": item_name, "description": description, "price": price, "quantity": quantity},
    )
    if response.ok:
        data = response.json()
        context.set("item_id", data["id"])
        context.set("item_price", data["price"])
    return response


def get_item(client, context, item_id: int | None = None):
    """Get item by ID."""
    iid = item_id or context.get("item_id")
    return client.get(f"/api/items/{iid}")


def update_item(client, context, item_id: int | None = None, **updates):
    """Update an item."""
    iid = item_id or context.get("item_id")
    return client.patch(f"/api/items/{iid}", json=updates)


def delete_item(client, context, item_id: int | None = None):
    """Delete an item."""
    iid = item_id or context.get("item_id")
    return client.delete(f"/api/items/{iid}")


def list_items(client, context, skip: int = 0, limit: int = 100):
    """List all items."""
    return client.get("/api/items", params={"skip": skip, "limit": limit})


def create_order(
    client,
    context,
    user_id: int | None = None,
    item_ids: list[int] | None = None,
    address: str = "123 Test St",
):
    """Create an order."""
    uid = user_id or context.get("user_id")
    items = item_ids or [context.get("item_id")]
    response = client.post(
        "/api/orders",
        json={"user_id": uid, "item_ids": items, "shipping_address": address},
    )
    if response.ok:
        data = response.json()
        context.set("order_id", data["id"])
    return response


def get_order(client, context, order_id: int | None = None):
    """Get order by ID."""
    oid = order_id or context.get("order_id")
    return client.get(f"/api/orders/{oid}")


def get_order_status(client, context, order_id: int | None = None):
    """Get order status including background job status."""
    oid = order_id or context.get("order_id")
    return client.get(f"/api/orders/{oid}/status")


def upload_file(
    client,
    context,
    filename: str = "test.txt",
    content: bytes = b"test content",
    content_type: str = "text/plain",
):
    """Upload a file."""
    response = client.post(
        "/api/files/upload",
        files={"file": (filename, content, content_type)},
        data={"description": f"Test file uploaded at {datetime.now().isoformat()}"},
    )
    if response.ok:
        context.set("uploaded_filename", filename)
    return response


def download_file(client, context, filename: str | None = None):
    """Download a file."""
    fname = filename or context.get("uploaded_filename", "test.txt")
    return client.get(f"/api/files/download/{fname}")


def send_email(
    client, context, to: str | None = None, subject: str = "Test Email", body: str = "Test body"
):
    """Send an email via API."""
    recipient = to or context.get("user_email", "test@example.com")
    response = client.post(
        "/api/emails/send-sync",
        json={"to": recipient, "subject": subject, "body": body},
    )
    if response.ok:
        context.set("email_sent", True)
    return response


def search(client, context, query: str, limit: int = 10, offset: int = 0):
    """Search for documents."""
    return client.post(
        "/api/search",
        json={"query": query, "limit": limit, "offset": offset},
    )


def verify_user_in_db(db, context, user_id: int | None = None):
    """Verify user exists in database."""
    uid = user_id or context.get("user_id")
    result = db.query("SELECT * FROM users WHERE id = %s", (uid,))
    return result.first()


def verify_item_in_db(db, context, item_id: int | None = None):
    """Verify item exists in database."""
    iid = item_id or context.get("item_id")
    result = db.query("SELECT * FROM items WHERE id = %s", (iid,))
    return result.first()


def verify_order_in_db(db, context, order_id: int | None = None):
    """Verify order exists in database."""
    oid = order_id or context.get("order_id")
    result = db.query("SELECT * FROM orders WHERE id = %s", (oid,))
    return result.first()


def count_items_in_db(db, context):
    """Count total items in database."""
    result = db.query("SELECT COUNT(*) as count FROM items")
    return result.scalar()


def count_orders_in_db(db, context):
    """Count total orders in database."""
    result = db.query("SELECT COUNT(*) as count FROM orders")
    return result.scalar()


def wait_for_email(
    mail, context, to: str | None = None, subject: str | None = None, timeout: float = 30.0
):
    """Wait for an email to be received."""
    recipient = to or context.get("user_email")
    email = mail.wait_for_email(to=recipient, subject=subject, timeout=timeout)
    if email:
        context.set("received_email", email)
    return email


def get_all_emails(mail, context):
    """Get all received emails."""
    return mail.get_all_emails()


def clear_emails(mail, context):
    """Clear all emails."""
    mail.delete_all_emails()
    return {"cleared": True}


def connect_websocket(ws, context, url: str = "ws://localhost:8000/ws"):
    """Connect to WebSocket."""
    conn = ws.connect(url)
    context.set("ws_connection_id", conn.id)
    return conn


def send_websocket_message(ws, context, message: dict[str, Any]):
    """Send a JSON message via WebSocket."""
    conn_id = context.get("ws_connection_id")
    ws.send_json(conn_id, message)
    return {"sent": True}


def receive_websocket_message(ws, context, timeout: float = 10.0):
    """Receive a JSON message via WebSocket."""
    conn_id = context.get("ws_connection_id")
    return ws.wait_for_json(conn_id, timeout=timeout)


def disconnect_websocket(ws, context):
    """Disconnect WebSocket."""
    conn_id = context.get("ws_connection_id")
    ws.disconnect(conn_id)
    return {"disconnected": True}


def test_cache_set(cache, context, key: str, value: Any, ttl: int | None = None):
    """Set a value in cache."""
    full_key = f"test_{key}_{datetime.now().timestamp()}"
    cache.set(full_key, value, ttl=ttl)
    context.set("last_cache_key", full_key)
    return {"key": full_key, "set": True}


def test_cache_get(cache, context, key: str | None = None):
    """Get a value from cache."""
    k = key or context.get("last_cache_key")
    return cache.get(k)


def test_cache_delete(cache, context, key: str | None = None):
    """Delete a value from cache."""
    k = key or context.get("last_cache_key")
    cache.delete(k)
    return {"deleted": True}


def index_document(search, context, doc_id: str, content: str, index: str = "test_index"):
    """Index a document for search."""
    from venomqa import IndexedDocument

    doc = IndexedDocument(id=doc_id, content=content)
    result = search.index_document(index, doc, refresh=True)
    context.set("last_search_index", index)
    context.set("last_search_doc_id", doc_id)
    return {"indexed": result}


def search_documents(search, context, query: str, index: str = "test_index", limit: int = 10):
    """Search for documents."""
    results, total = search.search(index, query=query, limit=limit)
    return {"results": results, "total": total}


def enqueue_job(queue, context, task_name: str, args: tuple = (), kwargs: dict | None = None):
    """Enqueue a background job."""
    job_id = queue.enqueue(task_name, *args, queue="default", **(kwargs or {}))
    context.set("last_job_id", job_id)
    return {"job_id": job_id}


def get_job_status(queue, context, job_id: str | None = None):
    """Get status of a background job."""
    jid = job_id or context.get("last_job_id")
    job = queue.get_job(jid)
    if job:
        return {"status": job.status.value, "job": job}
    return {"status": "not_found"}


def wait_for_job(queue, context, job_id: str | None = None, timeout: float = 30.0):
    """Wait for a background job to complete."""
    jid = job_id or context.get("last_job_id")
    result = queue.get_job_result(jid, timeout=timeout)
    return result


def get_server_time(client, context):
    """Get server time."""
    return client.get("/api/time")


def get_cached_response(client, context):
    """Get a cached response."""
    return client.get("/api/cached")


def clear_cache_via_api(client, context):
    """Clear the application cache."""
    return client.delete("/api/cache/clear")


def trigger_rate_limit(client, context, times: int = 10):
    """Trigger rate limiting by making many requests."""
    responses = []
    for _ in range(times):
        resp = client.get("/api/rate-limited")
        responses.append(resp.status_code)

    rate_limited = 429 in responses
    context.set("was_rate_limited", rate_limited)
    return {"rate_limited": rate_limited, "responses": responses}


def generate_report(client, context, report_type: str = "sales"):
    """Trigger report generation."""
    response = client.get(f"/api/jobs/generate-report?report_type={report_type}")
    if response.ok:
        data = response.json()
        context.set("report_job_id", data.get("task_id"))
    return response


def get_report_status(client, context, job_id: str | None = None):
    """Get report generation status."""
    jid = job_id or context.get("report_job_id")
    return client.get(f"/api/jobs/{jid}")


def cleanup_user(db, context, user_id: int | None = None):
    """Delete a user from database."""
    uid = user_id or context.get("user_id")
    if uid:
        db.delete("users", "id = %s", (uid,))
    return {"cleaned": True}


def cleanup_item(db, context, item_id: int | None = None):
    """Delete an item from database."""
    iid = item_id or context.get("item_id")
    if iid:
        db.delete("items", "id = %s", (iid,))
    return {"cleaned": True}


def cleanup_order(db, context, order_id: int | None = None):
    """Delete an order from database."""
    oid = order_id or context.get("order_id")
    if oid:
        db.delete("orders", "id = %s", (oid,))
    return {"cleaned": True}


def cleanup_all(db, context):
    """Clean up all created test resources."""
    user_id = context.get("user_id")
    item_id = context.get("item_id")
    order_id = context.get("order_id")

    if order_id:
        try:
            db.delete("orders", "id = %s", (order_id,))
        except Exception:
            pass

    if item_id:
        try:
            db.delete("items", "id = %s", (item_id,))
        except Exception:
            pass

    if user_id:
        try:
            db.delete("users", "id = %s", (user_id,))
        except Exception:
            pass

    return {"cleaned": True}


def assert_response_ok(response, context):
    """Assert that a response was successful."""
    assert response.ok, f"Response not OK: {response.status_code} - {response.text}"
    return response


def assert_status_code(response, context, expected: int):
    """Assert response status code."""
    assert response.status_code == expected, f"Expected {expected}, got {response.status_code}"
    return response


def assert_json_contains(response, context, key: str, value: Any = None):
    """Assert JSON response contains a key (and optionally value)."""
    data = response.json()
    assert key in data, f"Key '{key}' not found in response"
    if value is not None:
        assert data[key] == value, f"Expected {value}, got {data[key]}"
    return data


def save_to_context(response, context, key: str, json_path: str | None = None):
    """Save response data to context."""
    data = response.json()
    if json_path:
        parts = json_path.split(".")
        for part in parts:
            data = data.get(part)
    context.set(key, data)
    return {key: data}
