import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from venomqa import Journey, Step, Checkpoint
from venomqa.clients import HTTPClient


BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


def register_user(client, context):
    return client.post(
        "/api/auth/register",
        json={"email": "journey@example.com", "password": "testpass123", "name": "Journey User"},
    )


def login_user(client, context):
    response = client.post(
        "/api/auth/login",
        json={"email": "journey@example.com", "password": "testpass123"},
    )
    if response.status_code == 200:
        context["token"] = response.json()["access_token"]
    return response


def create_item(client, context):
    response = client.post(
        "/api/items",
        json={
            "name": "Journey Item",
            "description": "Created during journey test",
            "price": 99.99,
            "quantity": 5,
        },
        headers={"Authorization": f"Bearer {context['token']}"},
    )
    if response.status_code == 201:
        context["item_id"] = response.json()["item"]["id"]
    return response


def get_item(client, context):
    return client.get(f"/api/items/{context['item_id']}")


def update_item(client, context):
    return client.patch(
        f"/api/items/{context['item_id']}",
        json={"price": 149.99},
        headers={"Authorization": f"Bearer {context['token']}"},
    )


def delete_item(client, context):
    return client.delete(
        f"/api/items/{context['item_id']}", headers={"Authorization": f"Bearer {context['token']}"}
    )


verify_deletion = lambda client, ctx: client.get(f"/api/items/{ctx['item_id']}")


auth_journey = Journey(
    name="auth_flow",
    description="Test authentication flow",
    steps=[
        Step(name="register", action=register_user),
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
    ],
)


crud_journey = Journey(
    name="crud_flow",
    description="Test full CRUD lifecycle",
    steps=[
        Step(name="register", action=register_user),
        Step(name="login", action=login_user),
        Checkpoint(name="authenticated"),
        Step(name="create_item", action=create_item),
        Checkpoint(name="item_created"),
        Step(name="read_item", action=get_item),
        Step(name="update_item", action=update_item),
        Step(name="delete_item", action=delete_item),
        Checkpoint(name="item_deleted"),
    ],
)


list_journey = Journey(
    name="list_flow",
    description="Test list and pagination",
    steps=[
        Step(name="register", action=register_user),
        Step(name="login", action=login_user),
        Step(name="create_multiple", action=lambda c, ctx: [create_item(c, ctx) for _ in range(5)]),
        Step(name="list_items", action=lambda c, ctx: c.get("/api/items")),
    ],
)


JOURNEYS = [auth_journey, crud_journey, list_journey]
