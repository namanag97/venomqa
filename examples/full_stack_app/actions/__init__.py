import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Any


def register(client, context) -> dict[str, Any]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": context.get("email", "action@example.com"),
            "password": "testpass123",
            "name": "Action User",
        },
    )
    return {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }


def login(client, context) -> dict[str, Any]:
    response = client.post(
        "/api/auth/login",
        json={"email": context.get("email", "action@example.com"), "password": "testpass123"},
    )
    result = {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }
    if response.status_code == 200 and hasattr(response, "json"):
        context["token"] = response.json().get("access_token")
    return result


def create_item(client, context) -> dict[str, Any]:
    headers = {}
    if context.get("token"):
        headers["Authorization"] = f"Bearer {context['token']}"

    response = client.post(
        "/api/items",
        json={
            "name": context.get("item_name", "Test Item"),
            "description": context.get("item_description", "Test description"),
            "price": context.get("item_price", 29.99),
            "quantity": context.get("item_quantity", 1),
        },
        headers=headers,
    )

    result = {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }
    if response.status_code == 201 and hasattr(response, "json"):
        context["item_id"] = response.json().get("item", {}).get("id")
    return result


def get_item(client, context) -> dict[str, Any]:
    item_id = context.get("item_id")
    if not item_id:
        return {"status_code": 400, "data": {"error": "No item_id in context"}}

    response = client.get(f"/api/items/{item_id}")
    return {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }


def update_item(client, context) -> dict[str, Any]:
    item_id = context.get("item_id")
    token = context.get("token")

    if not item_id or not token:
        return {"status_code": 400, "data": {"error": "Missing item_id or token"}}

    response = client.patch(
        f"/api/items/{item_id}",
        json={
            "name": context.get("new_name", "Updated Item"),
            "price": context.get("new_price", 49.99),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    return {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }


def delete_item(client, context) -> dict[str, Any]:
    item_id = context.get("item_id")
    token = context.get("token")

    if not item_id or not token:
        return {"status_code": 400, "data": {"error": "Missing item_id or token"}}

    response = client.delete(f"/api/items/{item_id}", headers={"Authorization": f"Bearer {token}"})
    return {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }


def list_items(client, context) -> dict[str, Any]:
    page = context.get("page", 1)
    per_page = context.get("per_page", 20)

    response = client.get(f"/api/items?page={page}&per_page={per_page}")
    return {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }


def health_check(client, context) -> dict[str, Any]:
    response = client.get("/health")
    return {
        "status_code": response.status_code,
        "data": response.json() if hasattr(response, "json") else {},
    }


ACTIONS = {
    "register": register,
    "login": login,
    "create_item": create_item,
    "get_item": get_item,
    "update_item": update_item,
    "delete_item": delete_item,
    "list_items": list_items,
    "health_check": health_check,
}
