"""
Complete Journey demonstrating ALL VenomQA Ports.

This journey showcases:
1. ClientPort - HTTP API calls
2. DatabasePort - Direct database queries
3. StatePort - State branching and exploration
4. FilePort - File uploads/downloads
5. MailPort - Email testing via Mailhog
6. QueuePort - Background job testing
7. CachePort - Redis cache testing
8. SearchPort - Elasticsearch testing
9. WebSocketPort - Real-time communication
10. TimePort - Temporal testing
"""

from datetime import datetime

from venomqa import (
    Branch,
    Checkpoint,
    Journey,
    Path,
    Step,
)


def create_user_via_api(client, context):
    """Create a user via API (ClientPort)."""
    response = client.post(
        "/api/users",
        json={
            "email": f"test_{datetime.now().timestamp()}@example.com",
            "name": "Test User",
            "password": "securepassword123",
        },
    )
    assert response.ok, f"Failed to create user: {response.text}"
    data = response.json()
    context.set("user_id", data["id"])
    context.set("user_email", data["email"])
    return response


def create_item_via_api(client, context):
    """Create an item via API (ClientPort)."""
    response = client.post(
        "/api/items",
        json={
            "name": f"Test Item {datetime.now().timestamp()}",
            "description": "A test item for VenomQA",
            "price": 99.99,
            "quantity": 10,
        },
    )
    assert response.ok, f"Failed to create item: {response.text}"
    data = response.json()
    context.set("item_id", data["id"])
    context.set("item_price", data["price"])
    return response


def verify_item_in_database(db, context):
    """Verify item exists in database (DatabasePort)."""
    item_id = context.get("item_id")
    result = db.query("SELECT * FROM items WHERE id = %s", (item_id,))
    assert result.row_count == 1, "Item not found in database"
    item = result.first()
    assert item["name"].startswith("Test Item"), "Item name mismatch"
    return result


def update_item_via_api(client, context):
    """Update an item via API (ClientPort)."""
    item_id = context.get("item_id")
    response = client.patch(
        f"/api/items/{item_id}",
        json={"price": 149.99, "description": "Updated description"},
    )
    assert response.ok, f"Failed to update item: {response.text}"
    return response


def upload_file(client, context):
    """Upload a file (FilePort via multipart)."""
    file_content = b"This is test file content for VenomQA"
    response = client.post(
        "/api/files/upload",
        files={"file": ("test_document.txt", file_content, "text/plain")},
        data={"description": "Test file upload"},
    )
    assert response.ok, f"Failed to upload file: {response.text}"
    context.set("uploaded_filename", response.json()["file"]["filename"])
    return response


def download_file(client, context):
    """Download a file (FilePort)."""
    filename = context.get("uploaded_filename", "test_document.txt")
    response = client.get(f"/api/files/download/{filename}")
    assert response.ok, f"Failed to download file: {response.status_code}"
    assert len(response.body) > 0, "Empty file content"
    return response


def send_email_via_api(client, context):
    """Trigger email sending via API."""
    user_email = context.get("user_email", "test@example.com")
    response = client.post(
        "/api/emails/send-sync",
        json={
            "to": user_email,
            "subject": "Test Email from VenomQA",
            "body": "This is a test email sent via VenomQA testing.",
            "html_body": "<h1>Test Email</h1><p>Sent via VenomQA</p>",
        },
    )
    assert response.ok, f"Failed to send email: {response.text}"
    context.set("email_sent", True)
    return response


def verify_email_received(mail, context):
    """Verify email was received (MailPort)."""
    user_email = context.get("user_email", "test@example.com")
    email = mail.wait_for_email(to=user_email, subject="Test Email", timeout=30)
    assert email is not None, "Email not received"
    assert "VenomQA" in email.body, "Email content incorrect"
    context.set("received_email", email)
    return email


def create_order(client, context):
    """Create an order with background job."""
    user_id = context.get("user_id")
    item_id = context.get("item_id")
    response = client.post(
        "/api/orders",
        json={
            "user_id": user_id,
            "item_ids": [item_id],
            "shipping_address": "123 Test Street, Test City",
        },
    )
    assert response.ok, f"Failed to create order: {response.text}"
    data = response.json()
    context.set("order_id", data["id"])
    return response


def verify_background_job(queue, context):
    """Verify background job was created and completed (QueuePort)."""
    order_id = context.get("order_id")

    client = context.get_client()
    import time

    time.sleep(2)

    response = client.get(f"/api/orders/{order_id}/status")
    data = response.json()

    if data.get("task_status"):
        task_id = data["task_status"]["task_id"]
        job = queue.get_job(task_id)
        if job:
            context.set("job_id", task_id)
            context.set("job_status", job.status.value)

    return data


def test_rate_limiting(client, context):
    """Test rate limiting (ClientPort with rate limit)."""
    responses = []
    for i in range(7):
        response = client.get("/api/rate-limited")
        responses.append(response.status_code)

    rate_limited = any(code == 429 for code in responses)
    context.set("rate_limit_triggered", rate_limited)
    return {"rate_limited": rate_limited, "responses": responses}


def test_caching(cache, context):
    """Test cache operations (CachePort)."""
    test_key = f"test_key_{datetime.now().timestamp()}"
    test_value = {"name": "test", "timestamp": datetime.now().isoformat()}

    cache.set(test_key, test_value, ttl=60)
    context.set("cache_key", test_key)

    retrieved = cache.get(test_key)
    assert retrieved == test_value, "Cache value mismatch"

    exists = cache.exists(test_key)
    assert exists, "Cache key should exist"

    ttl = cache.get_ttl(test_key)
    assert ttl is not None and ttl > 0, "TTL should be positive"

    cache.delete(test_key)
    assert not cache.exists(test_key), "Key should be deleted"

    return {"cached": True, "key": test_key}


def test_search_indexing(search, context):
    """Test search operations (SearchPort)."""
    from venomqa import IndexedDocument

    doc = IndexedDocument(
        id=f"test_doc_{datetime.now().timestamp()}",
        content="VenomQA test document for search testing",
        title="Test Document",
        fields={"category": "test", "priority": "high"},
    )

    indexed = search.index_document("test_index", doc, refresh=True)
    assert indexed, "Document should be indexed"
    context.set("search_doc_id", doc.id)

    results, total = search.search(
        "test_index",
        query="VenomQA",
        limit=10,
    )
    assert total >= 1, "Should find at least one result"

    search.delete_document("test_index", doc.id)

    return {"indexed": indexed, "found": total}


def connect_websocket(ws, context):
    """Connect to WebSocket endpoint (WebSocketPort)."""
    conn = ws.connect("ws://localhost:8000/ws")
    context.set("ws_connection_id", conn.id)
    return conn


def send_websocket_message(ws, context):
    """Send and receive WebSocket message."""
    conn_id = context.get("ws_connection_id")

    ws.send_json(conn_id, {"type": "ping", "data": "test"})

    response = ws.wait_for_json(conn_id, timeout=10)
    assert response is not None, "No WebSocket response"
    assert response.get("type") == "pong", "Expected pong response"

    return response


def disconnect_websocket(ws, context):
    """Disconnect WebSocket."""
    conn_id = context.get("ws_connection_id")
    ws.disconnect(conn_id)
    return {"disconnected": True}


def test_time_operations(time, context):
    """Test time operations (TimePort)."""
    now = time.now()
    utc_now = time.now_utc()

    scheduled_id = time.schedule_after(
        delay_seconds=1.0,
        callback=lambda: print("Scheduled task executed"),
        name="test_task",
    )
    context.set("scheduled_task_id", scheduled_id)

    time.cancel_schedule(scheduled_id)

    formatted = time.format(now, "%Y-%m-%d %H:%M:%S")

    return {
        "now": now.isoformat(),
        "utc_now": utc_now.isoformat(),
        "formatted": formatted,
    }


def cleanup_created_resources(client, db, context):
    """Clean up all created resources."""
    item_id = context.get("item_id")
    user_id = context.get("user_id")
    order_id = context.get("order_id")

    if order_id:
        try:
            client.delete(f"/api/orders/{order_id}")
        except Exception:
            pass

    if item_id:
        try:
            client.delete(f"/api/items/{item_id}")
        except Exception:
            pass

    if user_id:
        try:
            db.delete("users", "id = %s", (user_id,))
        except Exception:
            pass

    return {"cleaned": True}


complete_journey = Journey(
    name="complete_feature_journey",
    description="Comprehensive journey testing ALL VenomQA ports and features",
    tags=["comprehensive", "all-ports", "integration"],
    steps=[
        Step(name="create_user", action=create_user_via_api, description="Create user via API"),
        Checkpoint(name="user_created"),
        Step(name="create_item", action=create_item_via_api, description="Create item via API"),
        Checkpoint(name="item_created"),
        Step(
            name="verify_item_db", action=verify_item_in_database, description="Verify item in DB"
        ),
        Step(name="update_item", action=update_item_via_api, description="Update item via API"),
        Checkpoint(name="item_updated"),
        Step(name="upload_file", action=upload_file, description="Upload test file"),
        Step(name="download_file", action=download_file, description="Download test file"),
        Checkpoint(name="file_ops_complete"),
        Step(name="send_email", action=send_email_via_api, description="Send test email"),
        Step(
            name="verify_email", action=verify_email_received, description="Verify email received"
        ),
        Checkpoint(name="email_verified"),
        Step(
            name="create_order", action=create_order, description="Create order with background job"
        ),
        Step(name="verify_job", action=verify_background_job, description="Verify background job"),
        Checkpoint(name="order_complete"),
        Step(name="test_rate_limit", action=test_rate_limiting, description="Test rate limiting"),
        Checkpoint(name="rate_limit_tested"),
        Step(name="test_cache", action=test_caching, description="Test cache operations"),
        Step(name="test_search", action=test_search_indexing, description="Test search operations"),
        Checkpoint(name="cache_search_tested"),
        Step(name="connect_ws", action=connect_websocket, description="Connect WebSocket"),
        Step(name="ws_message", action=send_websocket_message, description="Send WS message"),
        Step(name="disconnect_ws", action=disconnect_websocket, description="Disconnect WebSocket"),
        Checkpoint(name="websocket_tested"),
        Step(name="test_time", action=test_time_operations, description="Test time operations"),
        Checkpoint(name="all_features_tested"),
        Branch(
            checkpoint_name="all_features_tested",
            paths=[
                Path(
                    name="cleanup_path",
                    description="Cleanup all created resources",
                    steps=[
                        Step(
                            name="cleanup",
                            action=cleanup_created_resources,
                            description="Cleanup resources",
                        ),
                    ],
                ),
                Path(
                    name="verify_state_path",
                    description="Verify final state before cleanup",
                    steps=[
                        Step(
                            name="verify_final_state",
                            action=verify_item_in_database,
                            description="Verify final DB state",
                        ),
                        Step(
                            name="cleanup_after_verify",
                            action=cleanup_created_resources,
                            description="Cleanup after verify",
                        ),
                    ],
                ),
            ],
        ),
    ],
)


crud_only_journey = Journey(
    name="crud_operations",
    description="Basic CRUD operations journey",
    tags=["crud", "basic"],
    steps=[
        Step(name="create_item", action=create_item_via_api, description="Create item"),
        Checkpoint(name="item_created"),
        Step(name="update_item", action=update_item_via_api, description="Update item"),
        Checkpoint(name="item_updated"),
        Branch(
            checkpoint_name="item_updated",
            paths=[
                Path(
                    name="delete_path",
                    steps=[
                        Step(
                            name="delete_item",
                            action=lambda client, ctx: client.delete(
                                f"/api/items/{ctx.get('item_id')}"
                            ),
                            description="Delete item",
                        ),
                    ],
                ),
            ],
        ),
    ],
)


websocket_journey = Journey(
    name="websocket_testing",
    description="WebSocket connection and messaging journey",
    tags=["websocket", "realtime"],
    steps=[
        Step(name="connect", action=connect_websocket, description="Connect to WebSocket"),
        Checkpoint(name="connected"),
        Step(name="ping_pong", action=send_websocket_message, description="Send ping, expect pong"),
        Step(name="disconnect", action=disconnect_websocket, description="Disconnect"),
    ],
)


email_journey = Journey(
    name="email_testing",
    description="Email sending and verification journey",
    tags=["email", "mail"],
    steps=[
        Step(name="create_user", action=create_user_via_api, description="Create user"),
        Checkpoint(name="user_ready"),
        Step(name="send_email", action=send_email_via_api, description="Send email"),
        Step(name="verify_email", action=verify_email_received, description="Verify received"),
    ],
)


rate_limit_journey = Journey(
    name="rate_limit_testing",
    description="Rate limiting validation journey",
    tags=["rate-limit", "api"],
    steps=[
        Step(name="test_rate_limit", action=test_rate_limiting, description="Test rate limit"),
    ],
)


cache_journey = Journey(
    name="cache_testing",
    description="Cache operations journey",
    tags=["cache", "redis"],
    steps=[
        Step(name="test_cache", action=test_caching, description="Test cache ops"),
    ],
)


search_journey = Journey(
    name="search_testing",
    description="Search indexing and querying journey",
    tags=["search", "elasticsearch"],
    steps=[
        Step(name="test_search", action=test_search_indexing, description="Test search ops"),
    ],
)


background_job_journey = Journey(
    name="background_job_testing",
    description="Background job processing journey",
    tags=["queue", "celery", "async"],
    steps=[
        Step(name="create_user", action=create_user_via_api, description="Create user"),
        Step(name="create_item", action=create_item_via_api, description="Create item"),
        Checkpoint(name="resources_created"),
        Step(name="create_order", action=create_order, description="Create order"),
        Step(name="verify_job", action=verify_background_job, description="Verify job"),
    ],
)


all_journeys = [
    complete_journey,
    crud_only_journey,
    websocket_journey,
    email_journey,
    rate_limit_journey,
    cache_journey,
    search_journey,
    background_job_journey,
]
