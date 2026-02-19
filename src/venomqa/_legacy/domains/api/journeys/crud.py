"""Generic CRUD journeys for API testing.

Demonstrates:
- Create, Read, Update, Delete operations
- Bulk operations
- State branching at each operation

This module provides journeys for testing generic REST API CRUD operations
with support for individual and bulk operations.
"""

from __future__ import annotations

from typing import Any

from venomqa import Branch, JourneyCheckpoint as Checkpoint, Journey, Path, Step
from venomqa.http import Client


class CRUDActions:
    """Actions for generic CRUD operations.

    Provides methods for creating, reading, updating, and deleting
    resources through a configurable REST API endpoint.

    Args:
        base_url: Base URL for the API service.
        resource_path: API path for the resource (e.g., '/api/items').
    """

    def __init__(self, base_url: str, resource_path: str) -> None:
        self.client = Client(base_url=base_url)
        self.resource_path = resource_path.rstrip("/")

    def create(self, data: dict[str, Any], token: str | None = None) -> Any:
        """Create a new resource.

        Args:
            data: Resource data to create.
            token: Optional authentication token.

        Returns:
            Response object from create request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(self.resource_path, json=data, headers=headers)

    def list(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> Any:
        """List resources with pagination and optional filters.

        Args:
            page: Page number for pagination.
            per_page: Number of items per page.
            filters: Optional filter parameters.
            token: Optional authentication token.

        Returns:
            Response object containing paginated resource list.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if filters:
            params.update(filters)
        return self.client.get(self.resource_path, params=params, headers=headers)

    def get(self, resource_id: str, token: str | None = None) -> Any:
        """Retrieve a single resource by ID.

        Args:
            resource_id: Unique identifier of the resource.
            token: Optional authentication token.

        Returns:
            Response object containing resource data.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"{self.resource_path}/{resource_id}", headers=headers)

    def update(
        self,
        resource_id: str,
        data: dict[str, Any],
        partial: bool = True,
        token: str | None = None,
    ) -> Any:
        """Update a resource by ID.

        Args:
            resource_id: Unique identifier of the resource.
            data: Data to update.
            partial: If True, use PATCH; if False, use PUT.
            token: Optional authentication token.

        Returns:
            Response object from update request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        method = self.client.patch if partial else self.client.put
        return method(f"{self.resource_path}/{resource_id}", json=data, headers=headers)

    def delete(self, resource_id: str, token: str | None = None) -> Any:
        """Delete a resource by ID.

        Args:
            resource_id: Unique identifier of the resource to delete.
            token: Optional authentication token.

        Returns:
            Response object from delete request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"{self.resource_path}/{resource_id}", headers=headers)

    def bulk_create(self, items: list[dict[str, Any]], token: str | None = None) -> Any:
        """Create multiple resources in a single request.

        Args:
            items: List of resource data to create.
            token: Optional authentication token.

        Returns:
            Response object from bulk create request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"{self.resource_path}/bulk", json={"items": items}, headers=headers
        )

    def bulk_delete(self, ids: list[str], token: str | None = None) -> Any:
        """Delete multiple resources in a single request.

        Args:
            ids: List of resource IDs to delete.
            token: Optional authentication token.

        Returns:
            Response object from bulk delete request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"{self.resource_path}/bulk", json={"ids": ids}, headers=headers)


def login(client: Client, context: dict) -> Any:
    """Authenticate and store token in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from login request.
    """
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


def create_resource(client: Client, context: dict) -> Any:
    """Create a new resource and store resource_id in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from create request.
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = actions.create(
        data=context.get("create_data", {"name": "Test Item", "value": 100}),
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["resource_id"] = data.get("id")
        assert data.get("name") == context.get("create_data", {}).get("name", "Test Item"), (
            "Name should match"
        )
    return response


def list_resources(client: Client, context: dict) -> Any:
    """List resources with pagination.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object containing resource list.
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = actions.list(
        page=context.get("page", 1),
        per_page=context.get("per_page", 20),
        filters=context.get("filters"),
        token=context.get("token"),
    )
    if response.status_code == 200:
        data = response.json()
        context["resource_list"] = data.get("items", [])
        context["total_count"] = data.get("total", 0)
    return response


def get_resource(client: Client, context: dict) -> Any:
    """Retrieve a single resource by ID.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing resource_id.

    Returns:
        Response object containing resource data.
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = actions.get(resource_id=context["resource_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("id") == context["resource_id"], "ID should match"
    return response


def update_resource(client: Client, context: dict) -> Any:
    """Update a resource with data from context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing resource_id and update_data.

    Returns:
        Response object from update request.
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = actions.update(
        resource_id=context["resource_id"],
        data=context.get("update_data", {"name": "Updated Item"}),
        partial=context.get("partial_update", True),
        token=context.get("token"),
    )
    if response.status_code == 200:
        data = response.json()
        assert data.get("name") == context.get("update_data", {}).get("name", "Updated Item"), (
            "Name should be updated"
        )
    return response


def delete_resource(client: Client, context: dict) -> Any:
    """Delete a resource by ID.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing resource_id.

    Returns:
        Response object from delete request.
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return actions.delete(resource_id=context["resource_id"], token=context.get("token"))


def verify_deleted(client: Client, context: dict) -> Any:
    """Verify that a resource has been deleted (should return 404).

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing resource_id.

    Returns:
        Response object from get request (expecting 404).
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = actions.get(resource_id=context["resource_id"], token=context.get("token"))
    assert response.status_code == 404, "Resource should be deleted (404)"
    return response


def bulk_create_resources(client: Client, context: dict) -> Any:
    """Create multiple resources in bulk.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from bulk create request.
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    items = context.get(
        "bulk_items",
        [
            {"name": "Bulk Item 1", "value": 10},
            {"name": "Bulk Item 2", "value": 20},
            {"name": "Bulk Item 3", "value": 30},
        ],
    )
    response = actions.bulk_create(items=items, token=context.get("token"))
    if response.status_code in [200, 201]:
        data = response.json()
        context["bulk_ids"] = [item.get("id") for item in data.get("items", [])]
        assert len(data.get("items", [])) == len(items), "All items should be created"
    return response


def bulk_delete_resources(client: Client, context: dict) -> Any:
    """Delete multiple resources in bulk.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing bulk_ids.

    Returns:
        Response object from bulk delete request.
    """
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return actions.bulk_delete(ids=context["bulk_ids"], token=context.get("token"))


crud_create_flow = Journey(
    name="api_crud_create",
    description="Create and verify new resource",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create", action=create_resource),
        Checkpoint(name="created"),
        Step(name="verify", action=get_resource),
    ],
)

crud_read_flow = Journey(
    name="api_crud_read",
    description="List and get individual resources",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create", action=create_resource),
        Step(name="list", action=list_resources),
        Step(name="get", action=get_resource),
        Step(name="cleanup", action=delete_resource),
    ],
)

crud_update_flow = Journey(
    name="api_crud_update",
    description="Update resource with partial and full updates",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create", action=create_resource),
        Checkpoint(name="created"),
        Branch(
            checkpoint_name="created",
            paths=[
                Path(
                    name="partial_update",
                    steps=[
                        Step(
                            name="patch",
                            action=update_resource,
                            args={
                                "partial_update": True,
                                "update_data": {"name": "Partially Updated"},
                            },
                        ),
                        Step(name="verify_partial", action=get_resource),
                    ],
                ),
                Path(
                    name="full_update",
                    steps=[
                        Step(
                            name="put",
                            action=update_resource,
                            args={
                                "partial_update": False,
                                "update_data": {"name": "Fully Updated", "value": 200},
                            },
                        ),
                        Step(name="verify_full", action=get_resource),
                    ],
                ),
            ],
        ),
        Step(name="cleanup", action=delete_resource),
    ],
)

crud_delete_flow = Journey(
    name="api_crud_delete",
    description="Delete resource and verify deletion",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create", action=create_resource),
        Step(name="delete", action=delete_resource),
        Step(name="verify_deleted", action=verify_deleted),
    ],
)

crud_bulk_flow = Journey(
    name="api_crud_bulk",
    description="Bulk create and delete operations",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="bulk_create", action=bulk_create_resources),
        Checkpoint(name="bulk_created"),
        Step(name="list_verify", action=list_resources),
        Step(name="bulk_delete", action=bulk_delete_resources),
        Checkpoint(name="bulk_deleted"),
    ],
)
