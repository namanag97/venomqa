"""Generic CRUD journeys for API testing.

Demonstrates:
- Create, Read, Update, Delete operations
- Bulk operations
- State branching at each operation
"""


from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.clients import HTTPClient


class CRUDActions:
    def __init__(self, base_url: str, resource_path: str):
        self.client = HTTPClient(base_url=base_url)
        self.resource_path = resource_path.rstrip("/")

    def create(self, data: dict, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(self.resource_path, json=data, headers=headers)

    def list(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: dict | None = None,
        token: str | None = None,
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params = {"page": page, "per_page": per_page}
        if filters:
            params.update(filters)
        return self.client.get(self.resource_path, params=params, headers=headers)

    def get(self, resource_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(f"{self.resource_path}/{resource_id}", headers=headers)

    def update(
        self, resource_id: str, data: dict, partial: bool = True, token: str | None = None
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        method = self.client.patch if partial else self.client.put
        return method(f"{self.resource_path}/{resource_id}", json=data, headers=headers)

    def delete(self, resource_id: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"{self.resource_path}/{resource_id}", headers=headers)

    def bulk_create(self, items: list, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(
            f"{self.resource_path}/bulk", json={"items": items}, headers=headers
        )

    def bulk_delete(self, ids: list, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.delete(f"{self.resource_path}/bulk", json={"ids": ids}, headers=headers)


def login(client, context):
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


def create_resource(client, context):
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


def list_resources(client, context):
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


def get_resource(client, context):
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = actions.get(resource_id=context["resource_id"], token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        assert data.get("id") == context["resource_id"], "ID should match"
    return response


def update_resource(client, context):
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


def delete_resource(client, context):
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return actions.delete(resource_id=context["resource_id"], token=context.get("token"))


def verify_deleted(client, context):
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    response = actions.get(resource_id=context["resource_id"], token=context.get("token"))
    assert response.status_code == 404, "Resource should be deleted (404)"
    return response


def bulk_create_resources(client, context):
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


def bulk_delete_resources(client, context):
    actions = CRUDActions(
        base_url=context.get("base_url", "http://localhost:8000"),
        resource_path=context.get("resource_path", "/api/items"),
    )
    return actions.bulk_delete(ids=context["bulk_ids"], token=context.get("token"))


crud_create_flow = Journey(
    name="crud_create",
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
    name="crud_read",
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
    name="crud_update",
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
                            context_overrides={
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
                            context_overrides={
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
    name="crud_delete",
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
    name="crud_bulk",
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
