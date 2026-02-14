# CRUD Operations

Examples of testing Create, Read, Update, Delete operations.

## Basic CRUD Journey

```python
from venomqa import Journey, Step, Checkpoint

def create_item(client, context):
    """Create a new item."""
    response = client.post("/api/items", json={
        "name": "Test Item",
        "price": 29.99,
        "description": "A test item",
    })

    if response.status_code in [200, 201]:
        context["item_id"] = response.json()["id"]
        context["item_name"] = response.json()["name"]

    return response


def read_item(client, context):
    """Read the created item."""
    item_id = context.get_required("item_id")
    return client.get(f"/api/items/{item_id}")


def update_item(client, context):
    """Update the item."""
    item_id = context.get_required("item_id")
    return client.put(f"/api/items/{item_id}", json={
        "name": "Updated Item",
        "price": 39.99,
        "description": "An updated test item",
    })


def delete_item(client, context):
    """Delete the item."""
    item_id = context.get_required("item_id")
    return client.delete(f"/api/items/{item_id}")


def verify_deleted(client, context):
    """Verify item no longer exists."""
    item_id = context.get_required("item_id")
    return client.get(f"/api/items/{item_id}")


journey = Journey(
    name="item_crud",
    description="Test complete CRUD operations for items",
    tags=["crud", "items"],
    steps=[
        Step(name="create", action=create_item),
        Checkpoint(name="item_created"),
        Step(name="read", action=read_item),
        Step(name="update", action=update_item),
        Step(name="read_updated", action=read_item),
        Step(name="delete", action=delete_item),
        Step(
            name="verify_deleted",
            action=verify_deleted,
            expect_failure=True,
        ),
    ],
)
```

## CRUD with Authentication

```python
from venomqa import Journey, Step, Checkpoint


def login(client, context):
    """Login to get auth token."""
    response = client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "admin123",
    })

    if response.status_code == 200:
        token = response.json()["token"]
        context["token"] = token
        client.set_auth_token(token)

    return response


def create_user(client, context):
    """Create a new user."""
    response = client.post("/api/users", json={
        "email": "newuser@example.com",
        "name": "New User",
        "role": "member",
    })

    if response.status_code in [200, 201]:
        context["user_id"] = response.json()["id"]

    return response


def read_user(client, context):
    """Read user details."""
    user_id = context.get_required("user_id")
    return client.get(f"/api/users/{user_id}")


def update_user(client, context):
    """Update user details."""
    user_id = context.get_required("user_id")
    return client.patch(f"/api/users/{user_id}", json={
        "name": "Updated User",
        "role": "admin",
    })


def delete_user(client, context):
    """Delete user."""
    user_id = context.get_required("user_id")
    return client.delete(f"/api/users/{user_id}")


journey = Journey(
    name="user_crud_admin",
    description="Admin CRUD operations for users",
    tags=["crud", "users", "admin"],
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create_user", action=create_user),
        Checkpoint(name="user_created"),
        Step(name="read_user", action=read_user),
        Step(name="update_user", action=update_user),
        Step(name="verify_update", action=read_user),
        Step(name="delete_user", action=delete_user),
    ],
)
```

## CRUD with Validation Testing

```python
from venomqa import Journey, Step, Branch, Path, Checkpoint


def create_valid_item(client, context):
    """Create item with valid data."""
    return client.post("/api/items", json={
        "name": "Valid Item",
        "price": 29.99,
    })


def create_without_name(client, context):
    """Create item without required name."""
    return client.post("/api/items", json={
        "price": 29.99,
    })


def create_with_negative_price(client, context):
    """Create item with invalid price."""
    return client.post("/api/items", json={
        "name": "Invalid Item",
        "price": -10.00,
    })


def create_with_empty_name(client, context):
    """Create item with empty name."""
    return client.post("/api/items", json={
        "name": "",
        "price": 29.99,
    })


journey = Journey(
    name="item_validation",
    description="Test item creation validation",
    tags=["crud", "validation"],
    steps=[
        # Valid creation
        Step(name="create_valid", action=create_valid_item),

        Checkpoint(name="baseline"),

        # Validation errors
        Branch(
            checkpoint_name="baseline",
            paths=[
                Path(name="missing_name", steps=[
                    Step(
                        name="create",
                        action=create_without_name,
                        expect_failure=True,
                    ),
                ]),
                Path(name="negative_price", steps=[
                    Step(
                        name="create",
                        action=create_with_negative_price,
                        expect_failure=True,
                    ),
                ]),
                Path(name="empty_name", steps=[
                    Step(
                        name="create",
                        action=create_with_empty_name,
                        expect_failure=True,
                    ),
                ]),
            ],
        ),
    ],
)
```

## Bulk Operations

```python
from venomqa import Journey, Step


def create_items_batch(client, context):
    """Create multiple items in one request."""
    items = [
        {"name": f"Item {i}", "price": 10.00 + i}
        for i in range(10)
    ]

    response = client.post("/api/items/batch", json={"items": items})

    if response.status_code in [200, 201]:
        context["item_ids"] = [item["id"] for item in response.json()["items"]]

    return response


def list_items(client, context):
    """List all items."""
    return client.get("/api/items", params={"limit": 100})


def delete_items_batch(client, context):
    """Delete multiple items."""
    item_ids = context.get_required("item_ids")
    return client.post("/api/items/batch-delete", json={"ids": item_ids})


journey = Journey(
    name="bulk_operations",
    description="Test bulk create and delete",
    tags=["crud", "bulk"],
    steps=[
        Step(name="create_batch", action=create_items_batch),
        Step(name="list_items", action=list_items),
        Step(name="delete_batch", action=delete_items_batch),
        Step(name="verify_empty", action=list_items),
    ],
)
```

## Pagination Testing

```python
from venomqa import Journey, Step


def create_many_items(client, context):
    """Create items for pagination testing."""
    for i in range(25):
        client.post("/api/items", json={
            "name": f"Item {i}",
            "price": 10.00,
        })
    return {"created": 25}


def get_page_1(client, context):
    """Get first page."""
    response = client.get("/api/items", params={"page": 1, "limit": 10})
    context["page_1_count"] = len(response.json()["items"])
    return response


def get_page_2(client, context):
    """Get second page."""
    response = client.get("/api/items", params={"page": 2, "limit": 10})
    context["page_2_count"] = len(response.json()["items"])
    return response


def get_page_3(client, context):
    """Get third page (partial)."""
    response = client.get("/api/items", params={"page": 3, "limit": 10})
    context["page_3_count"] = len(response.json()["items"])
    return response


journey = Journey(
    name="pagination_test",
    description="Test pagination",
    tags=["crud", "pagination"],
    steps=[
        Step(name="create_items", action=create_many_items),
        Step(name="page_1", action=get_page_1),
        Step(name="page_2", action=get_page_2),
        Step(name="page_3", action=get_page_3),
    ],
)
```

## Search and Filter

```python
from venomqa import Journey, Step


def setup_items(client, context):
    """Create items with different categories."""
    items = [
        {"name": "Apple", "category": "fruit", "price": 1.50},
        {"name": "Banana", "category": "fruit", "price": 0.75},
        {"name": "Carrot", "category": "vegetable", "price": 2.00},
        {"name": "Broccoli", "category": "vegetable", "price": 3.00},
    ]

    for item in items:
        client.post("/api/items", json=item)

    return {"created": len(items)}


def search_by_name(client, context):
    """Search items by name."""
    return client.get("/api/items", params={"q": "apple"})


def filter_by_category(client, context):
    """Filter items by category."""
    return client.get("/api/items", params={"category": "fruit"})


def filter_by_price_range(client, context):
    """Filter items by price range."""
    return client.get("/api/items", params={
        "min_price": 1.00,
        "max_price": 2.00,
    })


def sort_by_price(client, context):
    """Sort items by price."""
    return client.get("/api/items", params={
        "sort": "price",
        "order": "desc",
    })


journey = Journey(
    name="search_filter",
    description="Test search and filter",
    tags=["crud", "search", "filter"],
    steps=[
        Step(name="setup", action=setup_items),
        Step(name="search_name", action=search_by_name),
        Step(name="filter_category", action=filter_by_category),
        Step(name="filter_price", action=filter_by_price_range),
        Step(name="sort_price", action=sort_by_price),
    ],
)
```
