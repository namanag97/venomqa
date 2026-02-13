"""Hello World Actions for VenomQA Quickstart.

These actions demonstrate basic CRUD operations against a REST API.
Each action receives:
    - client: VenomQA HTTP client for making requests
    - context: Shared context dictionary for passing data between steps

Actions should return the HTTP response for automatic validation.
"""

from typing import Any


def check_health(client: Any, context: dict) -> Any:
    """Check API health status.

    Args:
        client: VenomQA HTTP client.
        context: Shared context dictionary.

    Returns:
        HTTP response from the health endpoint.
    """
    response = client.get("/health")

    # Store health info in context for later steps
    if response.status_code == 200:
        context["api_healthy"] = True
        context["api_version"] = response.json().get("version")

    return response


def list_items(client: Any, context: dict) -> Any:
    """List all items.

    Args:
        client: VenomQA HTTP client.
        context: Shared context dictionary.

    Returns:
        HTTP response with list of items.
    """
    response = client.get("/api/items")

    if response.status_code == 200:
        context["items_count"] = len(response.json())

    return response


def create_item(client: Any, context: dict, name: str = "Test Item", **kwargs) -> Any:
    """Create a new item.

    Args:
        client: VenomQA HTTP client.
        context: Shared context dictionary.
        name: Name for the new item.
        **kwargs: Additional item fields (description, price).

    Returns:
        HTTP response with created item.
    """
    payload = {
        "name": name,
        "description": kwargs.get("description", "Created by VenomQA"),
        "price": kwargs.get("price", 9.99),
    }

    response = client.post("/api/items", json=payload)

    if response.status_code == 201:
        item = response.json()
        context["created_item_id"] = item["id"]
        context["created_item"] = item

    return response


def get_item(client: Any, context: dict, item_id: int | None = None) -> Any:
    """Get an item by ID.

    Args:
        client: VenomQA HTTP client.
        context: Shared context dictionary.
        item_id: Item ID to fetch. If None, uses context["created_item_id"].

    Returns:
        HTTP response with item details.
    """
    if item_id is None:
        item_id = context.get("created_item_id")

    if item_id is None:
        raise ValueError("No item_id provided and none in context")

    response = client.get(f"/api/items/{item_id}")

    if response.status_code == 200:
        context["fetched_item"] = response.json()

    return response


def update_item(
    client: Any,
    context: dict,
    item_id: int | None = None,
    **updates,
) -> Any:
    """Update an item.

    Args:
        client: VenomQA HTTP client.
        context: Shared context dictionary.
        item_id: Item ID to update. If None, uses context["created_item_id"].
        **updates: Fields to update (name, description, price).

    Returns:
        HTTP response with updated item.
    """
    if item_id is None:
        item_id = context.get("created_item_id")

    if item_id is None:
        raise ValueError("No item_id provided and none in context")

    payload = {}
    if "name" in updates:
        payload["name"] = updates["name"]
    if "description" in updates:
        payload["description"] = updates["description"]
    if "price" in updates:
        payload["price"] = updates["price"]

    if not payload:
        payload = {"name": "Updated by VenomQA"}

    response = client.put(f"/api/items/{item_id}", json=payload)

    if response.status_code == 200:
        context["updated_item"] = response.json()

    return response


def delete_item(client: Any, context: dict, item_id: int | None = None) -> Any:
    """Delete an item.

    Args:
        client: VenomQA HTTP client.
        context: Shared context dictionary.
        item_id: Item ID to delete. If None, uses context["created_item_id"].

    Returns:
        HTTP response (204 No Content on success).
    """
    if item_id is None:
        item_id = context.get("created_item_id")

    if item_id is None:
        raise ValueError("No item_id provided and none in context")

    response = client.delete(f"/api/items/{item_id}")

    if response.status_code == 204:
        # Clean up context
        context.pop("created_item_id", None)
        context.pop("created_item", None)

    return response
