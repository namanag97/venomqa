"""API versioning journeys.

Demonstrates:
- API v1 compatibility
- API v2 compatibility
- Version transition handling

This module provides journeys for testing API version compatibility
and migration between API versions.
"""

from __future__ import annotations

from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.client import Client


class VersionedAPIActions:
    """Actions for versioned API operations.

    Provides methods for interacting with different API versions,
    supporting version-specific features and behaviors.

    Args:
        base_url: Base URL for the API service.
        version: API version to use (e.g., 'v1', 'v2').
    """

    def __init__(self, base_url: str, version: str = "v1") -> None:
        self.client = Client(base_url=base_url)
        self.version = version
        self.base_path = f"/api/{version}"

    def get_items(self, token: str | None = None) -> Any:
        """Get all items from the versioned API.

        Args:
            token: Optional authentication token.

        Returns:
            Response object containing items list.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"{self.base_path}/items", headers=headers)

    def get_item(self, item_id: str, token: str | None = None) -> Any:
        """Get a single item by ID from the versioned API.

        Args:
            item_id: Unique identifier of the item.
            token: Optional authentication token.

        Returns:
            Response object containing item data.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"{self.base_path}/items/{item_id}", headers=headers)

    def create_item(self, data: dict[str, Any], token: str | None = None) -> Any:
        """Create a new item via the versioned API.

        Args:
            data: Item data to create.
            token: Optional authentication token.

        Returns:
            Response object from create request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(f"{self.base_path}/items", json=data, headers=headers)

    def update_item(self, item_id: str, data: dict[str, Any], token: str | None = None) -> Any:
        """Update an existing item via the versioned API.

        Args:
            item_id: Unique identifier of the item to update.
            data: Updated item data.
            token: Optional authentication token.

        Returns:
            Response object from update request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.patch(f"{self.base_path}/items/{item_id}", json=data, headers=headers)

    def delete_item(self, item_id: str, token: str | None = None) -> Any:
        """Delete an item via the versioned API.

        Args:
            item_id: Unique identifier of the item to delete.
            token: Optional authentication token.

        Returns:
            Response object from delete request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"{self.base_path}/items/{item_id}", headers=headers)

    def get_api_info(self) -> Any:
        """Get API version information.

        Returns:
            Response object containing API version details.
        """
        return self.client.get(f"{self.base_path}/info")


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


def get_v1_api_info(client: Client, context: dict) -> Any:
    """Get API v1 version information.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object containing v1 API info.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v1"
    )
    response = actions.get_api_info()
    if response.status_code == 200:
        data = response.json()
        context["v1_info"] = data
        assert data.get("version") == "1.0", "Should be v1 API"
    return response


def get_v2_api_info(client: Client, context: dict) -> Any:
    """Get API v2 version information.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object containing v2 API info.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v2"
    )
    response = actions.get_api_info()
    if response.status_code == 200:
        data = response.json()
        context["v2_info"] = data
        assert data.get("version") == "2.0", "Should be v2 API"
    return response


def create_v1_item(client: Client, context: dict) -> Any:
    """Create an item using API v1.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from create request.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v1"
    )
    response = actions.create_item(
        data={"name": "V1 Test Item", "value": 100},
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["v1_item_id"] = data.get("id")
        assert data.get("name") == "V1 Test Item", "Item name should match"
    return response


def create_v2_item(client: Client, context: dict) -> Any:
    """Create an item using API v2 with enhanced features.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from create request.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v2"
    )
    response = actions.create_item(
        data={"name": "V2 Test Item", "value": 200, "metadata": {"tags": ["test"]}},
        token=context.get("token"),
    )
    if response.status_code in [200, 201]:
        data = response.json()
        context["v2_item_id"] = data.get("id")
        assert data.get("name") == "V2 Test Item", "Item name should match"
        assert data.get("metadata") is not None, "V2 should support metadata"
    return response


def get_v1_item(client: Client, context: dict) -> Any:
    """Retrieve an item using API v1.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing v1_item_id.

    Returns:
        Response object containing item data.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v1"
    )
    response = actions.get_item(item_id=context["v1_item_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("id") == context["v1_item_id"], "Item ID should match"
    return response


def get_v2_item(client: Client, context: dict) -> Any:
    """Retrieve an item using API v2.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing v2_item_id.

    Returns:
        Response object containing item data with v2 features.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v2"
    )
    response = actions.get_item(item_id=context["v2_item_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("id") == context["v2_item_id"], "Item ID should match"
        assert data.get("metadata") is not None, "V2 items should have metadata"
    return response


def migrate_v1_to_v2(client: Client, context: dict) -> Any:
    """Access a v1 item through v2 API to test migration.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing v1_item_id.

    Returns:
        Response object containing migrated item data.
    """
    actions_v2 = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v2"
    )
    response = actions_v2.get_item(item_id=context["v1_item_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        context["migrated_item"] = data
    return response


def delete_v1_item(client: Client, context: dict) -> Any:
    """Delete an item using API v1.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing v1_item_id.

    Returns:
        Response object from delete request.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v1"
    )
    return actions.delete_item(item_id=context["v1_item_id"], token=context.get("token"))


def delete_v2_item(client: Client, context: dict) -> Any:
    """Delete an item using API v2.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing v2_item_id.

    Returns:
        Response object from delete request.
    """
    actions = VersionedAPIActions(
        base_url=context.get("base_url", "http://localhost:8000"), version="v2"
    )
    return actions.delete_item(item_id=context["v2_item_id"], token=context.get("token"))


api_v1_flow = Journey(
    name="api_v1",
    description="Test API v1 endpoints",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="get_api_info", action=get_v1_api_info),
        Step(name="create_item", action=create_v1_item),
        Checkpoint(name="item_created"),
        Step(name="get_item", action=get_v1_item),
        Step(name="cleanup", action=delete_v1_item),
    ],
)

api_v2_flow = Journey(
    name="api_v2",
    description="Test API v2 endpoints with enhanced features",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="get_api_info", action=get_v2_api_info),
        Step(name="create_item", action=create_v2_item),
        Checkpoint(name="item_created"),
        Step(name="get_item", action=get_v2_item),
        Step(name="cleanup", action=delete_v2_item),
    ],
)

api_version_transition_flow = Journey(
    name="api_version_transition",
    description="Test migration from v1 to v2 API",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="create_v1_item", action=create_v1_item),
        Checkpoint(name="v1_item_created"),
        Step(name="get_v1_info", action=get_v1_api_info),
        Step(name="get_v2_info", action=get_v2_api_info),
        Checkpoint(name="both_versions_available"),
        Branch(
            checkpoint_name="both_versions_available",
            paths=[
                Path(
                    name="v1_access",
                    steps=[
                        Step(name="access_v1", action=get_v1_item),
                        Step(name="verify_v1_format", action=get_v1_item),
                    ],
                ),
                Path(
                    name="v2_access_v1_data",
                    steps=[
                        Step(name="migrate_item", action=migrate_v1_to_v2),
                        Step(name="verify_migration", action=get_v2_item),
                    ],
                ),
            ],
        ),
        Step(name="cleanup_v1", action=delete_v1_item),
    ],
)
